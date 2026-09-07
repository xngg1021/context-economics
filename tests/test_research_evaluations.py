import unittest
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
from research_evaluations import retention,factorial
from pricing_refresh import check
import hermes_structural_replay as hr

class ResearchTests(unittest.TestCase):
    def test_retention_does_not_confuse_fact_presence_with_outcome(self):
        r=retention();self.assertIsNone(r['task_success'])
        for row in r['rows'][1:]:
            self.assertTrue(all(x['n']==2 and x['critical_fact_presence']==.5 for x in row['by_content_type'].values()))

    def test_factorial_interaction_and_missing_duplicate(self):
        rows=[{'task_id':'a','compression':a,'cache':b,'value':v} for a,b,v in
              [(False,False,10),(True,False,8),(False,True,6),(True,True,5)]]
        r=factorial(rows,['a']);self.assertEqual(r['means']['interaction'],1)
        self.assertEqual(r['means']['compression'],-1.5)
        for bad,expected in [(rows[:3],['a']),(rows+rows[:1],['a']),(rows,['a','b'])]:
            with self.assertRaises(ValueError):factorial(bad,expected)

    def test_pricing_stale_and_untrusted_source(self):
        s=json.loads(Path('pricing/official-20260907-runtime-stage.json').read_text())
        stamp=datetime.fromisoformat(s['retrieved_at'])
        self.assertTrue(check(s,stamp+timedelta(days=8))['stale'])
        self.assertFalse(check(s,stamp)['stale'])
        next(iter(s['models'].values()))['source']='https://evil.example'
        with self.assertRaises(ValueError):check(s,stamp)

    def test_hermes_rejects_unpinned_code_before_execution(self):
        with self.assertRaisesRegex(ValueError,'fingerprint'):hr.replay(__file__)
