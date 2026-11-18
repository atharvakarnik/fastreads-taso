#!/usr/bin/env python3
"""Shared, dependency-free launcher with application AND installation readiness checks."""
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

BASE = Path(__file__).resolve().parent
URL = "http://127.0.0.1:8002/viewer.html"
INSTANCE = hashlib.sha256(os.fsencode(BASE)).hexdigest()


def ready():
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open("http://127.0.0.1:8002/api/health", timeout=0.7) as response:
            value = json.load(response)
            return value == {"app": "fastreads-taso-v1", "instance": INSTANCE}
    except (OSError, ValueError, urllib.error.URLError):
        return False


def main():
    if sys.version_info < (3, 10):
        print("FastReads Taso requires Python 3.10 or newer.")
        return 1
    child = None
    try:
        if ready():
            print("Reusing FastReads Taso from this folder.")
        else:
            with socket.socket() as probe:
                try:
                    probe.bind(("127.0.0.1", 8002))
                except OSError:
                    print("Port 8002 is occupied by another application or another copy of FastReads Taso. Close it and retry.")
                    return 1
            print("Starting FastReads Taso…", flush=True)
            child = subprocess.Popen([sys.executable, str(BASE / "server.py")], cwd=BASE)
            deadline = time.monotonic() + 15
            while not ready():
                if child.poll() is not None or time.monotonic() >= deadline:
                    print("FastReads Taso did not become ready. Read the server message above.")
                    return 1
                time.sleep(0.2)
        print(f"FastReads Taso: {URL}", flush=True)
        if os.environ.get("NO_BROWSER") != "1":
            if not webbrowser.open(URL):
                print("Open the URL above in a desktop browser with WebGL2.")
        if child:
            print("Keep this window open. Press Ctrl+C here when finished.", flush=True)
            child.wait()
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
