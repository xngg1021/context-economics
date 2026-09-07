"""Frozen, sequential public-task campaign using the existing paired runner.

prepare creates a reviewed input bundle. run requires an unchanged git checkout,
a matching frozen bundle and named provider credential. No production mutation.
"""
from __future__ import annotations
import argparse
import json
import os
import platform
import shutil
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

# Credentialed entry must use the trusted isolated bootstrap. This guard runs
# before any repository import; -I -S bootstrap also excludes startup/pyc poison.
if __name__ == '__main__' and any(os.environ.get(k) for k in (
    'OPENAI_API_KEY','ANTHROPIC_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','MOONSHOT_API_KEY')):
    print(json.dumps({'status':'BLOCKED','reason':'use trusted_runtime_bootstrap with python -I -S'}))
    raise SystemExit(2)

import experiment_runner as er
import provider_runtime as pr
import runtime_experiment as rx

KINDS = ('path', 'identifier', 'number', 'date', 'negation', 'constraint',
         'intent', 'tool_protocol', 'structured_id', 'retrievable_output',
         'reasoning_state', 'social_intent')
SOURCE_ROOT = Path(__file__).resolve().parent
_BOOTSTRAP_SOURCE_IDENTITY = None


def task_set(split, count):
    if split not in {'smoke', 'pilot', 'train', 'holdout'} or type(count) is not int or not 2 <= count <= 40:
        raise ValueError('invalid split/count')
    tasks=[]
    for i in range(count):
        kind=KINDS[i % len(KINDS)]
        value = {'path': f'src/{split}/cache_{i}.py', 'identifier':f'retry_{split}_{i}',
                 'number':str(37+i), 'date':f'2026-10-{i%28+1:02d}',
                 'negation':f'do not use provider_{i}', 'constraint':f'do not modify branch_{i}',
                 'intent':f'compare before editing item_{i}', 'tool_protocol':f'foo_{i},bar_{i}',
                 'structured_id':f'{split}-X0-{i:04d}', 'retrievable_output':f'public_fixture_{i}',
                 'reasoning_state':f'rejected design_{i}', 'social_intent':f'ask before sending item_{i}'}[kind]
        fact=f'The exact required value of {kind} is: {value}'
        noise=[f'Unrelated archived item {j} in {split}.' for j in range(12)]
        # Alternate early/tail facts; preserve negative outcomes when bounding loses facts.
        history=[fact]+noise if (i + i//len(KINDS))%2 == 0 else noise+[fact]
        tasks.append({'task_id':f'{split}-{i:03d}', 'content_type':kind,'history':history,
                      'input':f'Return only the exact required value of {kind} from the history.',
                      'expected_answer':value})
    return tasks


def identity():
    if _BOOTSTRAP_SOURCE_IDENTITY is not None:
        # Set only in the isolated child after trusted source extraction/import,
        # before its provider credential is delivered. Not a promotion attestation.
        return dict(_BOOTSTRAP_SOURCE_IDENTITY)
    # Source inspection is not a provider operation. Git helpers/fsmonitor must
    # never inherit runtime provider credentials or injected Git configuration.
    environment = {'PATH':os.defpath, 'LC_ALL':'C'}
    if os.name == 'nt' and 'SystemRoot' in os.environ:
        environment['SystemRoot'] = os.environ['SystemRoot']
    environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_OPTIONAL_LOCKS='0')
    executable = shutil.which('git', path=os.defpath)
    if not executable:
        raise ValueError('trusted Git executable unavailable')
    def git(*args):return subprocess.check_output(
        [executable,'-c','core.fsmonitor=false','-c','core.untrackedCache=false',*args],
        text=True,env=environment,cwd=SOURCE_ROOT).strip()
    if git('status','--porcelain','--untracked-files=normal'):
        raise ValueError('source checkout must be clean')
    return {'repository_commit':git('rev-parse','HEAD'),'repository_tree':git('rev-parse','HEAD^{tree}')}


