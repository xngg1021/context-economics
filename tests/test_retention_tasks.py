import unittest
import retention_tasks as r


class RetentionTaskTests(unittest.TestCase):
    def test_solver_requires_evidence_and_computes_answers(self):
        for split in ('train', 'holdout'):
            for task in r.tasks(split):
                self.assertEqual(r.solve(task['history'], task['query']), task['expected'])
                self.assertIsNone(r.solve([], task['query']))
                self.assertIsNone(r.solve(task['history']*2, task['query']))
        task = next(t for t in r.tasks() if t['kind']=='constraint')
        self.assertEqual(r.solve(task['history'], {**task['query'], 'requested':0}), 'accept')
        task = next(t for t in r.tasks() if t['kind']=='tool_protocol')
        self.assertEqual(r.solve(task['history'], {**task['query'], 'reply_to':'wrong'}), 'reject')

    def test_content_breakdown_and_separate_reacquisition(self):
        bounded = r.evaluate(); lookup = r.evaluate(reacquire=True)
        for report in (bounded, lookup):
            self.assertEqual(report['evidence_class'], 'fixture')
            for policy in report['policies']:
                self.assertEqual(set(policy['by_content_type']), set(r.KINDS))
                for row in policy['by_content_type'].values():
                    self.assertEqual(row['n'], 2)
                    self.assertIsNone(row['provider_bill'])
        for row in bounded['policies'][2]['by_content_type'].values():
            self.assertEqual(row['task_success'], .5)
        for row in lookup['policies'][2]['by_content_type'].values():
            self.assertEqual(row['task_success'], 1)
            self.assertEqual(row['reacquisition_calls'], 1)
