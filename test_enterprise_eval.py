import copy
import json
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch

from enterprise_eval import Environment, grade, make_task, migration, paired_root_bootstrap, reference_solve, run_live, task_manifest


class ContractTests(unittest.TestCase):
    def test_reference_and_noop_all_variants(self):
        for root in range(12):
            for depth in (4, 8, 16):
                for fault in (False, True):
                    task = make_task(root, depth, fault)
                    env = Environment(task)
                    self.assertFalse(grade(task, env.snapshot())["success"])
                    reference_solve(env)
                    self.assertTrue(grade(task, env.snapshot())["success"])
                    self.assertEqual(env.fault_triggered, fault)

    def test_dependency_order_enforced(self):
        task = make_task(0, 4, False)
        env = Environment(task)
        self.assertIn("error", env.call("complete", {"node": task.goal, "request_id": "1"}))
        self.assertEqual(env.effects, [])

    def test_lost_ack_idempotency_and_duplicate_detection(self):
        task = make_task(0, 2, True)
        first = task.nodes[task.goal][0]
        env = Environment(task)
        args = {"node": first, "request_id": "1"}
        self.assertEqual(env.call("complete", args)["error"], "timeout")
        self.assertTrue(env.call("complete", args)["replayed"])
        self.assertEqual(len(env.effects), 1)
        env.call("complete", {"node": first, "request_id": "2"})
        reference_solve(env)
        self.assertFalse(grade(task, env.snapshot())["success"])

    def test_request_key_cannot_change_operation(self):
        task = make_task(0, 2, False)
        env = Environment(task)
        first = task.nodes[task.goal][0]
        env.call("complete", {"node": first, "request_id": "x"})
        self.assertIn("error", env.call("complete", {"node": task.goal, "request_id": "x"}))

    def test_unrelated_work_fails(self):
        task = make_task(0, 4, False)
        env = Environment(task)
        reference_solve(env)
        other = next(node for node in task.nodes if node not in env.done)
        env.call("complete", {"node": other, "request_id": "other"})
        self.assertFalse(grade(task, env.snapshot())["success"])

    def test_public_contract_does_not_include_evaluator_fields(self):
        public = make_task(0, 4, True).public_request()
        self.assertEqual(set(public), {"task_id", "instruction", "goal", "available_nodes"})
        self.assertNotIn("reference", json.dumps(public))

    def test_lineage_never_crosses_splits(self):
        split_by_root = {}
        for root in range(12):
            for depth in (4, 8, 16):
                for fault in (False, True):
                    task = make_task(root, depth, fault)
                    split_by_root.setdefault(task.root_id, set()).add(task.split)
        self.assertTrue(all(len(v) == 1 for v in split_by_root.values()))

    def test_migration_semantics(self):
        task = make_task(0, 4, False)
        old = task_manifest(task)
        self.assertEqual(migration(old, task_manifest(task, note="doc fix")), "reuse")
        self.assertEqual(migration(old, task_manifest(task, "2")), "regrade")
        self.assertEqual(migration(old, task_manifest(make_task(0, 8, False))), "rerun")
        self.assertEqual(migration(old, old, artifact_complete=False), "rerun")
        self.assertEqual(migration(None, old), "rerun")

    def test_paired_stats_reject_missing_and_duplicate(self):
        rows = [{"root_id": f"r{i}", "task_id": f"t{i}", "repeat": 0,
                 "system": system, "success": int(system == "b")}
                for i in range(4) for system in ("a", "b")]
        result = paired_root_bootstrap(rows)
        self.assertEqual(result["difference_b_minus_a"], 1)
        self.assertEqual(result["ci95_percentile"], [1, 1])
        with self.assertRaises(ValueError):
            paired_root_bootstrap(rows[:-1])
        with self.assertRaises(ValueError):
            paired_root_bootstrap(rows + rows[:1])

    def test_real_http_path_is_scripted_not_model_quality(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                if len(requests) == 1:
                    message = {"role": "assistant", "content": None, "tool_calls": [
                        {"id": "call_1", "type": "function", "function": {"name": "status", "arguments": "{}"}}]}
                else:
                    message = {"role": "assistant", "content": "I am done."}
                data = json.dumps({"choices": [{"message": message}],
                                   "usage": {"prompt_tokens": 10, "completion_tokens": 5}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            import urllib.request
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with patch("urllib.request.urlopen", opener.open):
                result = run_live(make_task(0, 4, True), f"http://127.0.0.1:{server.server_port}/v1", "scripted", 19)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
        self.assertEqual(result["termination"], "actor_stopped")
        self.assertFalse(result["grading"]["success"])
        self.assertEqual(result["usage"]["prompt_tokens"], 20)
        self.assertEqual(len(result["events"]), 1)
        self.assertNotIn("verifier_hash", json.dumps(requests))
        self.assertTrue(result["usage_complete"])


if __name__ == "__main__":
    unittest.main()
