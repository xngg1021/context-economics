import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import experiment_runner as er
import runtime_campaign as rc

class CampaignTests(unittest.TestCase):
    def test_disjoint_split_and_all_content_types(self):
        train=rc.task_set('train',24);holdout=rc.task_set('holdout',24)
        self.assertFalse({t['task_id'] for t in train}&{t['task_id'] for t in holdout})
        self.assertEqual({t['content_type'] for t in holdout},set(rc.KINDS))
        self.assertEqual(sum(t['expected_answer'] in '\n'.join(t['history'][-4:]) for t in holdout),12)

    def test_aborted_campaign_is_immutable_and_redacted(self):
        class Broken:
            evidence_origin='loopback'
            def execute(self,*args,**kw):raise ValueError('SECRET PRIVATE ANSWER')
        m=er.local_manifest('failed','a'*40)
        tasks=[{'task_id':t} for t in m.expected_task_ids]
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(er.RunnerError):er.run_experiment(m,tasks,{'control':Broken(),'treatment':Broken()},td)
            p=Path(td)/'failed';text=''.join(f.read_text() for f in p.iterdir())
            self.assertNotIn('SECRET',text)
            f=json.loads((p/'failure.json').read_text())
            self.assertEqual(f['expected_task_count'],2);self.assertFalse(f['performance_candidate'])
            self.assertFalse((p/'paired-statistics.json').exists())
            with self.assertRaises(er.RunnerError):er.run_experiment(m,tasks,{'control':Broken(),'treatment':Broken()},td)

    def test_artifact_collision_rejected_before_execution(self):
        m=er.local_manifest('failed','a'*40)
        with self.assertRaises(er.RunnerError):
            er.run_experiment(m,[],{},'.',supplemental_artifacts={'manifest.json':{}})

    def test_fingerprint_mutation_fails(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'campaign.json';p.write_text(json.dumps({'bundle_digest':'wrong','pins':{}}))
            with self.assertRaisesRegex(ValueError,'fingerprint'):rc.run(p,td)
