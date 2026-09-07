import importlib.util
import json
import marshal
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

LAUNCHER=Path(__file__).resolve().parents[1]/'trusted_runtime_bootstrap.py'


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'source';self.source.mkdir()
        self.marker=self.root/'must-not-exist'
        self.environment={**os.environ,'OPENAI_API_KEY':'FIXTURE-PRIVATE',
                          'PYTHONPATH':str(self.source),'GIT_DIR':str(self.root/'wrong')}
        self.git('init','-q')
        (self.source/'.gitignore').write_text('__pycache__/\n*.pyc\n')
        (self.source/'provider_runtime.py').write_text(
            "import os\nassert not os.environ.get('OPENAI_API_KEY'), 'secret delivered before import'\n"
            "def check(): return bool(os.environ.get('OPENAI_API_KEY'))\n")
        (self.source/'runtime_campaign.py').write_text(
            "import json\nimport provider_runtime\n"
            "def main(args):\n"
            " assert provider_runtime.check()\n"
            " assert _BOOTSTRAP_SOURCE_IDENTITY['repository_commit']\n"
            " print(json.dumps({'status':'complete','operation':'run','production_mutation':False}))\n"
            " return 0\n")
        self.git('add','.')
        self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture')
        self.campaign=self.root/'campaign.json'
        self.expected_commit=self.git('rev-parse','HEAD')
        self.campaign.write_text(json.dumps({'pins':{'provider':'openai',
            'repository_commit':self.git('rev-parse','HEAD'),
            'repository_tree':self.git('rev-parse','HEAD^{tree}')}}))

    def git(self,*args):
        return subprocess.check_output(['git',*args],cwd=self.source,text=True,stderr=subprocess.DEVNULL).strip()

    def launch(self, isolated=True):
        return subprocess.run([sys.executable,*(['-I','-S'] if isolated else []),str(LAUNCHER),
            '--source',str(self.source),'--campaign',str(self.campaign),'--output-root',str(self.root/'out'),'--expected-commit',self.expected_commit],
            env=self.environment,cwd=self.source,capture_output=True,text=True)

    def test_ignored_forged_pyc_is_not_loaded_and_secret_arrives_after_import(self):
        source=self.source/'provider_runtime.py'
        cache=Path(importlib.util.cache_from_source(str(source)));cache.parent.mkdir()
        poisoned=f"from pathlib import Path\nPath({str(self.marker)!r}).write_text('POISON')\n"
        header=importlib.util.MAGIC_NUMBER+struct.pack('<III',0,int(source.stat().st_mtime),source.stat().st_size)
        cache.write_bytes(header+marshal.dumps(compile(poisoned,str(source),'exec')))
        result=self.launch()
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertFalse(self.marker.exists())
        self.assertNotIn('FIXTURE-PRIVATE',result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'],'complete')

    def test_dirty_provider_rejected_before_import(self):
        (self.source/'provider_runtime.py').write_text(
            f"from pathlib import Path\nPath({str(self.marker)!r}).write_text('POISON')\n")
        result=self.launch()
        self.assertEqual(result.returncode,2)
        self.assertFalse(self.marker.exists())
        self.assertNotIn('FIXTURE-PRIVATE',result.stdout+result.stderr)

    def test_nonisolated_start_is_rejected_before_local_import(self):
        (self.source/'argparse.py').write_text(
            f"from pathlib import Path\nPath({str(self.marker)!r}).write_text('POISON')\n")
        result=self.launch(isolated=False)
        self.assertEqual(result.returncode,2)
        self.assertFalse(self.marker.exists())

    def test_campaign_cannot_authorize_an_unreviewed_source_commit(self):
        (self.source/'extra').write_text('new commit')
        self.git('add','.')
        self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','unreviewed')
        bundle=json.loads(self.campaign.read_text())
        bundle['pins'].update(repository_commit=self.git('rev-parse','HEAD'),repository_tree=self.git('rev-parse','HEAD^{tree}'))
        self.campaign.write_text(json.dumps(bundle))
        self.assertEqual(self.launch().returncode,2)