def prepare(provider, revision, pricing_path, output, experiment_id, split, count):
    source=identity()
    snapshot=json.loads(Path(pricing_path).read_text())
    from pricing_refresh import check
    if check(snapshot)['stale']:raise ValueError('pricing snapshot stale')
    row=snapshot['models'][revision]
    price=pr.Price(provider,revision,row['input'],row['output'],row['cached_read'],
                   'sha256:'+pr.digest(snapshot),row.get('max_input_tokens',200000))
    pr.ProviderExecutor(provider,revision,price)
    if row['provider'] != provider or row['currency'] != 'USD' or row['unit'] != 'per-million-tokens':
        raise ValueError('pricing unit/provider mismatch')
    if split == 'holdout' and count < 24:
        raise ValueError('formal holdout requires at least 24 pairs')
    tasks=task_set(split,count)
    policy={'control':{'history_limit':None},'treatment':{'history_limit':4}}
    pins={**source,'provider':provider,'model_revision':revision,'split':split,
          'tasks_digest':pr.digest(tasks),'policy_digest':pr.digest(policy),
          'pricing_digest':pr.digest(snapshot),'scorer':'public-exact-match:v1',
          'scorer_source_digest':pr.digest((SOURCE_ROOT/'provider_runtime.py').read_text()),
          'created_at':datetime.now(timezone.utc).isoformat(),
          'primary_metric':'cost_per_success','assignment':'counterbalanced',
          'gate_config':asdict(__import__('experiment_analysis').GateConfig(max_treatment_p95_wall_time_ms=30000)),
          'production_mutation':False,'calibration':'fixed a priori; no holdout tuning',
          'isolation':{'fresh_session':True,'unique_prefix_per_run':True,
                       'cache_state':'unavailable','provider_cache_key':None,
                       'cross_arm_cache_control':'prefix diversification proxy; no guaranteed cold cache'}}
    bundle={'experiment_id':experiment_id,'pins':pins,'tasks':tasks,'policy':policy,
            'price':asdict(price),'pricing_snapshot':snapshot}
    bundle['bundle_digest']=pr.digest(bundle)
    er.publish_artifacts(Path(output),{'campaign.json':json.dumps(bundle,indent=2)+'\n'})
    return bundle


