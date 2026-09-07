import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import context_runtime as rt
import runtime_http


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length=int(self.headers["Content-Length"]); json.loads(self.rfile.read(length))
        body=json.dumps({"id":"local-1","model":"deterministic","model_revision":"v1",
          "usage":{"prompt_tokens":8,"cached_prompt_tokens":3,"cache_write_tokens":1,"completion_tokens":2},
          "billing":{"amount_usd":.0001,"source":"fixture-price","status":"estimated"},
          "choices":[{"text":"4"}]}).encode()
        self.send_response(200); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass


class HTTPE2E(unittest.TestCase):
    def test_local_http_capture_normalize(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            event, answer=runtime_http.run_request(url=f"http://127.0.0.1:{server.server_port}",run_id="r",task_id="math",policy_id="control",model="deterministic",model_revision="v1",sequence_index=0,input_text="2+2")
            self.assertEqual(answer,"4")
            outcome={"event_id":"out-1","event_kind":"outcome","run_id":"r","task_id":"math","policy_id":"control","occurred_at":event["occurred_at"],"payload":{"success":True,"task_score":1.0,"scorer_id":"exact","scorer_version":"v1","scoring_provenance":"benchmark","harness_revision":"local-http-v1"}}
            c=rt.Collector(runtime_http.OpenAICompatibleHTTPAdapter()); c.capture(event); c.capture(outcome)
            result=rt.normalize([rt.Envelope.parse(x) for x in c.bundle()["events"]])
            receipt=result["l5_receipts"]["runs"][0]
            self.assertEqual(receipt["cached_input_tokens"],3)
            self.assertEqual(receipt["billing_status"],"estimated")
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__": unittest.main()

class StandardHTTPTests(unittest.TestCase):
    def call(self, payload, estimator=None):
        from unittest.mock import patch, MagicMock
        response=MagicMock();response.__enter__.return_value.read.return_value=json.dumps(payload).encode()
        with patch('urllib.request.urlopen',return_value=response):
            return runtime_http.run_request(url='http://localhost',run_id='r',task_id='t',policy_id='p',model='m',model_revision='v1',sequence_index=0,input_text='PRIVATE',pricing_estimator=estimator)
    def standard(self):
        return {'id':'r','model':'m','object':'chat.completion','created':1,
                'usage':{'prompt_tokens':10,'completion_tokens':2,'prompt_tokens_details':{'cached_tokens':4}},
                'choices':[{'message':{'role':'assistant','content':'4'}}],
                'headers':{'authorization':'SECRET'}}
    def test_standard_estimator_cache_redaction_and_unknown_ttft(self):
        seen=[]
        def estimate(usage):
            seen.append(usage);return {'amount_usd':.2,'source':'snapshot@v1','status':'observed'}
        event,answer=self.call(self.standard(),estimate)
        p=event['payload']
        self.assertEqual(answer,'4');self.assertEqual(p['billing_status'],'estimated')
        self.assertEqual(p['cached_input_tokens'],4);self.assertIsNone(p['ttft_ms'])
        self.assertGreaterEqual(p['request_wall_time_ms'],0)
        self.assertFalse(p['provider_metadata']['cache_write_usage_available'])
        self.assertEqual(seen[0]['input_tokens'],10)
        self.assertNotIn('SECRET',str(event));self.assertNotIn('PRIVATE',str(event))
    def test_no_billing_no_estimator(self):
        with self.assertRaisesRegex(rt.TelemetryError,'pricing_estimator'):self.call(self.standard())
    def test_malformed_usage(self):
        for value in (True,'10',-1,None,11.1):
            payload=self.standard();payload['usage']['prompt_tokens']=value
            with self.assertRaises(rt.TelemetryError):self.call(payload)
        payload=self.standard();payload['usage']['prompt_tokens_details']['cached_tokens']=11
        with self.assertRaises(rt.TelemetryError):self.call(payload)
