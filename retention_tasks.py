"""Public deterministic task outcomes; no model-quality or monetary claim.

Solver receives only retained history + query, never the expected answer.
The optional lookup arm is a SEPARATE deterministic reacquisition experiment.
Provider tokens/bills and real-model semantic retention remain unavailable.
"""
import argparse
import json
import time
from collections import defaultdict
from statistics import mean
from runtime_campaign import KINDS


def tasks(split='train'):
    if split not in ('train', 'holdout'):
        raise ValueError('invalid split')
    rows = []
    for i in range(24):
        kind = KINDS[i % 12]
        key = f'{split}-{kind}-{i}'
        data, query, expected = {
            'path': ({'root': f'src/{split}', 'file': f'module{i}.py'}, {}, f'src/{split}/module{i}.py'),
            'identifier': ({'aliases': {'target': f'retry_{i}'}}, {'alias':'target'}, f'retry_{i}'),
            'number': ({'capacity': 100+i, 'used': 37}, {}, 63+i),
            'date': ({'start': '2026-10-01', 'days': i+1}, {}, f'2026-10-{i+2:02d}'),
            'negation': ({'forbidden': 'alpha'}, {'options':['alpha','beta']}, 'beta'),
            'constraint': ({'limit': i+2}, {'requested': i+3}, 'reject'),
            'intent': ({'mode':'compare-before-edit'}, {'operation':'edit'}, 'defer'),
            'tool_protocol': ({'pending': [f'call-{i}']}, {'reply_to':f'call-{i}'}, 'accept'),
            'structured_id': ({'account':{'id':f'{split}-X-{i:04d}'}}, {}, f'{split}-X-{i:04d}'),
            'retrievable_output': ({'table': {'a':i, 'b':i+1}}, {}, 2*i+1),
            'reasoning_state': ({'rejected':['A','B']}, {'candidates':['A','B','C']}, 'C'),
            'social_intent': ({'consent':False}, {'operation':'send'}, 'ask'),
        }[kind]
        fact = json.dumps({'key':key, 'kind':kind, 'data':data}, sort_keys=True)
        noise = [json.dumps({'key':f'noise-{j}', 'kind':'noise', 'data':{}}) for j in range(12)]
        history = [fact]+noise if (i+i//12)%2 == 0 else noise+[fact]
        rows.append({'task_id':key, 'kind':kind, 'history':history, 'query':{'key':key, **query},
                     'expected':expected, 'fact':fact})
    return rows


def solve(history, query):
    from datetime import date, timedelta
    found = [json.loads(row) for row in history if json.loads(row).get('key') == query['key']]
    if len(found) != 1:
        return None
    record = found[0]; d = record['data']; k = record['kind']
    if k == 'path': return d['root']+'/'+d['file']
    if k == 'identifier': return d['aliases'][query['alias']]
    if k == 'number': return d['capacity']-d['used']
    if k == 'date': return (date.fromisoformat(d['start'])+timedelta(days=d['days'])).isoformat()
    if k == 'negation': return next(x for x in query['options'] if x != d['forbidden'])
    if k == 'constraint': return 'reject' if query['requested'] > d['limit'] else 'accept'
    if k == 'intent': return 'defer' if d['mode']=='compare-before-edit' and query['operation']=='edit' else 'proceed'
    if k == 'tool_protocol': return 'accept' if query['reply_to'] in d['pending'] else 'reject'
    if k == 'structured_id': return d['account']['id']
    if k == 'retrievable_output': return sum(d['table'].values())
    if k == 'reasoning_state': return next(x for x in query['candidates'] if x not in d['rejected'])
    if k == 'social_intent': return 'ask' if not d['consent'] and query['operation']=='send' else 'proceed'
    raise ValueError('unsupported task')


def evaluate(split='train', *, reacquire=False):
    source = tasks(split)
    catalog = {row['task_id']:row['fact'] for row in source}
    policies = []
    for limit in (None, 8, 4):
        by_kind = defaultdict(list)
        for row in source:
            history = row['history'] if limit is None else row['history'][-limit:]
            literal = row['fact'] in history
            begin = time.perf_counter()
            answer = solve(history, row['query'])
            calls = int(answer is None and reacquire)
            if calls:
                # Exact public key lookup; expected answer is never supplied to solver.
                answer = solve([catalog[row['query']['key']]], row['query'])
            elapsed = (time.perf_counter()-begin)*1000
            by_kind[row['kind']].append({'success':answer == row['expected'], 'literal':literal,
                'reacquisition':calls, 'latency_ms':elapsed,
                'input_utf8_bytes':len('\n'.join(history).encode())})
        policies.append({'policy':'full-history' if limit is None else f'tail-{limit}',
            'by_content_type':{kind:{'n':len(rows), 'literal_presence':mean(x['literal'] for x in rows),
                'task_success':mean(x['success'] for x in rows),
                'failure_mode':'none' if all(x['success'] for x in rows) else 'required_record_missing',
                'reacquisition_calls':sum(x['reacquisition'] for x in rows),
                'retry_calls':0, 'input_utf8_bytes_mean':mean(x['input_utf8_bytes'] for x in rows),
                'local_solver_wall_ms_mean':mean(x['latency_ms'] for x in rows),
                'provider_tokens':None, 'provider_bill':None, 'provider_latency':None}
                for kind, rows in by_kind.items()}})
    return {'schema_version':1, 'evidence_class':'fixture', 'split':split,
            'scorer':'deterministic-content-operations:v1',
            'campaign':'separate-public-lookup' if reacquire else 'bounded-history-no-tools',
            'actual_hermes_compression':'unavailable', 'real_model_calibration':False,
            'production_mutation':False, 'policies':policies}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--split', choices=['train','holdout'], default='train')
    p.add_argument('--reacquire', action='store_true')
    args = p.parse_args()
    print(json.dumps(evaluate(args.split, reacquire=args.reacquire), indent=2))
