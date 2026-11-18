#!/usr/bin/env python3
"""FastReads Taso: offline review server derived from fastreads (see NOTICE.md)."""
import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import stat
import sys
import tempfile
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

BASE_DIR = Path(__file__).resolve().parent
PORT = 8002
APP_ID = "fastreads-taso-v1"
REFERENCE = "flair2d.nii.gz"
CANDIDATE = "3d_resliced.nii.gz"
OPTIONAL = "spcX_ir_2mm_p4_te980_corr.nii.gz"
MODES = ("independent", "candidate-only")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
VISIT_RE = re.compile(r"P[1-9][0-9]*\Z")
TASK_RE = re.compile(r"[0-9a-f]{32}\Z")


class Problem(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def natural_key(value):
    return tuple((1, int(p)) if p.isdigit() else (0, p.casefold())
                 for p in re.split(r"(\d+)", value)) + ((0, value),)


def safe_path(root, path, directory=False):
    """Reject symlinks (including ancestors), escapes, nonregular inputs and junctions."""
    try:
        parts = path.relative_to(root).parts
        for p in (root, *(root.joinpath(*parts[:i]) for i in range(1, len(parts) + 1))):
            if p.is_symlink() or (hasattr(p, "is_junction") and p.is_junction()):
                return False
            if p.resolve() != p.absolute():
                return False
        mode = path.stat().st_mode
        return stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)
    except (OSError, ValueError, RuntimeError):
        return False


def discover(base):
    """Internal inventory only. Never serialize this mapping into the reading API."""
    root = Path(base) / "data"
    inventory = {}
    summary = dict(visits=0, paired=0, reference_only=0, candidate_only=0,
                   neither=0, optional=0, rejected=0)
    if not root.exists() and not root.is_symlink():
        return inventory, summary
    if not safe_path(Path(base), root, directory=True):
        raise Problem("data/ must be a regular local directory without symlinks.", 503)
    for subject in sorted(root.iterdir(), key=lambda p: natural_key(p.name)):
        if not ID_RE.fullmatch(subject.name) or not safe_path(root, subject, True):
            summary["rejected"] += 1
            continue
        for visit in sorted(subject.iterdir(), key=lambda p: natural_key(p.name)):
            if not VISIT_RE.fullmatch(visit.name) or not safe_path(root, visit, True):
                summary["rejected"] += 1
                continue
            summary["visits"] += 1
            names = [p.name for p in visit.iterdir()]
            found = set()
            for sequence in (REFERENCE, CANDIDATE, OPTIONAL):
                matches = [n for n in names if n.casefold() == sequence.casefold()]
                path = visit / sequence
                if matches != [sequence] or not safe_path(root, path):
                    if matches:
                        summary["rejected"] += 1
                    continue
                found.add(sequence)
                if sequence != OPTIONAL:
                    inventory[(subject.name, visit.name, sequence)] = path
            summary["optional"] += int(OPTIONAL in found)
            category = ("paired" if REFERENCE in found and CANDIDATE in found else
                        "reference_only" if REFERENCE in found else
                        "candidate_only" if CANDIDATE in found else "neither")
            summary[category] += 1
    return inventory, summary


def task_key(task):
    return task["indd"], task["visit"], task["sequence"]


def empty_review():
    return dict(notes="", completed=False, flag=False, revision=0, updated_at="")


def validate_state(state):
    """Fail closed instead of resetting a damaged assignment or losing old reviews."""
    if not isinstance(state, dict) or state.get("version") != 1 or not isinstance(state.get("modes"), dict):
        raise ValueError()
    all_ids = set()
    for mode, session in state["modes"].items():
        if mode not in MODES or not isinstance(session, dict):
            raise ValueError()
        if not TASK_RE.fullmatch(session["seed"]) or not isinstance(session["tasks"], list):
            raise ValueError()
        keys, ids = set(), set()
        for task in session["tasks"]:
            key = task_key(task)
            if (not ID_RE.fullmatch(key[0]) or not VISIT_RE.fullmatch(key[1]) or
                    key[2] not in ((CANDIDATE,) if mode == "candidate-only" else (REFERENCE, CANDIDATE)) or
                    not TASK_RE.fullmatch(task["id"]) or task["id"] in all_ids or key in keys):
                raise ValueError()
            keys.add(key)
            ids.add(task["id"])
            all_ids.add(task["id"])
        if not isinstance(session["reviews"], dict) or not set(session["reviews"]) <= ids:
            raise ValueError()
        for review in session["reviews"].values():
            if (not isinstance(review["notes"], str) or type(review["completed"]) is not bool or
                    type(review["flag"]) is not bool or type(review["revision"]) is not int or
                    review["revision"] < 1 or not isinstance(review["updated_at"], str)):
                raise ValueError()


