"""Trusted entrypoint: python -I -S /trusted/path/trusted_runtime_bootstrap.py.

Trust this small launcher and the Python/OS installation independently of the
mutable checkout. Never import it from that checkout in a credentialed process.
It does not import repository modules, follows no Git overrides, exports exact
Git blobs into a private fresh directory, and injects only the selected provider
credential through stdin AFTER the child imports validated source. No bytecode
or ignored checkout files are copied. No credential is in argv, child env, logs
or persisted artifacts. This is source integrity, not external evidence trust.
"""
import os
import sys

if not sys.flags.isolated or not sys.flags.no_site:
    print('{"status":"BLOCKED","reason":"python -I -S required"}')
    raise SystemExit(2)

# Capture before importing any non-core library. No repository path is searched
# under the REQUIRED -I -S interpreter flags. The launcher itself is trusted.
_NAMES = ('OPENAI_API_KEY','ANTHROPIC_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','MOONSHOT_API_KEY')
_SECRETS = {name:os.environ.pop(name) for name in _NAMES if name in os.environ}

import argparse
import hashlib
import json
import queue
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

CHILD = r'''
import sys, os, json
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
# There are no provider secrets in this process yet. Only exported Git blobs
# are importable; startup site/customization and checkout pyc are excluded.
import runtime_campaign as campaign
campaign._BOOTSTRAP_SOURCE_IDENTITY = {
    'repository_commit':sys.argv[2], 'repository_tree':sys.argv[3]}
print('CONTEXT_SOURCE_IMPORTED_V1', flush=True)
secret = json.load(sys.stdin)
if set(secret) not in ({'OPENAI_API_KEY'}, {'ANTHROPIC_API_KEY'}):
    raise SystemExit(2)
os.environ.update(secret)
secret.clear()
raise SystemExit(campaign.main(['run','--campaign',sys.argv[4],'--output-root',sys.argv[5]]))
'''


def launch(source, campaign_path, output_root, expected_commit, expected_campaign_digest):
    if not sys.flags.isolated or not sys.flags.no_site:
        raise ValueError('isolated_interpreter_required')
    source = Path(source).resolve()
    campaign_path = Path(campaign_path).resolve()
    output_root = Path(output_root).resolve()
    bundle = json.loads(campaign_path.read_text())
    frozen_fields = dict(bundle)
    claimed = frozen_fields.pop('bundle_digest')
    actual = hashlib.sha256(json.dumps(frozen_fields,sort_keys=True,separators=(',', ':'),
                                      allow_nan=False).encode()).hexdigest()
    # Independent launch pin covers model/provider/prices/tasks/gates, not just
    # source identity. Never derive this expected value from mutable campaign JSON.
    if actual != claimed or actual != expected_campaign_digest:
        raise ValueError('authorized_campaign_digest_mismatch')
    provider = bundle['pins']['provider']
    credential_name = {'openai':'OPENAI_API_KEY','anthropic':'ANTHROPIC_API_KEY'}[provider]
    if not _SECRETS.get(credential_name):
        raise ValueError('credential_unavailable')
    environment = {'PATH':os.defpath, 'LC_ALL':'C', 'GIT_CONFIG_NOSYSTEM':'1',
                   'GIT_CONFIG_GLOBAL':os.devnull, 'GIT_OPTIONAL_LOCKS':'0'}
    if os.name=='nt' and 'SystemRoot' in os.environ:
        environment['SystemRoot'] = os.environ['SystemRoot']
    git = shutil.which('git',path=os.defpath)
    if not git:
        raise ValueError('trusted_git_unavailable')
    def read(*args):
        return subprocess.check_output([git,'-c','core.fsmonitor=false',
            '-c','core.untrackedCache=false',*args],cwd=source,env=environment,stderr=subprocess.DEVNULL)
    if read('status','--porcelain','--untracked-files=normal').strip():
        raise ValueError('dirty_source')
    commit = read('rev-parse','HEAD').decode().strip()
    tree = read('rev-parse',commit+'^{tree}').decode().strip()
    # This pin comes from the trusted launch command/deployment, NOT campaign JSON.
    if (len(expected_commit)!=40 or any(c not in '0123456789abcdef' for c in expected_commit)
        or commit != expected_commit or bundle['pins']['repository_commit'] != commit
        or bundle['pins']['repository_tree'] != tree):
        raise ValueError('source_identity_mismatch')
    with tempfile.TemporaryDirectory(prefix='context-verified-') as td:
        snapshot = Path(td)/'source';snapshot.mkdir(mode=0o700)
        for item in read('ls-tree','-rz',commit).split(b'\0'):
            if not item:continue
            meta, raw_path = item.split(b'\t',1)
            mode, kind, oid = meta.decode().split()
            relative = Path(raw_path.decode())
            if (kind!='blob' or mode not in ('100644','100755') or relative.is_absolute()
                or '..' in relative.parts or relative.suffix in ('.pyc','.pyo')
                or '__pycache__' in relative.parts):
                raise ValueError('unsupported_source_entry')
            content = read('cat-file','blob',oid)
            if hashlib.sha1(b'blob '+str(len(content)).encode()+b'\0'+content).hexdigest()!=oid:
                raise ValueError('source_blob_mismatch')
            target=snapshot/relative;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(content);target.chmod(0o444)
        # Snapshot is based on one exact commit; later checkout mutation cannot
        # change the child's code. Every directory is private to this launcher.
        # Pin the bundle bytes too, eliminating a file-swap between checks/run.
        frozen = Path(td)/'campaign.json';frozen.write_text(json.dumps(bundle));frozen.chmod(0o400)
        with subprocess.Popen([sys.executable,'-I','-S','-B','-c',CHILD,str(snapshot),
            commit,tree,str(frozen),str(output_root)],cwd=snapshot,env=environment,
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) as child:
            ready=queue.Queue(maxsize=1)
            threading.Thread(target=lambda:ready.put(child.stdout.readline(256)),daemon=True).start()
            try:
                if ready.get(timeout=30) != 'CONTEXT_SOURCE_IMPORTED_V1\n':
                    raise ValueError('validated_import_not_ready')
                # Do not queue the key in the pipe while modules are importing.
                stdout,_ = child.communicate(json.dumps({credential_name:_SECRETS[credential_name]}),timeout=3000)
                returncode=child.returncode
            except Exception:
                child.kill();child.communicate()
                raise ValueError('isolated_child_failed') from None
        _SECRETS.clear()
        # Never forward native stdout/stderr from a failed import or execution.
        if returncode:
            return {'status':'BLOCKED','operation':'run','evidence_upgraded':False}
        parsed=json.loads(stdout)
        if parsed != {'status':'complete','operation':'run','production_mutation':False}:
            raise ValueError('unexpected_child_result')
        return parsed


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--campaign',required=True)
    p.add_argument('--expected-commit',required=True,help='independently reviewed source SHA; never derive from campaign')
    p.add_argument('--expected-campaign-digest',required=True,help='digest recorded in trusted campaign review/launch config')
    p.add_argument('--output-root',default='artifacts')
    args=p.parse_args()
    try:
        result=launch(args.source,args.campaign,args.output_root,args.expected_commit,args.expected_campaign_digest)
    except Exception:
        result={'status':'BLOCKED','operation':'run','evidence_upgraded':False}
    finally:
        _SECRETS.clear()
    print(json.dumps(result))
    return 0 if result['status']=='complete' else 2


if __name__=='__main__':
    raise SystemExit(main())
