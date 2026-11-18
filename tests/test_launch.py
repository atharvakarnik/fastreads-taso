"""Launcher integration tests run copies of the app with no clinical inputs."""
import http.client
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import unittest

import server


class LauncherTests(unittest.TestCase):
    @unittest.skipIf(os.name == "nt" or shutil.which("bash") is None, "POSIX launcher needs bash")
    def test_start_reuse_other_copy_and_shutdown(self):
        with socket.socket() as probe:
            try:
                probe.bind(("127.0.0.1", 8002))
            except OSError:
                self.skipTest("port 8002 already occupied; do not disturb another application")
        with tempfile.TemporaryDirectory(prefix="taso-launch-synthetic-") as temp:
            root = Path(temp).resolve()
            first = root / "copy one"
            second = root / "copy two"
            for directory in (first, second):
                directory.mkdir()
                for name in ("server.py", "launch.py", "viewer.html", "viewer.js", "niivue.umd.js", "Start_Viewer.sh"):
                    shutil.copyfile(server.BASE_DIR / name, directory / name)
            env = dict(os.environ, NO_BROWSER="1")
            child = subprocess.Popen(["bash", str(first / "Start_Viewer.sh")], env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            try:
                for _ in range(70):
                    conn = http.client.HTTPConnection("127.0.0.1", 8002, timeout=0.2)
                    try:
                        conn.request("GET", "/api/health")
                        response = conn.getresponse()
                        if response.status == 200:
                            response.read()
                            break
                    except OSError:
                        if child.poll() is not None:
                            self.fail(child.stdout.read())
                        time.sleep(0.1)
                    finally:
                        conn.close()
                else:
                    self.fail("synthetic launcher server did not become ready")
                reused = subprocess.run(["bash", str(first / "Start_Viewer.sh")], env=env,
                                        capture_output=True, text=True, timeout=6)
                self.assertEqual(reused.returncode, 0, reused.stdout)
                self.assertIn("Reusing", reused.stdout)
                rejected = subprocess.run(["bash", str(second / "Start_Viewer.sh")], env=env,
                                          capture_output=True, text=True, timeout=6)
                self.assertEqual(rejected.returncode, 1, rejected.stdout)
                self.assertIn("another copy", rejected.stdout)
                self.assertFalse((second / "state").exists())
            finally:
                if child.poll() is None:
                    child.send_signal(signal.SIGINT)
                output, _ = child.communicate(timeout=8)
            self.assertEqual(child.returncode, 0, output)
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(("127.0.0.1", 8002))  # Owned child was stopped.
