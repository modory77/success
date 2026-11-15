"""로컬 웹 UI: http://127.0.0.1:8766  (표준 라이브러리만 사용)

보안: 127.0.0.1 에만 바인딩, Host 헤더 검사(DNS rebinding 방지), POST 는 사용자 지정 헤더 필수(CSRF 방지),
파일 접근은 uploads/ samples/ output/ 폴더의 파일 이름(경로 없음)으로만 허용.
"""
import json
import mimetypes
import os
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import common, config, illustrate, pipeline
from .common import ROOT, log

PORT = int(os.environ.get("UI_PORT", "8766"))
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}
FOLDERS = {"uploads": ROOT / "uploads", "samples": ROOT / "samples", "inbox": ROOT / "inbox"}
INDEX = Path(__file__).resolve().parent / "web" / "index.html"
KEYS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


class Job:
    lock = threading.Lock()
    running = False
    video = ""
    stage = ""
    lines: list = []
    error = ""


def _sink(msg):
    Job.lines.append(str(msg))
    if len(Job.lines) > 4000:
        del Job.lines[:1000]


def mask(v: str) -> str:
    return "" if not v else (v[:4] + "..." + v[-4:] if len(v) > 12 else "설정됨")


def set_env(key: str, value: str):
    f = ROOT / ".env"
    lines = f.read_text(encoding="utf-8-sig").splitlines() if f.exists() else []
    for i, l in enumerate(lines):
        if re.match(rf"^\s*{key}\s*=", l):
            lines[i] = f"{key}={value}"
            break
    else:
        lines.append(f"{key}={value}")
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[key] = value


def resolve_video(vid: str) -> Path:
    """'uploads/파일.mp4' 형태의 id 를 안전하게 실제 경로로."""
    folder, _, name = vid.partition("/")
    if folder not in FOLDERS or not name or name != Path(name).name:
        raise ValueError("잘못된 영상 id")
    p = FOLDERS[folder] / name
    if not p.is_file() or p.suffix.lower() not in VIDEO_EXTS:
        raise FileNotFoundError(name)
    return p


def list_videos():
    o = config.defaults()
    out = []
    for folder, d in FOLDERS.items():
        if not d.exists():
            continue
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
                st = pipeline.status(p, o)
                res = pipeline.out_path(p, o)
                out.append({"id": f"{folder}/{p.name}", "name": p.name, "folder": folder,
                            "size_mb": round(p.stat().st_size / 1048576, 1), "status": st,
                            "output": f"/files/output/{res.name}?v={int(res.stat().st_mtime)}" if st["render"] else ""})
    return out


def start_job(vid, stage, force, opts):
    with Job.lock:
        if Job.running:
            return False, "이미 다른 작업이 실행 중입니다"
        Job.running, Job.video, Job.stage, Job.error, Job.lines = True, vid, stage, "", []
    path = resolve_video(vid)

    def work():
        common.add_log_sink(_sink)
        try:
            pipeline.run(path, stage, opts, force)
        except Exception as e:  # noqa: BLE001
            Job.error = str(e)
            log(f"\n오류: {e}")
        finally:
            common.remove_log_sink(_sink)
            Job.running = False
    threading.Thread(target=work, daemon=True).start()
    return True, ""


