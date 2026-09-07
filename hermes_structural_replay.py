"""Replay selected exact upstream methods, never the full compressor or transport.

Supply agent/context_compressor.py from the pinned upstream commit. SHA-256 is
checked BEFORE parsing/compiling. No upstream imports or module initializers run.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path

PIN_PATH=Path(__file__).with_name('fixtures')/'hermes-structural-pin.json'


def replay(source_path):
    pin=json.loads(PIN_PATH.read_text());raw=Path(source_path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pin['source_sha256']:raise ValueError('upstream source fingerprint mismatch')
    module=ast.parse(raw.decode());cls=next(n for n in module.body if isinstance(n,ast.ClassDef) and n.name=='ContextCompressor')
    selected=[]
    for node in module.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in pin['constants'] for t in node.targets):selected.append(node)
    methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in pin['methods']]
    if len(methods)!=len(pin['methods'])+2:raise ValueError('unexpected method/property shape')
    selected.append(ast.ClassDef(name='Replay',bases=[],keywords=[],body=methods,decorator_list=[]))
    preamble=ast.parse('from __future__ import annotations').body
    compiled=compile(ast.fix_missing_locations(ast.Module(body=preamble+selected,type_ignores=[])),str(source_path),'exec')
    namespace={};exec(compiled,namespace)
    obj=namespace['Replay']();obj._tail_token_budget=None;obj._max_summary_tokens=None
    obj.context_length=200000;obj.tail_mode='lean';obj.threshold_tokens=100000;obj.summary_target_ratio=.2
    lean=obj.tail_token_budget;summary=obj.max_summary_tokens
    obj._tail_token_budget=None;obj.tail_mode='legacy';legacy=obj.tail_token_budget
    messages=[{'role':'user'},{'role':'assistant','tool_calls':[{'id':'call'}]},
              {'role':'tool','tool_call_id':'call'},{'role':'user'}]
    backward=obj._align_boundary_backward(messages,2);forward=obj._align_boundary_forward(messages,2)
    return {'evidence_class':'trace-replay','scope':'exact budget properties and tool-group boundary methods only',
            'upstream_commit':pin['commit'],'upstream_source_sha256':pin['source_sha256'],
            'context_window':200000,'lean_tail_budget':lean,'legacy_tail_budget':legacy,
            'summary_budget':summary,'tool_boundary_backward':backward,'tool_boundary_forward':forward,
            'full_compressor_executed':False,'protected_head_preserved':None,
            'system_prompt_reconstruction':None,'memory_profile_injection':None,'tool_schema_placement':None,
            'session_boundary':None,'provider_transport':None,'prompt_tokens_before':None,
            'prompt_tokens_after':None,'cache_prefix_observation':None,'task_success':None,
            'bill':None,'latency':None,'reacquisition':None,'production_mutation':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True)
    print(json.dumps(replay(p.parse_args().source),indent=2))
