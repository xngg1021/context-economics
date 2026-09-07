"""Exact pinned compressor component replay; no surrogate LLM or transport.

Runs head protection, assembly, tool pairing, summary template and state reset.
Full compress()/summary generation and host prompt assembly are NOT certified.
Only literal constants and reachable function/method definitions are compiled;
upstream imports and module initializers are not executed.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from hermes_structural_replay import PIN_PATH, replay as budget_replay

ROOTS = {'_protect_head_size', '_assemble_compressed',
         '_summary_template_sections', '_reset_session_compaction_state',
         '_reset_micro_compact_cursor_state'}


def load(source):
    pin = json.loads(PIN_PATH.read_text())
    raw = Path(source).read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin['source_sha256']:
        raise ValueError('upstream source fingerprint mismatch')
    tree = ast.parse(raw.decode())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name=='ContextCompressor')
    functions = {n.name:n for n in tree.body if isinstance(n, ast.FunctionDef)}
    methods = {}
    for node in cls.body:
        if isinstance(node, ast.FunctionDef):
            methods.setdefault(node.name, []).append(node)
    wanted, selected, selected_functions = set(ROOTS), set(), set()
    while wanted:
        name = wanted.pop()
        if name in methods and name not in selected:
            nodes = methods[name]; selected.add(name)
        elif name in functions and name not in selected_functions:
            nodes = [functions[name]]; selected_functions.add(name)
        else:
            continue
        for node in nodes:
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and child.id in functions and child.id not in selected_functions:
                    wanted.add(child.id)
                if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name) and child.value.id in ('self','cls','ContextCompressor'):
                    if child.attr in methods and child.attr not in selected:
                        wanted.add(child.attr)
    def constants(nodes):
        result = []
        for node in nodes:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                try:
                    ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    # Compose only constants, with no calls or external attribute reads.
                    if any(isinstance(x, (ast.Call, ast.Attribute, ast.Subscript, ast.Lambda,
                                          ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp))
                           or (isinstance(x, ast.Name) and not x.id.isupper())
                           for x in ast.walk(node.value)):
                        continue
                result.append(node)
        return result
    body = constants(cls.body)+[n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in selected]
    module = ast.Module(body=ast.parse('from __future__ import annotations').body+constants(tree.body)+
        [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in selected_functions]+
        [ast.ClassDef(name='ContextCompressor', bases=[], keywords=[], body=body, decorator_list=[])], type_ignores=[])
    # No upstream import is allowed, including lazy imports in reached methods.
    import builtins
    def deny_import(*args, **kwargs):
        raise ImportError('upstream dependency not in component replay')
    namespace = {'__builtins__':{**vars(builtins), '__import__':deny_import}}
    # The compiler's future declaration imports __future__; it contains no upstream code.
    module.body = module.body[1:]
    code = compile(ast.fix_missing_locations(module), str(source), 'exec',
                   flags=__import__('__future__').annotations.compiler_flag)
    exec(code, namespace)
    return namespace, sorted(selected)


def replay(source):
    base = budget_replay(source)
    ns, methods = load(source)
    obj = ns['ContextCompressor']()
    obj.protect_first_n = 2; obj.compression_count = 0; obj._previous_summary = None
    messages = [{'role':'system','content':'Public system fixture.'},
                {'role':'user','content':'Public initial task.'},
                {'role':'assistant','content':'Acknowledged.'},
                {'role':'user','content':'Earlier work.'},
                {'role':'assistant','tool_calls':[{'id':'call-1','function':{'name':'lookup','arguments':'{}'}}]},
                {'role':'tool','tool_call_id':'call-1','content':'Public lookup result.'},
                {'role':'assistant','content':'Latest answer.'}]
    initial = obj._protect_head_size(messages)
    obj.compression_count = 1
    repeated = obj._protect_head_size(messages)
    obj._summary_has_user_turn = True
    compressed = obj._assemble_compressed(messages, 1, 4,
        SimpleNamespace(tail_start=4, summary_indices=set()), 'Public supplied summary fixture.')
    calls = {c['id'] for m in compressed for c in m.get('tool_calls', [])}
    replies = {m['tool_call_id'] for m in compressed if m.get('role')=='tool'}
    template = obj._summary_template_sections(ns['_SECTION_INSTRUCTIONS'][True], 1000, '')
    obj._previous_summary='old fixture';obj._last_summary_error='old failure'
    obj._reset_session_compaction_state();obj._reset_micro_compact_cursor_state()
    return {**base, 'scope':'exact source components; supplied summary fixture, no summary model',
        'loaded_component_methods':methods,
        'initial_protected_head_messages':initial, 'repeat_protected_head_messages':repeated,
        'protected_system_content_preserved':compressed[0]['content'].startswith(messages[0]['content']),
        'message_count_before':len(messages), 'message_count_after':len(compressed),
        'tool_protocol_preserved':calls==replies,
        'upstream_orphan_sanitizer':'not executed; requires agent_runtime_helpers',
        'summary_template_executed': '## Constraints & Preferences' in template,
        'session_state_reset':obj._previous_summary is None and obj._last_summary_error is None
                              and obj._micro_compact_rolling_summary=='',
        'summary_generation':'not executed; fixture supplied at assembly boundary',
        'full_compressor_executed':False, 'memory_profile_injection':None,
        'provider_transport':None, 'production_mutation':False}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True)
    print(json.dumps(replay(p.parse_args().source), indent=2))
