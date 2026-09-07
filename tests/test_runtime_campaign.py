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

    def test_prepare_and_full_frozen_campaign_fixture(self):
        import provider_runtime as pr
        from tests.test_provider_runtime import response, REV
        source={'repository_commit':'a'*40,'repository_tree':'b'*40}
        with tempfile.TemporaryDirectory() as td,patch.object(rc,'identity',return_value=source):
            bundle=rc.prepare('openai',REV,'pricing/official-20260907-runtime-stage.json',
                              Path(td)/'stage','complete','smoke',2)
            with patch.dict('os.environ',{'OPENAI_API_KEY':'FIXTURE'}),patch.object(pr,'send',return_value=response()),patch.object(pr,'verify_model',return_value={'available':True}):
                output=rc.run(Path(td)/'stage/campaign.json',Path(td)/'runs')
            index=json.loads((output/'fingerprints.json').read_text())
            import hashlib
            for name,value in index['files'].items():
                self.assertEqual(hashlib.sha256((output/name).read_bytes()).hexdigest(),value)
            self.assertTrue((output/'capabilities.json').exists())

    def test_rehashed_bundle_cannot_relabel_arbitrary_rates(self):
        import provider_runtime as pr
        from tests.test_provider_runtime import REV
        source={'repository_commit':'a'*40,'repository_tree':'b'*40}
        with tempfile.TemporaryDirectory() as td,patch.object(rc,'identity',return_value=source):
            bundle=rc.prepare('openai',REV,'pricing/official-20260907-runtime-stage.json',
                              Path(td)/'stage','rates','smoke',2)
            bundle.pop('bundle_digest');bundle['price']['input']=0
            bundle['bundle_digest']=pr.digest(bundle)
            p=Path(td)/'tampered.json';p.write_text(json.dumps(bundle))
            with patch.dict('os.environ',{'OPENAI_API_KEY':'FIXTURE'}),patch.object(pr,'send') as send:
                with self.assertRaisesRegex(ValueError,'price does not match'):rc.run(p,Path(td)/'runs')
                send.assert_not_called()

    def test_partial_request_survives_later_executor_failure(self):
        import provider_runtime as pr
        from tests.test_context_runtime import request
        class Partial:
            evidence_origin='loopback'
            def execute(self, task, *, run_id, policy_id, manifest):
                event=request()
                event.update(run_id=run_id, task_id=task['task_id'], policy_id=policy_id)
                yield event
                raise pr.ProviderError('scorer_failure')
        m=er.local_manifest('partial','a'*40)
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(er.RunnerError):
                er.run_experiment(m,[{'task_id':t} for t in m.expected_task_ids],
                                  {'control':Partial(),'treatment':Partial()},td)
            p=Path(td)/'partial'
            raw=json.loads((p/'raw-telemetry.json').read_text())
            self.assertEqual(len(raw['events']),1)
            failure=json.loads((p/'failure.json').read_text())
            self.assertEqual(failure['failure_class'],'scorer_failure')
            self.assertEqual(failure['success_denominator_attempted'],1)
            self.assertEqual(failure['successful_run_count'],0)
            self.assertEqual(failure['unattempted_run_count'],3)
            self.assertTrue((p/'fingerprints.json').exists())

    def test_holdout_minimum_24(self):
        source={'repository_commit':'a'*40,'repository_tree':'b'*40}
        with tempfile.TemporaryDirectory() as td, patch.object(rc,'identity',return_value=source):
            with self.assertRaisesRegex(ValueError,'24 pairs'):
                rc.prepare('openai','gpt-4.1-mini-2025-04-14','pricing/official-20260907-runtime-stage.json',td,'too-small','holdout',20)

    def test_source_git_never_inherits_provider_credentials(self):
        import os
        keys=['OPENAI_API_KEY','ANTHROPIC_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','MOONSHOT_API_KEY']
        with patch.dict(os.environ,{**{k:'TEST-SECRET' for k in keys},'GIT_CONFIG_COUNT':'1'}):
            with patch.object(rc.subprocess,'check_output',side_effect=['','a'*40,'b'*40]) as git:
                self.assertEqual(rc.identity()['repository_commit'],'a'*40)
                for call in git.call_args_list:
                    env=call.kwargs['env']
                    self.assertTrue(all(k not in env for k in keys))
                    self.assertNotIn('GIT_CONFIG_COUNT',env)
                    self.assertIn('core.fsmonitor=false',call.args[0])
                    self.assertEqual(env['GIT_CONFIG_NOSYSTEM'],'1')
                    self.assertEqual(env['GIT_CONFIG_GLOBAL'],os.devnull)
            self.assertTrue(all(os.environ[k]=='TEST-SECRET' for k in keys))

    def test_finalization_failure_retains_collected_evidence(self):
        m=er.local_manifest('finalize-failure','a'*40)
        tasks=[{'task_id':t,'input':'2+2','expected_answer':'4'} for t in m.expected_task_ids]
        with tempfile.TemporaryDirectory() as td, er.local_http_server() as url:
            executor=er.LocalHTTPExecutor(url)
            with patch.object(er.rt,'normalize',side_effect=ValueError('PRIVATE')):
                with self.assertRaises(er.RunnerError):
                    er.run_experiment(m,tasks,{'control':executor,'treatment':executor},td)
            p=Path(td)/m.experiment_id
            self.assertTrue(json.loads((p/'raw-telemetry.json').read_text())['events'])
            self.assertEqual(json.loads((p/'failure.json').read_text())['phase'],'normalization_and_join')
            self.assertFalse((p/'acceptance.json').exists())
            self.assertNotIn('PRIVATE',''.join(f.read_text() for f in p.iterdir()))
