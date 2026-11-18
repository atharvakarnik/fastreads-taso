import copy
import csv
import gzip
import http.client
import io
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from synthetic import add, nifti_bytes


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="taso-synthetic-")
        self.base = Path(self.temp.name).resolve()
        self.store = server.Store(self.base)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def restart(self):
        self.store.close()
        self.store = server.Store(self.base)

    def test_fixture_is_synthetic_nifti(self):
        raw = gzip.decompress(nifti_bytes())
        self.assertEqual(struct.unpack_from("<i", raw)[0], 348)
        self.assertEqual(raw[344:348], b"n+1\0")
        self.assertEqual(len(raw), 352 + 16 * 18 * 10 * 2)

    def test_empty_and_optional_never_substituted(self):
        self.assertEqual(self.store.initialize("independent")["tasks"], [])
        add(self.base, sequences=(server.OPTIONAL,))
        inventory, s = server.discover(self.base)
        self.assertFalse(inventory)
        self.assertEqual((s["visits"], s["optional"], s["neither"]), (1, 1, 1))
        self.assertFalse(self.store.initialize("candidate-only")["tasks"])

    def test_discovery_natural_order_partial_exact_files(self):
        add(self.base, visit="P10")
        add(self.base, visit="P2", sequences=(server.REFERENCE,))
        add(self.base, visit="P1")
        add(self.base, subject="INDD002", sequences=(server.CANDIDATE, server.OPTIONAL))
        add(self.base, visit="P0")
        add(self.base, visit="P01")
        add(self.base, visit="P3x")
        add(self.base, visit="P4", sequences=("3d_resliced.nii", "flair2d-copy.nii.gz"))
        inventory, s = server.discover(self.base)
        self.assertEqual(list(dict.fromkeys(k[1] for k in inventory if k[0] == "INDD001")), ["P1", "P2", "P10"])
        self.assertEqual((s["paired"], s["reference_only"], s["candidate_only"], s["neither"]), (2, 1, 1, 1))
        self.assertEqual(len(inventory), 6)

    def test_three_visit_acceptance_and_blinded_queue(self):
        add(self.base)
        add(self.base, visit="P2", sequences=(server.REFERENCE,))
        add(self.base, subject="INDD002")
        q = self.store.initialize("independent")
        self.assertEqual(q["summary"]["visits"], 3)
        self.assertEqual(len(q["tasks"]), 5)
        text = json.dumps(q)
        for hidden in ("INDD001", "INDD002", server.REFERENCE, server.CANDIDATE, str(self.base)):
            self.assertNotIn(hidden, text)
        tasks = self.store.session("independent")["tasks"]
        self.assertTrue(all(server.task_key(a)[:2] != server.task_key(b)[:2] for a, b in zip(tasks, tasks[1:])))

    def test_restart_add_remove_and_separate_mode_records(self):
        add(self.base)
        add(self.base, visit="P2")
        q = self.store.initialize("independent")
        first = q["tasks"][0]["id"]
        self.store.save("independent", first, dict(notes='α\t"quoted"\nsecond line', completed=True, flag=True, revision=0))
        before = copy.deepcopy(self.store.state)
        self.restart()
        self.assertEqual(self.store.state, before)
        self.assertEqual(self.store.initialize("independent")["tasks"][0]["id"], first)
        other = self.store.initialize("candidate-only")
        candidate = self.store.session("candidate-only")["tasks"]
        self.assertTrue(all(t["sequence"] == server.CANDIDATE for t in candidate))
        self.assertTrue(set(t["id"] for t in candidate).isdisjoint(t["id"] for t in before["modes"]["independent"]["tasks"]))
        self.assertTrue(all(not t["review"]["completed"] for t in other["tasks"]))
        add(self.base, subject="INDD002")
        extended = self.store.initialize("independent")["tasks"]
        self.assertEqual([t["id"] for t in extended[:4]], [t["id"] for t in q["tasks"]])
        task = self.store.task("independent", first)
        (self.base / "data" / task["indd"] / task["visit"] / task["sequence"]).unlink()
        q2 = self.store.initialize("independent")
        self.assertFalse(q2["tasks"][0]["available"])
        self.assertTrue(q2["tasks"][0]["review"]["completed"])
        rows = list(csv.DictReader(io.StringIO(self.store.export("independent").decode("utf-8"), newline=""), delimiter="\t"))
        self.assertEqual(rows[0]["notes"], 'α\t"quoted"\nsecond line')
        self.assertEqual(rows[0]["sequence"], task["sequence"])
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(r["mode"] == "independent" for r in rows))

    def test_distinct_visit_and_sequence_reviews_and_conflict(self):
        add(self.base)
        add(self.base, visit="P2")
        self.store.initialize("independent")
        for i, t in enumerate(self.store.session("independent")["tasks"]):
            self.store.save("independent", t["id"], dict(notes=str(i), completed=True, flag=False, revision=0))
        reviews = self.store.session("independent")["reviews"]
        self.assertEqual(len(reviews), 4)
        self.assertEqual(len({r["notes"] for r in reviews.values()}), 4)
        with self.assertRaises(server.Problem) as caught:
            self.store.save("independent", next(iter(reviews)), dict(notes="stale", completed=False, flag=False, revision=0))
        self.assertEqual(caught.exception.status, 409)
        with self.assertRaises(server.Problem):
            self.store.save("independent", "0" * 32, dict(notes="x", completed=False, flag=False, revision=0))

    def test_failed_write_preserves_memory_disk_and_backup(self):
        add(self.base)
        task_id = self.store.initialize("independent")["tasks"][0]["id"]
        self.store.save("independent", task_id, dict(notes="retained", completed=True, flag=False, revision=0))
        before = self.store.path.read_bytes()
        state = copy.deepcopy(self.store.state)
        real_replace = os.replace
        def fail_main(src, dst):
            if Path(dst) == self.store.path:
                raise OSError("synthetic disk failure")
            real_replace(src, dst)
        with mock.patch("server.os.replace", side_effect=fail_main):
            with self.assertRaises(server.Problem):
                self.store.save("independent", task_id, dict(notes="lost?", completed=False, flag=True, revision=1))
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(self.store.backup.read_bytes(), before)
        self.assertEqual(self.store.state, state)
        self.assertFalse(list(self.store.directory.glob(".write-*")))
        self.restart()
        self.assertEqual(self.store.state, state)

    def test_corrupt_state_refuses_reset_and_backup_restore(self):
        add(self.base)
        self.store.initialize("independent")
        task = self.store.session("independent")["tasks"][0]
        self.store.save("independent", task["id"], dict(notes="backup", completed=True, flag=False, revision=0))
        good = self.store.path.read_bytes()
        self.store.save("independent", task["id"], dict(notes="latest", completed=True, flag=False, revision=1))
        self.assertEqual(self.store.backup.read_bytes(), good)
        self.store.close()
        self.store.path.write_text("broken", encoding="utf-8")
        with self.assertRaises(server.Problem):
            server.Store(self.base)
        self.assertEqual(self.store.path.read_text(), "broken")
        self.store.path.write_bytes(self.store.backup.read_bytes())
        self.store = server.Store(self.base)
        self.assertEqual(self.store.session("independent")["reviews"][task["id"]]["notes"], "backup")

    def test_validation_and_one_writer(self):
        with self.assertRaises(server.Problem):
            server.Store(self.base)
        for mode in ("both", None, [], {}):
            with self.assertRaises(server.Problem):
                self.store.initialize(mode)
        add(self.base)
        task = self.store.initialize("independent")["tasks"][0]
        for changes in ({"completed": "true"}, {"revision": True}, {"notes": "x" * 20001}, {"flag": 1}, {"extra": True}):
            payload = dict(notes="", completed=False, flag=False, revision=0)
            payload.update(changes)
            with self.assertRaises(server.Problem):
                self.store.save("independent", task["id"], payload)

    def test_symlinks_and_case_ambiguity(self):
        d = add(self.base)
        # A second case spelling cannot exist on every filesystem.
        alias = d / "3D_RESLICED.NII.GZ"
        alias.write_bytes(nifti_bytes())
        if len([p for p in d.iterdir() if p.name.casefold() == server.CANDIDATE]) > 1:
            self.assertNotIn(("INDD001", "P1", server.CANDIDATE), server.discover(self.base)[0])
        alias.unlink()
        outside = self.base / "outside.nii.gz"
        outside.write_bytes(nifti_bytes())
        (d / server.CANDIDATE).unlink(missing_ok=True)
        try:
            (d / server.CANDIDATE).symlink_to(outside)
            (self.base / "data" / "ESCAPE").symlink_to(d, target_is_directory=True)
            (self.base / "data" / "INDD001" / "P2").symlink_to(d, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation unavailable on this OS")
        inventory, _ = server.discover(self.base)
        self.assertEqual(list(inventory), [("INDD001", "P1", server.REFERENCE)])
        self.assertFalse(server.safe_path(self.base / "data", outside))


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="taso-http-synthetic-")
        self.base = Path(self.temp.name).resolve()
        for name in ("viewer.html", "viewer.js", "niivue.umd.js"):
            shutil.copyfile(server.BASE_DIR / name, self.base / name)
        add(self.base)
        self.httpd = server.make_server(self.base, 0)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.httpd.server_port
        self.token = self.httpd.token

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()
        self.httpd.store.close()
        self.temp.cleanup()

    def request(self, path, payload=None, headers=None, method=None):
        h = {"X-FastReads-Token": self.token, "Content-Type": "application/json"}
        h.update(headers or {})
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=4)
        conn.request(method or ("POST" if payload is not None else "GET"), path,
                     body=json.dumps(payload).encode() if payload is not None else None, headers=h)
        response = conn.getresponse()
        body = response.read()
        status, out_headers = response.status, dict(response.getheaders())
        conn.close()
        return status, out_headers, body

    def start_mode(self, mode="independent"):
        status, _, data = self.request("/api/session", {"mode": mode})
        self.assertEqual(status, 200)
        return json.loads(data)

    def test_static_health_empty_and_loopback(self):
        self.assertEqual(self.httpd.server_address[0], "127.0.0.1")
        self.assertEqual(json.loads(self.request("/api/health")[2])["app"], server.APP_ID)
        self.assertIn(b"FastReads Taso", self.request("/")[2])
        shutil.rmtree(self.base / "data")
        q = self.start_mode()
        self.assertEqual(q["summary"]["visits"], 0)
        self.assertEqual(q["tasks"], [])

    def test_image_defaults_opaque_and_save_export(self):
        q = self.start_mode()
        for task in q["tasks"]:
            path = f'/api/independent/{task["id"]}'
            status, headers, image = self.request(path + "/image")
            true_task = self.httpd.store.task("independent", task["id"])
            self.assertEqual(status, 200)
            self.assertEqual(image, nifti_bytes())
            self.assertEqual(headers["X-Display-Range"], "-200,200" if true_task["sequence"] == server.CANDIDATE else "auto")
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertNotIn("Content-Disposition", headers)
            self.assertEqual(self.request(path + "/review", dict(notes="synthetic", completed=True, flag=True, revision=0))[0], 200)
        self.assertEqual(self.request("/api/independent/export")[0], 404)
        self.assertEqual(self.request("/api/independent/export", {"unblind": False})[0], 400)
        status, headers, data = self.request("/api/independent/export", {"unblind": True})
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])
        rows = list(csv.DictReader(io.StringIO(data.decode()), delimiter="\t"))
        self.assertEqual({r["sequence"] for r in rows}, {server.REFERENCE, server.CANDIDATE})
        self.assertTrue(all(r["notes"] == "synthetic" for r in rows))

    def test_deny_paths_origins_ids_and_bad_payloads(self):
        q = self.start_mode()
        task = q["tasks"][0]["id"]
        for path in ("/server.py", "/state/reviews.json", "/data/INDD001/P1/flair2d.nii.gz", "/.git/config",
                     "/../server.py", "/%2e%2e/server.py", "/api/independent/../../server.py/image",
                     "/api/independent/%2e%2e/image", "/api/independent/" + "0" * 32 + "/image"):
            self.assertEqual(self.request(path)[0], 404, path)
        self.assertEqual(self.request("/api/status", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request("/api/status", headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.request("/api/status", headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.request("/api/session", {"mode": "independent"}, headers={"X-FastReads-Token": "bad"})[0], 403)
        self.assertEqual(self.request("/api/session", ["invalid"])[0], 400)
        self.assertEqual(self.request("/api/session", {"mode": "independent"}, headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request(f"/api/candidate-only/{task}/review", dict(notes="", completed=False, flag=False, revision=0))[0], 404)

    def test_input_replaced_by_symlink_after_discovery(self):
        q = self.start_mode()
        task = self.httpd.store.task("independent", q["tasks"][0]["id"])
        path = self.base / "data" / task["indd"] / task["visit"] / task["sequence"]
        path.unlink()
        outside = self.base / "outside.nii.gz"
        outside.write_bytes(nifti_bytes())
        try:
            path.symlink_to(outside)
        except OSError:
            self.skipTest("symlink creation unavailable on this OS")
        self.assertEqual(self.request(f'/api/independent/{task["id"]}/image')[0], 404)


if __name__ == "__main__":
    unittest.main()
