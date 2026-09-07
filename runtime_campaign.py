"""Frozen, sequential public-task campaign using the existing paired runner.

prepare creates a reviewed input bundle. run requires an unchanged git checkout,
a matching frozen bundle and named provider credential. No production mutation.
"""
from __future__ import annotations
import argparse
import json
import os
import platform
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import experiment_runner as er
import provider_runtime as pr
import runtime_experiment as rx

KINDS = ('path', 'identifier', 'number', 'date', 'negation', 'constraint',
         'intent', 'tool_protocol', 'structured_id', 'retrievable_output',
         'reasoning_state', 'social_intent')


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
        history=[fact]+noise if i%2 == 0 else noise+[fact]
        tasks.append({'task_id':f'{split}-{i:03d}', 'content_type':kind,'history':history,
                      'input':f'Return only the exact required value of {kind} from the history.',
                      'expected_answer':value})
    return tasks


def identity():
    def git(*args):return subprocess.check_output(['git',*args],text=True).strip()
    if git('status','--porcelain','--untracked-files=normal'):
        raise ValueError('source checkout must be clean')
    return {'repository_commit':git('rev-parse','HEAD'),'repository_tree':git('rev-parse','HEAD^{tree}')}


def prepare(provider, revision, pricing_path, output, experiment_id, split, count):
    source=identity()
    snapshot=json.loads(Path(pricing_path).read_text())
    row=snapshot['models'][revision]
    price=pr.Price(provider,revision,row['input'],row['output'],row['cached_read'],
                   'sha256:'+pr.digest(snapshot),row.get('max_input_tokens',200000))
    pr.ProviderExecutor(provider,revision,price)
    if row['provider'] != provider or row['currency'] != 'USD' or row['unit'] != 'per-million-tokens':
        raise ValueError('pricing unit/provider mismatch')
    if split == 'holdout' and count < 20:
        raise ValueError('formal holdout requires at least 20 pairs')
    tasks=task_set(split,count)
    policy={'control':{'history_limit':None},'treatment':{'history_limit':4}}
    pins={**source,'provider':provider,'model_revision':revision,'split':split,
          'tasks_digest':pr.digest(tasks),'policy_digest':pr.digest(policy),
          'pricing_digest':pr.digest(snapshot),'scorer':'public-exact-match:v1',
          'scorer_source_digest':pr.digest(Path('provider_runtime.py').read_text()),
          'created_at':datetime.now(timezone.utc).isoformat(),
          'primary_metric':'cost_per_success','assignment':'counterbalanced',
          'gate_config':asdict(__import__('experiment_analysis').GateConfig()),
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
    provider=pins['provider']
    if not os.environ.get(pr.CREDENTIALS[provider]):raise pr.ProviderError('credential_unavailable')
    price=pr.Price(**bundle['price']);rev=pins['model_revision']
    manifest=rx.ExperimentManifest.from_mapping({
        'experiment_id':bundle['experiment_id'],'declared_evidence_class':'runtime-A/B',
        'assignment_method':'counterbalanced','control_policy':'control','treatment_policy':'treatment',
        'provider':provider,'model':rev,'model_revision':rev,'harness_revision':'provider-runtime:v1',
        'repository_commit':current['repository_commit'],'runtime_environment_ref':'python:'+platform.python_version(),
        'task_set_ref':'sha256:'+pins['tasks_digest'],'pricing_snapshot_ref':price.source,
        'policy_bundle_ref':'sha256:'+pins['policy_digest'],
        'expected_task_ids':[t['task_id'] for t in bundle['tasks']]})
    executors={arm:pr.ProviderExecutor(provider,rev,price,**policy) for arm,policy in bundle['policy'].items()}
    extras={'capabilities.json':{a:e.capabilities.to_mapping() for a,e in executors.items()},
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
