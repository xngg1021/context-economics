"""Small injectable paired experiment orchestrator; stdlib, no secrets in artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import threading
import tempfile
import shutil
from contextlib import contextmanager
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Mapping, Protocol, Sequence, Iterable

import context_runtime as rt
import experiment_analysis as ea
import runtime_experiment as rx
import runtime_http
import task_economics as te


class RunnerError(ValueError):
    pass


class RuntimeExecutor(Protocol):
    evidence_origin: str

    def execute(self, task: Mapping[str, object], *, run_id: str, policy_id: str,
                manifest: rx.ExperimentManifest) -> Iterable[Mapping[str, object]]:
        """Execute one arm and emit canonical, redacted telemetry including outcome."""
        ...


def run_experiment(manifest: rx.ExperimentManifest, tasks: Sequence[Mapping[str, object]],
                   executors: Mapping[str, RuntimeExecutor], output_root: str | Path,
                   *, config: ea.GateConfig | None = None, seed: int = 0,
                   target: str = 'task-economic', allow_estimated: bool = False,
                   held_out_task_set_ref: str | None = None,
                   supplemental_artifacts: Mapping[str, Mapping[str, object]] | None = None) -> Path:
    supplemental_artifacts = dict(supplemental_artifacts or {})
    reserved = {'manifest.json', 'schedule.json', 'raw-telemetry.json', 'normalized.json',
                'l5-receipts.json', 'l6-events.json', 'joint-report.json', 'paired-statistics.json',
                'acceptance.json', 'provenance.json', 'fingerprints.json', 'failure.json'}
    if reserved & supplemental_artifacts.keys():
        raise RunnerError('supplemental artifact collides with canonical output')
    for name, value in supplemental_artifacts.items():
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
            raise RunnerError('invalid supplemental artifact filename')
        rt._mapping(value, 'supplemental_artifact')
    raw_manifest = asdict(manifest)
    raw_manifest['expected_task_ids'] = list(manifest.expected_task_ids)
    manifest = rx.ExperimentManifest.from_mapping(raw_manifest)
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', manifest.experiment_id):
        raise RunnerError('experiment_id must be a safe single directory name')
    if manifest.assignment_method not in {'paired-fixed', 'counterbalanced'}:
        raise RunnerError('runner supports paired-fixed or counterbalanced')
    if type(seed) is not int:
        raise RunnerError('seed must be an integer')
    ids = [rt._text(t.get('task_id'), 'task_id') for t in tasks]
    if len(set(ids)) != len(ids) or set(ids) != set(manifest.expected_task_ids):
        raise RunnerError('task set must match manifest exactly without duplicates')
    arms = (manifest.control_policy, manifest.treatment_policy)
    if set(executors) != set(arms):
        raise RunnerError('executors must match the two manifest arms')
    origins = {executor.evidence_origin for executor in executors.values()}
    origin = next(iter(origins)) if len(origins) == 1 else 'mixed'
    if manifest.declared_evidence_class in {'runtime-A/B', 'task-economic'} and origin != 'real-provider':
        raise RunnerError('local or mixed executors cannot claim real runtime evidence')
    output = Path(output_root) / manifest.experiment_id
    if output.exists():
        raise RunnerError('experiment output already exists; choose a new experiment_id')
    schedule = ea.counterbalanced_schedule(ids, *arms)
    if manifest.assignment_method == 'paired-fixed':
        for assignment in schedule:
            assignment['order'] = list(arms)
    by_task = {task['task_id']: task for task in tasks}
    collector = rt.Collector(rt.CanonicalAdapter())
    run_number = 0
    for task_order, assignment in enumerate(schedule):
        assignment['task_order'] = task_order
        assignment['runs'] = []
        for arm_order, policy in enumerate(assignment['order']):
            run_id = f'{manifest.experiment_id}-run-{run_number:06d}'
            run_number += 1
            assignment['runs'].append({'run_id':run_id, 'policy_id':policy,
                                       'task_id':assignment['task_id'], 'arm_order':arm_order})
            try:
                events = list(executors[policy].execute(by_task[assignment['task_id']], run_id=run_id,
                                                      policy_id=policy, manifest=manifest))
            except Exception:
                # No fabricated bill/usage for a request without a valid receipt.
                # Persist prior completed arms and full expected-task denominator;
                # a failed campaign cannot enter performance aggregates.
                failed = {'manifest.json': {'manifest': raw_manifest},
                          'schedule.json': {'tasks': schedule},
                          'raw-telemetry.json': collector.bundle(),
                          'failure.json': {'status': 'aborted', 'failed_run_id': run_id,
                              'failed_task_id': assignment['task_id'], 'failed_policy_id': policy,
                              'failure_class': 'executor_failure', 'bill_status': 'unavailable',
                              'expected_task_count': len(ids), 'attempted_runs': run_number,
                              'performance_candidate': False, 'evidence_eligible': False,
                              'candidate_for_promotion': False, 'production_mutation': False}}
                publish_artifacts(output, {name:json.dumps(value, allow_nan=False)+'\n'
                                           for name,value in failed.items()})
                raise RunnerError('executor failed; immutable incomplete campaign recorded') from None
            if not events:
                raise RunnerError('executor emitted no events')
            for event in events:
                if (event.get('run_id'), event.get('task_id'), event.get('policy_id')) != (run_id, assignment['task_id'], policy):
                    raise RunnerError('executor crossed scheduled run/task/policy identity')
                collector.capture(event)
    raw = collector.bundle()
    normalized = rt.normalize([rt.Envelope.parse(row) for row in raw['events']])
    receipt_rows = normalized['l5_receipts']['runs']
    receipts = [te.RunReceipt.from_mapping(row) for row in receipt_rows]
    records = [rx.ReceiptRecord(receipt, frozenset(row)) for receipt,row in zip(receipts,receipt_rows)]
    events = [rx.ExperimentContextEvent.from_mapping(row) for row in normalized['l6_context_events']['events']]
    joint = rx.build_joint_report(manifest, records, events, require_complete=True)
    statistics = ea.paired_statistics(receipts, *arms, seed=seed)
    acceptance = ea.acceptance_gate(receipts, {}, *arms, config or ea.GateConfig(),
                                   manifest=manifest, experiment_events=events,
                                   target=target, allow_estimated=allow_estimated,
                                   evidence_origin=origin, held_out_task_set_ref=held_out_task_set_ref)
    provenance = {**raw_manifest, 'evidence_origin':origin, 'seed':seed,
                  'held_out_task_set_ref':held_out_task_set_ref,
                  'scorers':sorted({(r.scorer_id,r.scorer_version,r.scoring_provenance) for r in receipts}),
                  'billing_evidence':sorted({(r.billing_status,r.provider_bill_source) for r in receipts}),
                  'time_boundary':'request wall time measured; non-streaming TTFT unknown',
                  'public_evidence':'simulation / contract E2E' if origin == 'loopback' else 'caller-declared; not independently authenticated'}
    artifacts = {'manifest.json':{'schema_version':1,'manifest':raw_manifest},
                 'schedule.json':{'assignment_method':manifest.assignment_method,'tasks':schedule},
                 'raw-telemetry.json':raw, 'normalized.json':normalized,
                 'l5-receipts.json':normalized['l5_receipts'],
                 'l6-events.json':normalized['l6_context_events'],
                 'joint-report.json':joint, 'paired-statistics.json':statistics,
                 'acceptance.json':acceptance, 'provenance.json':provenance}
    artifacts.update(supplemental_artifacts)
    # Validate serialization before creating a finished directory. No task text or answers persisted.
    rendered = {name:json.dumps(te._json_safe(value),indent=2,ensure_ascii=False,allow_nan=False)+'\n'
                for name,value in artifacts.items()}
    if supplemental_artifacts:
        rendered['fingerprints.json'] = json.dumps({
            'algorithm': 'sha256', 'scope': 'all other files; fingerprint index excluded',
            'files': {name:hashlib.sha256(content.encode()).hexdigest() for name,content in rendered.items()}
        }, indent=2)+'\n'
    publish_artifacts(output, rendered)
    return output


def publish_artifacts(output: Path, rendered: Mapping[str, str]) -> None:
    """Publish a complete directory only; same-parent rename is atomic."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() or not rendered:
        raise RunnerError('output exists or artifact set is empty')
    if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name) for name in rendered):
        raise RunnerError('artifact names must be single safe filenames')
    staging = Path(tempfile.mkdtemp(prefix='.'+output.name+'-',dir=output.parent))
    try:
        for name, content in rendered.items():
            path = staging / name
            path.write_text(content,encoding='utf-8')
        # Same-parent rename is the commit point. Concurrent completed outputs
        # are nonempty, so rename refuses to replace them. No stale lock blocks
        # retry after process termination; orphan private staging can be removed.
        staging.rename(output)
        staging = None
    finally:
        if staging is not None:
            shutil.rmtree(staging)


