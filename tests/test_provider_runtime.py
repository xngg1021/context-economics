import copy
import json
import tempfile
import unittest
import urllib.error
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch, MagicMock

import context_runtime as rt
import experiment_runner as er
import provider_runtime as pr

REV = 'gpt-4.1-mini-2025-04-14'

def response():
    return {'id': 'PRIVATE-IDENTITY', 'model': REV,
            'usage': {'prompt_tokens': 10, 'completion_tokens': 1,
                      'prompt_tokens_details': {'cached_tokens': 4}},
            'choices': [{'finish_reason': 'stop', 'message': {'content': '4'}}]}

def price(provider='openai', rev=REV):
    return pr.Price(provider, rev, .4, 1.6, .1, 'sha256:'+'a'*64)

class ProviderTests(unittest.TestCase):
    def test_native_redaction_and_unknown(self):
        p=response();p['authorization']={'secret':['PRIVATE']};p['prompt']='PRIVATE'
        u,answer,done=pr.native_response('openai',p,REV)
        self.assertEqual(answer,'4');self.assertTrue(done)
        self.assertIsNone(u['cache_write_tokens'])
        self.assertNotIn('PRIVATE',json.dumps(u))
        del p['usage']['prompt_tokens_details']
        u,_,_=pr.native_response('openai',p,REV)
        self.assertIsNone(u['cached_input_tokens'])
        with self.assertRaises(pr.ProviderError):price().estimate(u)

    def test_malformed_semantics(self):
        for mutate in [lambda p:p.update(model='alias'),lambda p:p.update(billing={'status':'observed'}),
                       lambda p:p['usage'].update(cached_prompt_tokens=3),
                       lambda p:p.update(service_tier='priority'),
                       lambda p:p['choices'][0]['message'].update(tool_calls=[{}])]:
            p=response();mutate(p)
            with self.assertRaises(pr.ProviderError):pr.native_response('openai',p,REV)
        for v in [True, '3', -1, float('inf'), None]:
            p=response();p['usage']['prompt_tokens']=v
            with self.assertRaises(ValueError):pr.native_response('openai',p,REV)

    def test_anthropic_disjoint_cache_counters(self):
        p={'id':'id','model':'claude-sonnet-4-20250514','usage':{'input_tokens':10,'output_tokens':2,
           'cache_read_input_tokens':20,'cache_creation_input_tokens':3},
           'content':[{'type':'text','text':'4'}],'stop_reason':'end_turn'}
        u,_,_=pr.native_response('anthropic',p,p['model'])
        self.assertEqual(u['input_tokens'],33)
        self.assertEqual(u['cached_input_tokens'],20)
        with self.assertRaises(pr.ProviderError):price('anthropic',p['model']).estimate(u)
        del p['usage']['cache_creation_input_tokens']
        u,_,_=pr.native_response('anthropic',p,p['model']);self.assertIsNone(u['cache_write_tokens'])
        p['content']=[{'type':'tool_use'}]
        with self.assertRaises(pr.ProviderError):pr.native_response('anthropic',p,p['model'])

    def test_price_rejects_invalid_and_preserves_bill_meaning(self):
        for n in [-1,float('inf'),True]:
            with self.assertRaises(ValueError):pr.Price('openai',REV,n,1,1,'sha256:'+'a'*64)
        u,_,_=pr.native_response('openai',response(),REV)
        self.assertAlmostEqual(price().estimate(u),4.4/1e6)

    def test_transport_never_exposes_errors_or_follows_redirect(self):
        with self.assertRaises(pr.ProviderError):pr.NoRedirect().redirect_request(None,None,302,'',{},'https://evil.example')
        with patch.dict('os.environ',{},clear=True),self.assertRaisesRegex(pr.ProviderError,'credential_unavailable'):
            pr.send('openai',{})
        for error in [urllib.error.HTTPError('SECRET',429,'PRIVATE',{},None),OSError('SECRET')]:
            with patch.dict('os.environ',{'OPENAI_API_KEY':'SECRET'}),patch('urllib.request.OpenerDirector.open',side_effect=error):
                with self.assertRaises(pr.ProviderError) as caught:pr.send('openai',{})
                self.assertNotIn('SECRET',str(caught.exception));self.assertNotIn('PRIVATE',str(caught.exception))

    def test_full_runner_fixture_estimated_and_no_promotion(self):
        m=replace(er.local_manifest('provider-fixture','a'*40),provider='openai',model=REV,
                  model_revision=REV,declared_evidence_class='runtime-A/B')
        tasks=[{'task_id':t,'input':'PRIVATE','history':['OLD'],'expected_answer':'4'} for t in m.expected_task_ids]
        with tempfile.TemporaryDirectory() as td,patch.object(pr,'send',return_value=response()):
            ex=pr.ProviderExecutor('openai',REV,price())
            path=er.run_experiment(m,tasks,{'control':ex,'treatment':ex},td,allow_estimated=True,target='runtime-A/B')
            content=''.join(p.read_text() for p in path.iterdir())
            self.assertNotIn('PRIVATE',content)
            data=json.loads((path/'normalized.json').read_text())
            self.assertIsNone(data['runs'][0]['requests'][0]['usage_observations']['cache_write_tokens'])
            self.assertEqual(data['l5_receipts']['runs'][0]['billing_status'],'estimated')
            self.assertFalse(json.loads((path/'acceptance.json').read_text())['candidate_for_promotion'])

    def test_observation_conflicts_fail(self):
        from tests.test_context_runtime import request,outcome
        r=request();r['payload']['usage_observations']={
            'input_tokens':999,'output_tokens':3,'cached_input_tokens':4,
            'cache_write_tokens':None,'service_tier':None,'response_id':None}
        with self.assertRaises(rt.TelemetryError):rt.normalize([rt.Envelope.parse(x) for x in (r,outcome())])

    def test_alias_and_price_mismatch_fail_before_network(self):
        for rev in ['latest','gpt-4.1-mini']:
            with self.assertRaises(pr.ProviderError):pr.ProviderExecutor('openai',rev,price())
        with self.assertRaises(pr.ProviderError):pr.ProviderExecutor('anthropic',REV,price())