def run(path, output):
    bundle=json.loads(Path(path).read_text())
    claimed=bundle.pop('bundle_digest')
    if claimed != pr.digest(bundle):raise ValueError('campaign fingerprint mismatch')
    pins=bundle['pins'];current=identity()
    if any(pins[k]!=v for k,v in current.items()):raise ValueError('source identity changed; prepare successor')
    if pr.digest(bundle['tasks'])!=pins['tasks_digest'] or pr.digest(bundle['policy'])!=pins['policy_digest']:
        raise ValueError('task/policy digest mismatch')
    if pr.digest(bundle['pricing_snapshot'])!=pins['pricing_digest']:
        raise ValueError('pricing digest mismatch')
    if pins['scorer'] != 'public-exact-match:v1' or pins['scorer_source_digest'] != pr.digest((SOURCE_ROOT/'provider_runtime.py').read_text()):
        raise ValueError('scorer implementation digest mismatch')
    # A caller can recompute JSON digests. Enforce the bounded reviewed generator
    # itself before any credentialed request, not just internal hash consistency.
    tasks=bundle['tasks']
    if not isinstance(tasks,list) or tasks != task_set(pins['split'],len(tasks)):
        raise ValueError('tasks do not match bounded canonical generator')
    if pins['split']=='holdout' and len(tasks)<24:
        raise ValueError('formal holdout requires at least 24 pairs')
    if bundle['policy'] != {'control':{'history_limit':None},'treatment':{'history_limit':4}}:
        raise ValueError('policy does not match reviewed candidate')
    from pricing_refresh import check
    if check(bundle['pricing_snapshot'])['stale']:raise ValueError('pricing snapshot stale')
    provider=pins['provider']
    if not os.environ.get(pr.CREDENTIALS[provider]):raise pr.ProviderError('credential_unavailable')
    price=pr.Price(**bundle['price']);rev=pins['model_revision']
    rate=bundle['pricing_snapshot']['models'][rev]
    expected_price=pr.Price(provider,rev,rate['input'],rate['output'],rate['cached_read'],
                            'sha256:'+pins['pricing_digest'],rate.get('max_input_tokens',200000))
    if price != expected_price or rate['provider'] != provider or rate['currency'] != 'USD' or rate['unit'] != 'per-million-tokens':
        raise ValueError('execution price does not match pinned snapshot')
    manifest=rx.ExperimentManifest.from_mapping({
        'experiment_id':bundle['experiment_id'],'declared_evidence_class':'runtime-A/B',
        'assignment_method':'counterbalanced','control_policy':'control','treatment_policy':'treatment',
        'provider':provider,'model':rev,'model_revision':rev,'harness_revision':'provider-runtime:v1',
        'repository_commit':current['repository_commit'],'runtime_environment_ref':'python:'+platform.python_version(),
        'task_set_ref':'sha256:'+pins['tasks_digest'],'pricing_snapshot_ref':price.source,
        'policy_bundle_ref':'sha256:'+pins['policy_digest'],
        'expected_task_ids':[t['task_id'] for t in bundle['tasks']]})
    executors={arm:pr.ProviderExecutor(provider,rev,price,**policy) for arm,policy in bundle['policy'].items()}
    __import__('experiment_analysis').GateConfig(**pins['gate_config'])
    if Path(output, bundle['experiment_id']).exists():
        raise ValueError('experiment output already exists')
    if not __import__('re').fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',bundle['experiment_id']):
        raise ValueError('unsafe experiment identity')
    try:
        model_check=pr.verify_model(provider,pins['model_revision'])
    except pr.ProviderError as exc:
        # Models lookup is separate from completion requests; no fabricated usage.
        er.publish_artifacts(Path(output)/bundle['experiment_id'], {
            'manifest.json':json.dumps({'manifest':asdict(manifest)}),
            'campaign-ref.json':json.dumps({'digest':claimed,'pins':pins}),
            'failure.json':json.dumps({'status':'aborted','phase':'model_preflight',
                'failure_class':er.failure_category(exc),'actual_completion_requests':0,
                'model_lookup_attempts':1,'provider_bill':None,'billing_status':'unavailable',
                'evidence_eligible':False,'candidate_for_promotion':False,'production_mutation':False})})
        raise pr.ProviderError('model_preflight_aborted') from None
    extras={'model-availability.json':model_check,
            'capabilities.json':{a:e.capabilities.to_mapping() for a,e in executors.items()},
            'environment.json':{'python':platform.python_version(),'system':platform.system(),**current},
            'pricing-snapshot-ref.json':{'digest':pins['pricing_digest'],'source_ref':price.source},
            'scorer-ref.json':{'identity':pins['scorer'],'digest':pins['scorer_source_digest']},
            'campaign-ref.json':{'digest':claimed,'pins':pins},
            'measurement-boundaries.json':{
                'native_cache_write':'nullable observations; legacy ledger zero projection is not measurement',
                'context':'submitted task input presence only; no access classifier for internal reasoning',
                'prefetch':'unsupported','reacquisition':'unsupported','tools':'disabled',
                'latency_and_failure_dollar_cost':'not monetized; legacy additive projection zero',
                'billing':'estimated; no observed-bill task-economic evidence'}}
    return er.run_experiment(manifest,bundle['tasks'],executors,output,
        config=__import__('experiment_analysis').GateConfig(**pins['gate_config']),
        target='runtime-A/B',allow_estimated=True,
        held_out_task_set_ref=manifest.task_set_ref if pins['split']=='holdout' else None,
        supplemental_artifacts=extras)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare')
    for arg in ('provider','revision','pricing','output','experiment-id'):p.add_argument('--'+arg,required=True)
    p.add_argument('--split',choices=['smoke','pilot','train','holdout'],default='smoke')
    p.add_argument('--count',type=int,default=2)
    p=sub.add_parser('run');p.add_argument('--campaign',required=True);p.add_argument('--output-root',default='artifacts')
    args=parser.parse_args(argv)
    try:
        if args.command=='prepare':prepare(args.provider,args.revision,args.pricing,args.output,args.experiment_id,args.split,args.count)
        else:run(args.campaign,args.output_root)
        print(json.dumps({'status':'complete','operation':args.command,'production_mutation':False}));return 0
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError):
        # Native errors, paths, private answers and credential names never printed.
        print(json.dumps({'status':'BLOCKED','operation':args.command,'evidence_upgraded':False}));return 2

if __name__=='__main__':raise SystemExit(main())