class LocalHTTPExecutor:
    """Synthetic transport fixture, never a credential-backed evidence source."""
    evidence_origin = 'loopback'

    def __init__(self, url: str):
        self.url = url

    def execute(self, task, *, run_id, policy_id, manifest):
        event, answer = runtime_http.run_request(url=self.url,run_id=run_id,
            task_id=task['task_id'],policy_id=policy_id,model=manifest.model,
            model_revision=manifest.model_revision,sequence_index=0,input_text=task['input'])
        event['event_id'] = run_id+'-request'
        yield event
        envelope = {'run_id':run_id, 'task_id':task['task_id'], 'policy_id':policy_id,
                    'occurred_at':event['occurred_at']}
        yield {**envelope,'event_id':run_id+'-context','event_kind':'context',
               'payload':{'kind':'context_hit','asset_id':'synthetic-task-input'}}
        yield {**envelope,'event_id':run_id+'-outcome','event_kind':'outcome',
               'payload':{'success':answer == task['expected_answer'],
                   'task_score':float(answer == task['expected_answer']),
                   'scorer_id':'local-exact-match','scorer_version':'v1',
                   'scoring_provenance':'benchmark','harness_revision':manifest.harness_revision}}


@contextmanager
def local_http_server():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            body = json.dumps({'id':'local-fixture', 'model':payload['model'],
                'usage':{'prompt_tokens':8,'completion_tokens':1,'prompt_tokens_details':{'cached_tokens':3}},
                'billing':{'amount_usd':.0001,'source':'synthetic-price:v1','status':'estimated'},
                'choices':[{'message':{'role':'assistant','content':'4'}}]}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self, *args):
            pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/v1/chat/completions'
    finally:
        server.shutdown();server.server_close();thread.join()


