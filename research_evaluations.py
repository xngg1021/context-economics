"""Descriptive structural retention and exact complete four-cell factorial math."""
import argparse
import json
import math
from collections import defaultdict
from statistics import mean
import context_runtime as rt
from runtime_campaign import task_set, KINDS


def retention():
    tasks=task_set('train',24)
    rows=[]
    for limit in (None,4,8):
        grouped=defaultdict(list)
        for task in tasks:
            kept=task['history'] if limit is None else task['history'][-limit:]
            # Literal fact presence only, never a task-outcome or semantic-recall claim.
            grouped[task['content_type']].append(task['expected_answer'] in '\n'.join(kept))
        rows.append({'policy':'full-history' if limit is None else f'tail-{limit}-messages',
                     'by_content_type':{kind:{'n':len(v),'critical_fact_presence':mean(v)} for kind,v in grouped.items()}})
    return {'evidence_class':'simulation','scope':'literal critical-fact presence in bounded history',
            'task_success':None,'bill':None,'latency':None,'reacquisition':None,
            'semantic_retention':None,'existing_compressor':'not evaluated', 'rows':rows}


def factorial(rows, expected_task_ids):
    """Within-task difference-of-differences; incomplete cells fail, no imputation.

    value is one explicitly chosen scalar metric with a common unit. Cache factor
    must be declared proxy or controlled by the caller; this math proves neither.
    """
    expected=list(expected_task_ids)
    if not expected or len(expected)!=len(set(expected)):raise ValueError('invalid expected tasks')
    cells=defaultdict(dict)
    for row in rows:
        task=row['task_id']
        if task not in expected:raise ValueError('unexpected task')
        a,b=row['compression'],row['cache']
        if type(a) is not bool or type(b) is not bool:raise ValueError('factors require booleans')
        value=rt._num(row['value'],'value')
        if (a,b) in cells[task]:raise ValueError('duplicate cell')
        cells[task][a,b]=value
    if set(cells)!=set(expected) or any(len(c)!=4 for c in cells.values()):raise ValueError('incomplete factorial')
    effects=[]
    for task in expected:
        c=cells[task];a,b,c0,d=c[False,False],c[True,False],c[False,True],c[True,True]
        effects.append({'task_id':task,'compression':((b-a)+(d-c0))/2,
                        'cache':((c0-a)+(d-b))/2,'interaction':d-c0-b+a})
    return {'descriptive_only':True,'n':len(expected),'effects':effects,
            'means':{key:mean(r[key] for r in effects) for key in ('compression','cache','interaction')},
            'causal_claim':'not inferred','production_mutation':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--retention',action='store_true',required=True)
    parser.parse_args();print(json.dumps(retention(),indent=2))
