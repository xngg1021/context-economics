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
