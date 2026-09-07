import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
import experiment_runner as er
import experiment_analysis as ea
import runtime_experiment as rx

class RunnerTests(unittest.TestCase):
    def test_full_local_http_ab_ba_and_replay(self):
        for assignment in ('counterbalanced','paired-fixed'):
            with self.subTest(assignment=assignment), tempfile.TemporaryDirectory() as td, er.local_http_server() as url:
                m=er.local_manifest('test','a'*40,assignment)
                tasks=[{'task_id':t,'input':'2+2','expected_answer':'4'} for t in m.expected_task_ids]
                ex=er.LocalHTTPExecutor(url)
                p=er.run_experiment(m,tasks,{'control':ex,'treatment':ex},td)
                self.assertEqual(len(list(p.iterdir())),10)
                schedule=json.loads((p/'schedule.json').read_text())['tasks']
                self.assertEqual(schedule[0]['order'],['control','treatment'])
                self.assertEqual(schedule[1]['order'],['treatment','control'] if assignment=='counterbalanced' else ['control','treatment'])
                receipts=rx.load_receipt_records(p/'l5-receipts.json')
                self.assertEqual({x.receipt.run_id for x in receipts},{r['run_id'] for t in schedule for r in t['runs']})
                events=rx.load_experiment_events(p/'l6-events.json')
                self.assertTrue(rx.build_joint_report(rx.load_manifest(p/'manifest.json'),receipts,events,require_complete=True)['structurally_complete'])
                a=json.loads((p/'acceptance.json').read_text())
                b=ea.acceptance_gate([r.receipt for r in receipts],{},'control','treatment',ea.GateConfig(),manifest=m,experiment_events=events,evidence_origin='loopback')
                self.assertEqual(a,b)
                self.assertTrue(a['performance_candidate']);self.assertFalse(a['candidate_for_promotion'])
                self.assertTrue(all(r.receipt.ttft_ms is None for r in receipts))
                with self.assertRaises(er.RunnerError):er.run_experiment(m,tasks,{'control':ex,'treatment':ex},td)
    def test_bad_tasks_and_local_evidence_upgrade_fail_before_execution(self):
        m=er.local_manifest('test','a'*40)
        ex=er.LocalHTTPExecutor('http://127.0.0.1:1')
        tasks=[{'task_id':t,'input':'2+2','expected_answer':'4'} for t in m.expected_task_ids]
        with tempfile.TemporaryDirectory() as td:
            for bad in (replace(m,declared_evidence_class='runtime-A/B'),replace(m,experiment_id='../escape')):
                with self.assertRaises(er.RunnerError):er.run_experiment(bad,tasks,{'control':ex,'treatment':ex},td)
            with self.assertRaises(er.RunnerError):er.run_experiment(m,tasks[:1],{'control':ex,'treatment':ex},td)

    def test_atomic_publish_failure_leaves_no_finished_output_and_retry_works(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as td:
            output=Path(td)/'atomic'
            original=Path.write_text
            count=0
            def fail_second(path,*args,**kwargs):
                nonlocal count
                count+=1
                if count==2:raise OSError('simulated disk full')
                return original(path,*args,**kwargs)
            with patch.object(Path,'write_text',fail_second), self.assertRaises(OSError):
                er.publish_artifacts(output,{'one.json':'{}','two.json':'{}'})
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(td).iterdir()),[])
            er.publish_artifacts(output,{'one.json':'{}','two.json':'{}'})
            self.assertEqual(len(list(output.iterdir())),2)

    def test_noncanonical_partial_payload_never_reaches_artifacts(self):
        from tests.test_context_runtime import request
        for raises in (False, True):
            class Unsafe:
                evidence_origin='loopback'
                def execute(self, task, *, run_id, policy_id, manifest):
                    event=request()
                    event.update(run_id=run_id,task_id=task['task_id'],policy_id=policy_id)
                    yield event
                    event={**event,'event_id':event['event_id']+'-unsafe',
                           'payload':{'response_text':'PRIVATE-ANSWER'}}
                    yield event
                    if raises:raise RuntimeError('PRIVATE-ERROR')
            m=er.local_manifest('unsafe','a'*40)
            with tempfile.TemporaryDirectory() as td:
                with self.assertRaises(er.RunnerError):
                    er.run_experiment(m,[{'task_id':t} for t in m.expected_task_ids],
                                      {'control':Unsafe(),'treatment':Unsafe()},td)
                p=Path(td)/'unsafe'
                self.assertEqual(len(json.loads((p/'raw-telemetry.json').read_text())['events']),1)
                self.assertTrue(all('PRIVATE-' not in f.read_text() for f in p.iterdir()))
