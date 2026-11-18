#!/usr/bin/env python3
"""Optional Chrome + Node smoke test. No npm/pip packages; temporary synthetic inputs."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server
from synthetic import add


def main():
    chrome = os.environ.get("CHROME") or shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome and Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome").exists():
        chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    node = shutil.which("node")
    if not chrome or not node:
        print("SKIP: optional UI checks require Chrome and Node 22+ (development tools only).")
        return 0
    with tempfile.TemporaryDirectory(prefix="taso-browser-synthetic-") as temp:
        base = Path(temp).resolve()
        for name in ("viewer.html", "viewer.js", "niivue.umd.js"):
            shutil.copyfile(server.BASE_DIR / name, base / name)
        empty = "--empty" in sys.argv
        if not empty:
            add(base)
            add(base, visit="P2", sequences=(server.REFERENCE,))
            add(base, subject="INDD002", orientation="qform")
        httpd = server.make_server(base, 0)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            debug_port = probe.getsockname()[1]
        browser = subprocess.Popen([chrome, "--headless=new", "--no-first-run", "--no-default-browser-check",
            "--disable-background-networking", "--disable-component-update", "--disable-sync", "--disable-extensions",
            "--metrics-recording-only", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
            f"--user-data-dir={base / 'browser-profile'}", f"--remote-debugging-port={debug_port}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            result = subprocess.run([node, str(Path(__file__).with_name("browser_driver.mjs")), str(debug_port),
                                     f"http://127.0.0.1:{httpd.server_port}/viewer.html", "--empty" if empty else "--data"], timeout=90)
            return result.returncode
        finally:
            browser.terminate()
            browser.wait(timeout=10)
            httpd.shutdown()
            httpd.server_close()
            thread.join()
            httpd.store.close()


if __name__ == "__main__":
    raise SystemExit(main())