class Handler(BaseHTTPRequestHandler):
    server_version = "autoedit"

    def log_message(self, *a):  # 콘솔 조용히
        pass

    # ---------- helpers
    def _ok_host(self) -> bool:
        return self.headers.get("Host", "") in HOSTS

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    # ---------- GET
    def do_GET(self):
        if not self._ok_host():
            return self._json({"error": "bad host"}, 403)
        u = urlparse(self.path)
        try:
            if u.path == "/":
                b = INDEX.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                return self.wfile.write(b)
            if u.path == "/api/state":
                return self._json({
                    "gpu": common.gpu_name(), "videos": list_videos(), "defaults": config.defaults(),
                    "keys": {k: mask(os.environ.get(v, "")) for k, v in KEYS.items()},
                    "logos": len(illustrate.list_logos(config.defaults()["logo_dir"])),
                    "job": {"running": Job.running, "video": Job.video, "stage": Job.stage}})
            if u.path == "/api/log":
                since = int(parse_qs(u.query).get("since", ["0"])[0])
                return self._json({"lines": Job.lines[since:], "next": len(Job.lines), "running": Job.running,
                                   "stage": Job.stage, "video": Job.video, "error": Job.error})
            if u.path == "/api/report":
                p = resolve_video(parse_qs(u.query).get("video", [""])[0])
                r = pipeline.work_dir(p, config.defaults()) / "report.json"
                return self._json(json.loads(r.read_text(encoding="utf-8")) if r.exists() else {})
            m = re.match(r"^/files/(output|uploads|samples|inbox)/([^/]+)$", u.path)
            if m:
                return self._file(m[1], unquote(m[2]))
        except (ValueError, FileNotFoundError) as e:
            return self._json({"error": str(e)}, 404)
        self._json({"error": "not found"}, 404)

    def _file(self, folder, name):
        base = (ROOT / config.defaults()["out_dir"]) if folder == "output" else FOLDERS[folder]
        p = (base / Path(name).name)
        if not p.is_file():
            return self._json({"error": "not found"}, 404)
        size = p.stat().st_size
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        code = 200
        if rng and (m := re.match(r"bytes=(\d*)-(\d*)", rng)):
            if m[1]:
                start = int(m[1])
            if m[2]:
                end = min(int(m[2]), size - 1)
            code = 206
        self.send_response(code)
        self.send_header("Content-Type", mimetypes.guess_type(p.name)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(p, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 20, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
                left -= len(chunk)

    # ---------- POST
    def do_POST(self):
        if not self._ok_host() or self.headers.get("X-Autoedit") != "1":
            return self._json({"error": "forbidden"}, 403)
        u = urlparse(self.path)
        try:
            if u.path == "/api/upload":
                name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", Path(unquote(parse_qs(u.query).get("name", [""])[0])).name)
                if Path(name).suffix.lower() not in VIDEO_EXTS:
                    return self._json({"error": "영상 파일(mp4, mov, mkv, avi, m4v, webm)만 올릴 수 있습니다"}, 400)
                FOLDERS["uploads"].mkdir(exist_ok=True)
                dest = FOLDERS["uploads"] / name
                left = int(self.headers.get("Content-Length", 0))
                with open(dest, "wb") as f:
                    while left > 0:
                        chunk = self.rfile.read(min(1 << 20, left))
                        if not chunk:
                            break
                        f.write(chunk)
                        left -= len(chunk)
                return self._json({"ok": True, "id": f"uploads/{name}"})
            data = self._body()
            if u.path == "/api/run":
                ok, msg = start_job(data["video"], data.get("stage", "all"), bool(data.get("force")), data.get("opts") or {})
                return self._json({"ok": ok, "error": msg}, 200 if ok else 409)
            if u.path == "/api/settings":
                for k, env in KEYS.items():
                    v = (data.get(k) or "").strip()
                    if v:
                        if len(v) < 10 or re.search(r"\s", v):
                            return self._json({"error": f"{env} 형식이 올바르지 않습니다"}, 400)
                        set_env(env, v)
                return self._json({"ok": True, "keys": {k: mask(os.environ.get(v, "")) for k, v in KEYS.items()}})
            if u.path == "/api/clear":
                if Job.running:
                    return self._json({"error": "작업 실행 중에는 삭제할 수 없습니다"}, 409)
                p = resolve_video(data["video"])
                pipeline.clear_cache(p, config.merge(data.get("opts")))
                return self._json({"ok": True})
        except (ValueError, FileNotFoundError, KeyError) as e:
            return self._json({"error": str(e)}, 400)
        self._json({"error": "not found"}, 404)


def main(open_browser=True):
    for d in FOLDERS.values():
        d.mkdir(exist_ok=True)
    (ROOT / config.defaults()["out_dir"]).mkdir(exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"유튜브 자동 편집 UI: {url}   (종료: Ctrl+C)", flush=True)
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("종료합니다.")


if __name__ == "__main__":
    # 미리보기 창 등에서 실행할 때는 AUTOEDIT_NO_BROWSER=1 로 브라우저 자동 열기를 끈다
    main(open_browser=not os.environ.get("AUTOEDIT_NO_BROWSER"))
