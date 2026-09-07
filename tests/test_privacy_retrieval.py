import unittest
import context_runtime as rt
import task_economics as te
from tests.test_context_runtime import request, outcome
from tests.test_cost_ledger import tool

class PrivacyRetrievalTests(unittest.TestCase):
    def test_recursive_forbidden_fields(self):
        for key in ('Authorization','AUTHORIZATION','authorization_header','api_key','apikey','x-api-key','cookie','set-cookie','access_token','refresh_token','account_id','raw_prompt','raw_completion','prompt','completion','Proxy-Authorization','password','client_secret','session_token','session-id','id_token','token','credentials','private_key','aws_secret_access_key'):
            for wrap in (lambda x:x,lambda x:{'headers':x},lambda x:{'request':[x]},lambda x:{'a':[{'b':(x,)}]}):
                with self.subTest(key=key,wrap=wrap):
                    r=request();r['payload']['provider_metadata']=wrap({key:'SECRET'})
                    c=rt.Collector(rt.CanonicalAdapter())
                    with self.assertRaises(rt.TelemetryError): c.capture(r)
                    self.assertNotIn('SECRET',str(c.bundle()))
    def test_safe_metadata_and_no_mutable_alias(self):
        metadata={'route':'local','region':'us','response_id':'1','service_tier':'default','cache_hint':{'type':'routing'}}
        r=request();r['payload']['provider_metadata']=metadata
        c=rt.Collector(rt.CanonicalAdapter());c.capture(r)
        metadata['authorization']='SECRET'
        self.assertNotIn('SECRET',str(c.bundle()))
        b=c.bundle();b['events'][0]['payload']['provider_metadata']['authorization']='SECRET'
        self.assertNotIn('SECRET',str(c.bundle()))
    def test_depth_size_nodes_and_json_values(self):
        deep={}
        for _ in range(20):deep={'a':deep}
        for metadata in (deep,{'a':'x'*65537},{'a':[0]*4097},{'a':float('nan')},{'a':object()}):
            r=request();r['payload']['provider_metadata']=metadata
            with self.assertRaises(rt.TelemetryError):rt.Envelope.parse(r)
    def test_retrieval_roundtrip(self):
        for category in ('filesystem','search','database','web'):
            r=rt.normalize([rt.Envelope.parse(x) for x in (request(),tool(True,category=category),outcome())])['l5_receipts']['runs'][0]
            self.assertEqual(te.RunReceipt.from_mapping(r).retrieval_calls,1)
        for row in (tool(True,category='typo'),tool(True,category='compute')):
            row['payload']['is_retrieval']=False
            with self.assertRaises(rt.TelemetryError):rt.normalize([rt.Envelope.parse(x) for x in (request(),row,outcome())])
    def test_duplicate_event_normalize_fails(self):
        with self.assertRaises(rt.TelemetryError):rt.normalize([rt.Envelope.parse(x) for x in (request(),request(),outcome())])
