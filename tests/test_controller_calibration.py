import unittest

import controller_calibration as cc


BUDGET={"history_units":100,"retrieval_units":100,"memory_units":100,"tools_units":100,"repo_map_units":100,"prefetch_units":100,"compression_retained_ratio":.5}
MIN={"history_units":10,"retrieval_units":10,"memory_units":10,"tools_units":10,"repo_map_units":10,"prefetch_units":0,"compression_retained_ratio":.1}
MAX={"history_units":200,"retrieval_units":200,"memory_units":200,"tools_units":200,"repo_map_units":200,"prefetch_units":200,"compression_retained_ratio":1.0}
OBS={"miss_rate":.3,"hard_miss_rate":.1,"reacquisition_cost_units_per_task":2,"dependency_depth":4,"cache_hit_share":.5,"context_pressure":.5,"ttft_ms":1000,"prefetch_pollution_rate":.1,"interference_rate":.01}

def row(task, split):
    target=dict(BUDGET); target["retrieval_units"]=110
    return {"task_id":task,"split":split,"current":BUDGET,"bounds":{"minimum":MIN,"maximum":MAX},"observation":OBS,"target":target}


class CalibrationTests(unittest.TestCase):
    def test_insufficient_evidence(self):
        out=cc.calibrate([row("a","train"),row("b","holdout")],{"base_step_fraction":[.05],"max_step_fraction":[.2],"deadband":[.1]})
        self.assertEqual(out["status"],"insufficient evidence")

    def test_disjoint_and_heldout(self):
        rows=[row(x,"train") for x in "abc"]+[row(x,"holdout") for x in "de"]
        out=cc.calibrate(rows,{"base_step_fraction":[.05,.1],"max_step_fraction":[.1,.2],"deadband":[0,.1]})
        self.assertEqual(out["status"],"shadow-candidate"); self.assertFalse(out["auto_enable"])
        self.assertIn("holdout_loss",out)

    def test_overlap_fails(self):
        rows=[row("a","train"),row("a","holdout")]
        with self.assertRaises(cc.CalibrationError): cc.calibrate(rows,{"base_step_fraction":[.1],"max_step_fraction":[.2],"deadband":[.1]},min_train=1,min_holdout=1)


if __name__ == "__main__": unittest.main()

class GridValidationTests(unittest.TestCase):
    def test_invalid_grid_even_when_insufficient_evidence(self):
        for key in ('base_step_fraction','max_step_fraction','deadband'):
            for value in (-.5,2,float('nan'),float('inf'),True,'0.1'):
                grid={'base_step_fraction':[.05],'max_step_fraction':[.2],'deadband':[.1]};grid[key]=[value]
                with self.subTest(key=key,value=value),self.assertRaises(cc.CalibrationError):cc.calibrate([],grid)
        with self.assertRaises(cc.CalibrationError):cc.calibrate([],{'base_step_fraction':[.5],'max_step_fraction':[.2],'deadband':[.1]})
    def test_selected_policy_reparses(self):
        import adaptive_control as ac
        rows=[row(x,'train') for x in 'abc']+[row(x,'holdout') for x in 'de']
        result=cc.calibrate(rows,{'base_step_fraction':[0,.1],'max_step_fraction':[.2,1],'deadband':[0,1]})
        ac.ControllerPolicy.from_mapping(result['selected'])