def atomic_bytes(path, data):
    fd, temp = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class Store:
    def __init__(self, base):
        self.base = Path(base).absolute()
        self.directory = self.base / "state"
        if self.directory.is_symlink():
            raise Problem("state/ must not be a symlink.", 503)
        self.directory.mkdir(mode=0o700, exist_ok=True)
        if not safe_path(self.base, self.directory, True):
            raise Problem("Unsafe state directory.", 503)
        self.path = self.directory / "reviews.json"
        self.backup = self.directory / "reviews.json.bak"
        self.lock = threading.RLock()
        self.process_lock = None
        try:
            lock_path = self.directory / "writer.lock"
            if lock_path.is_symlink():
                raise OSError()
            self.process_lock = open(lock_path, "a+b")
            if os.name == "nt":
                import msvcrt
                self.process_lock.seek(0)
                self.process_lock.write(b"\0")
                self.process_lock.flush()
                self.process_lock.seek(0)
                msvcrt.locking(self.process_lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.process_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.close()
            raise Problem("Another viewer may be using this state folder, or it is not writable.", 503)
        try:
            if self.path.is_symlink() or self.backup.is_symlink():
                raise ValueError()
            if self.path.exists():
                self.state = json.loads(self.path.read_text(encoding="utf-8"))
                validate_state(self.state)
            elif self.backup.exists():
                raise ValueError()
            else:
                self.state = {"version": 1, "modes": {}}
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
            self.close()
            raise Problem("Review state is unreadable or invalid. Preserve state/ and restore a backup; see README.md.", 503)

    def close(self):
        if self.process_lock:
            self.process_lock.close()
            self.process_lock = None

    def commit(self, state):
        data = (json.dumps(state, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        try:
            if (not safe_path(self.base, self.directory, True) or
                    self.path.is_symlink() or self.backup.is_symlink()):
                raise OSError()
            if self.path.exists():
                atomic_bytes(self.backup, self.path.read_bytes())
            atomic_bytes(self.path, data)
        except OSError:
            raise Problem("Save failed. Local state was preserved; check free space and write permissions, then retry.", 503)
        self.state = state

    def initialize(self, mode):
        if not isinstance(mode, str) or mode not in MODES:
            raise Problem("Unknown review mode.")
        with self.lock:
            inventory, _ = discover(self.base)
            state = copy.deepcopy(self.state)
            session = state["modes"].setdefault(mode, dict(seed=secrets.token_hex(16), tasks=[], reviews={}))
            existing = {task_key(t) for t in session["tasks"]}
            pending = [dict(indd=k[0], visit=k[1], sequence=k[2]) for k in inventory
                       if k not in existing and (mode == "independent" or k[2] == CANDIDATE)]
            def rank(task):
                return hashlib.sha256((session["seed"] + json.dumps(task_key(task))).encode()).digest()
            groups = {}
            for task in sorted(pending, key=rank):
                groups.setdefault(task_key(task)[:2], []).append(task)
            previous = task_key(session["tasks"][-1])[:2] if session["tasks"] else None
            while groups:
                choices = [k for k in groups if k != previous] or list(groups)
                chosen = min(choices, key=lambda k: (-len(groups[k]), rank(groups[k][0])))
                task = groups[chosen].pop(0)
                task["id"] = secrets.token_hex(16)
                session["tasks"].append(task)
                previous = chosen
                if not groups[chosen]:
                    del groups[chosen]
            if state != self.state:
                self.commit(state)
        return self.queue(mode)

    def session(self, mode):
        if mode not in MODES or mode not in self.state["modes"]:
            raise Problem("Initialize this review mode first.", 404)
        return self.state["modes"][mode]

    def queue(self, mode):
        with self.lock:
            session = self.session(mode)
            inventory, summary = discover(self.base)
            return dict(mode=mode, summary=summary, tasks=[
                dict(id=t["id"], available=task_key(t) in inventory,
                     review=copy.deepcopy(session["reviews"].get(t["id"], empty_review())))
                for t in session["tasks"]])

    def task(self, mode, task_id):
        for task in self.session(mode)["tasks"]:
            if task["id"] == task_id:
                return task
        raise Problem("Unknown review task.", 404)

    def save(self, mode, task_id, payload):
        if (not isinstance(payload, dict) or set(payload) != {"notes", "completed", "flag", "revision"} or
                not isinstance(payload["notes"], str) or len(payload["notes"]) > 20000 or
                type(payload["completed"]) is not bool or type(payload["flag"]) is not bool or
                type(payload["revision"]) is not int):
            raise Problem("Invalid review fields (notes limit: 20,000 characters).")
        with self.lock:
            self.task(mode, task_id)
            current = self.session(mode)["reviews"].get(task_id, empty_review())
            if current["revision"] != payload["revision"]:
                raise Problem("This record changed in another tab. Keep your notes, then reload before editing.", 409)
            review = dict(payload, revision=current["revision"] + 1,
                          updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            state = copy.deepcopy(self.state)
            state["modes"][mode]["reviews"][task_id] = review
            self.commit(state)
            return review

    def export(self, mode):
        with self.lock:
            session = self.session(mode)
            stream = io.StringIO(newline="")
            writer = csv.writer(stream, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_ALL)
            writer.writerow(["INDD", "visit", "sequence", "mode", "review_task_id", "completed", "flag", "notes", "revision", "updated_at"])
            for task in session["tasks"]:
                r = session["reviews"].get(task["id"], empty_review())
                writer.writerow([*task_key(task), mode, task["id"], str(r["completed"]).lower(),
                                 str(r["flag"]).lower(), r["notes"], r["revision"], r["updated_at"]])
            return stream.getvalue().encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "FastReadsTaso/1"

    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; font-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        super().end_headers()

    def send_data(self, data, content_type="application/json; charset=utf-8", status=200, download=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if download:
            self.send_header("Content-Disposition", f'attachment; filename="{download}"')
        self.end_headers()
        self.wfile.write(data)

    def json(self, data, status=200):
        self.send_data(json.dumps(data).encode("utf-8"), status=status)

    def guard(self, write=False):
        expected = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != expected:
            raise Problem("Use the launcher's 127.0.0.1 URL.", 403)
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{expected}":
            raise Problem("Cross-origin requests are disabled.", 403)
        if self.headers.get("Sec-Fetch-Site") not in (None, "none", "same-origin"):
            raise Problem("Cross-site requests are disabled.", 403)
        if write and self.headers.get("X-FastReads-Token") != self.server.token:
            raise Problem("Session token missing; reload the viewer.", 403)

    def payload(self):
        if self.headers.get("Content-Type") != "application/json" or self.headers.get("Transfer-Encoding"):
            raise Problem("Use a JSON request.", 415)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 150000:
                raise ValueError()
            result = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except (ValueError, UnicodeError, RecursionError):
            raise Problem("Invalid or oversized JSON request.")

    def route(self, write=False):
        self.guard(write)
        path = urlsplit(self.path).path
        store = self.server.store
        if path == "/api/health" and not write:
            return self.json(dict(app=APP_ID, instance=hashlib.sha256(os.fsencode(store.base)).hexdigest()))
        if path == "/api/status" and not write:
            _, summary = discover(store.base)
            return self.json(dict(summary=summary, token=self.server.token))
        if path == "/api/session" and write:
            return self.json(store.initialize(self.payload().get("mode")))
        match = re.fullmatch(r"/api/(independent|candidate-only)/(queue|export|([0-9a-f]{32})/(image|review))", path)
        if match:
            mode, action, task_id, kind = match.groups()
            if action == "queue" and not write:
                return self.json(store.queue(mode))
            if action == "export" and write:
                if self.payload() != {"unblind": True}:
                    raise Problem("Export requires explicit acknowledgement of unblinding.")
                return self.send_data(store.export(mode), "text/tab-separated-values; charset=utf-8",
                                      download=f"fastreads-taso-{mode}.tsv")
            if kind == "review" and write:
                return self.json(dict(review=store.save(mode, task_id, self.payload())))
            if kind == "image" and not write:
                with store.lock:
                    task = store.task(mode, task_id)
                    inventory, _ = discover(store.base)
                    image = inventory.get(task_key(task))
                if image is None or not safe_path(store.base / "data", image):
                    raise Problem("This task's input is missing, unsafe or ambiguous. Restore the original input and restart.", 404)
                try:
                    fd = os.open(image, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
                    with os.fdopen(fd, "rb") as handle:
                        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                            raise OSError()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/gzip")
                        self.send_header("Content-Length", str(os.fstat(handle.fileno()).st_size))
                        self.send_header("X-Display-Range", "-200,200" if task["sequence"] == CANDIDATE else "auto")
                        self.end_headers()
                        shutil.copyfileobj(handle, self.wfile, 128 * 1024)
                    return
                except OSError:
                    raise Problem("Input could not be read.", 404)
        static = {"/": ("viewer.html", "text/html; charset=utf-8"),
                  "/viewer.html": ("viewer.html", "text/html; charset=utf-8"),
                  "/viewer.js": ("viewer.js", "text/javascript; charset=utf-8"),
                  "/niivue.umd.js": ("niivue.umd.js", "text/javascript; charset=utf-8")}
        if not write and path in static:
            name, mime = static[path]
            target = store.base / name
            if safe_path(store.base, target):
                return self.send_data(target.read_bytes(), mime)
        raise Problem("Not found.", 404)

    def handle_request(self, write=False):
        self.connection.settimeout(15)
        try:
            self.route(write)
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass
        except Problem as error:
            self.json(dict(error=str(error)), error.status)
        except (OSError, ValueError, TypeError):
            self.json(dict(error="Local operation failed. Check inputs and local write permissions."), 503)

    def do_GET(self):
        self.handle_request()

    def do_POST(self):
        self.handle_request(True)


def make_server(base=BASE_DIR, port=PORT):
    store = Store(base)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError:
        store.close()
        raise
    server.daemon_threads = True
    server.store = store
    server.token = secrets.token_hex(32)
    return server


def main():
    if sys.version_info < (3, 10):
        print("FastReads Taso requires Python 3.10 or newer.")
        return 1
    try:
        server = make_server()
    except (OSError, Problem) as error:
        print(str(error) if isinstance(error, Problem) else "Cannot start FastReads Taso. Check port 8002 and local write permissions.")
        return 1
    print("FastReads Taso: http://127.0.0.1:8002/viewer.html\nKeep this window open. Press Ctrl+C here to stop.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