def local_manifest(experiment_id, repository_commit, assignment='counterbalanced'):
    return rx.ExperimentManifest.from_mapping({
        'experiment_id':experiment_id, 'declared_evidence_class':'synthetic-contract',
        'assignment_method':assignment, 'control_policy':'control', 'treatment_policy':'treatment',
        'provider':'openai-compatible', 'model':'deterministic', 'model_revision':'v1',
        'harness_revision':'local-http-runner:v1', 'repository_commit':repository_commit,
        'runtime_environment_ref':'stdlib-loopback:v1','task_set_ref':'local-arithmetic:v1',
        'pricing_snapshot_ref':'synthetic-price:v1','policy_bundle_ref':'identical-local-arms:v1',
        'expected_task_ids':['task-a','task-b']})


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local-demo',action='store_true',required=True)
    parser.add_argument('--experiment-id',default='local-e2e')
    parser.add_argument('--output-root',default='artifacts')
    parser.add_argument('--repository-sha')
    parser.add_argument('--assignment',choices=['paired-fixed','counterbalanced'],default='counterbalanced')
    args=parser.parse_args(argv)
    try:
        sha=args.repository_sha or subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
        manifest=local_manifest(args.experiment_id,sha,args.assignment)
        tasks=[{'task_id':task,'input':'2+2','expected_answer':'4'} for task in manifest.expected_task_ids]
        with local_http_server() as url:
            executor=LocalHTTPExecutor(url)
            output=run_experiment(manifest,tasks,{'control':executor,'treatment':executor},args.output_root)
        print(json.dumps({'status':'complete','output':str(output),'evidence':'simulation / contract E2E'}))
        return 0
    except (ValueError,TypeError,OSError,subprocess.SubprocessError) as exc:
        print(json.dumps({'status':'ERROR','error':type(exc).__name__,'message':str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
