"""공통 유틸: 환경설정(.env), 로그, ffmpeg, 영상 정보, 오디오, 인코더 선택."""
import os
import re
import subprocess
import sys
import types
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent

# Windows 앱 제어 정책이 PyAV(av)의 DLL을 막는 환경이 있어, faster-whisper가 import 시점에
# 요구하는 av를 더미로 대체한다. 우리는 오디오를 ffmpeg로 직접 디코딩해 넘기므로 av는 쓰이지 않는다.
try:
    import av  # noqa: F401
except Exception:
    sys.modules["av"] = types.ModuleType("av")

import imageio_ffmpeg


def load_dotenv():
    """프로젝트 루트의 .env 를 읽어 환경변수로 등록 (값이 있으면 기존 환경변수보다 우선)."""
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            os.environ[k.strip()] = v


def _register_cuda_dlls():
    """pip로 설치한 CUDA 런타임(cublas/cudnn) DLL 위치를 등록 -> GPU 가속 whisper."""
    for d in Path(sys.prefix, "Lib", "site-packages", "nvidia").glob("*/bin"):
        try:
            os.add_dll_directory(str(d))
            os.environ["PATH"] = str(d) + os.pathsep + os.environ.get("PATH", "")
        except (OSError, AttributeError):
            pass


load_dotenv()
try:  # "잘못된 이미지" 같은 DLL 오류 팝업이 뜨며 멈추지 않게 한다 (오류는 예외로만 전달)
    import ctypes
    ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x8000)
except Exception:
    pass
_register_cuda_dlls()
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
KOREAN_FONT = Path(r"C:\Windows\Fonts\malgun.ttf")

# ---- 로그: 콘솔 + (웹 UI 등) 외부 수신자 -------------------------------------------------
_sinks = []


def add_log_sink(fn):
    _sinks.append(fn)


def remove_log_sink(fn):
    if fn in _sinks:
        _sinks.remove(fn)


def log(msg: str):
    try:
        print(msg, flush=True)
    except Exception:
        pass
    for s in list(_sinks):
        s(msg)


# ---- GPU / 인코더 ---------------------------------------------------------------------------
def cuda_ok() -> bool:
    """CUDA 런타임 DLL을 실제로 불러올 수 있는지 미리 확인 (보안 정책 등으로 막히면 False)."""
    import ctypes
    try:
        for d in Path(sys.prefix, "Lib", "site-packages", "nvidia").glob("cublas/bin"):
            for dll in d.glob("cublas64_*.dll"):
                ctypes.WinDLL(str(dll))
        ctypes.WinDLL("nvcuda.dll")
        return True
    except OSError:
        return False


def gpu_name() -> str:
    try:
        p = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=5)
        return p.stdout.strip().splitlines()[0] if p.returncode == 0 and p.stdout.strip() else "GPU 없음 (CPU)"
    except Exception:
        return "GPU 없음 (CPU)"


_nvenc = None


def nvenc_ok() -> bool:
    global _nvenc
    if _nvenc is None:
        p = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            "color=c=black:s=256x256:d=0.2", "-c:v", "h264_nvenc", "-f", "null", "-"],
                           capture_output=True)
        _nvenc = p.returncode == 0
    return _nvenc


def video_codec_args(codec: str = "auto", quality: int = 19, preset_cpu: str = "medium") -> list:
    """코덱 선택: auto(NVENC 가능하면 GPU, 아니면 CPU) | h264_nvenc | libx264. quality 는 낮을수록 고화질."""
    use_gpu = codec == "h264_nvenc" or (codec == "auto" and nvenc_ok())
    if use_gpu and nvenc_ok():
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(quality), "-b:v", "0",
                "-pix_fmt", "yuv420p"]
    return ["-c:v", "libx264", "-crf", str(quality), "-preset", preset_cpu, "-pix_fmt", "yuv420p"]


# ---- ffmpeg / 영상 정보 -------------------------------------------------------------------
def run_ffmpeg(args, graph: str | None = None, graph_file: Path | None = None):
    """ffmpeg 실행. graph가 길면 파일로 넘긴다(-/filter_complex, 구버전은 -filter_complex_script)."""
    base = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error"]
    if graph is None:
        cmds = [base + args]
    else:
        graph_file.write_text(graph, encoding="utf-8")
        cmds = [base + ["-/filter_complex", str(graph_file)] + args,
                base + ["-filter_complex_script", str(graph_file)] + args]
    err = ""
    for cmd in cmds:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if p.returncode == 0:
            return
        err = p.stderr
    raise RuntimeError("ffmpeg 실패:\n" + err[-2000:])


def probe(path: Path) -> dict:
    import cv2
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"영상을 열 수 없습니다: {path}")
    info = {
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        "fps": cap.get(cv2.CAP_PROP_FPS) or 30.0,
        "frames": int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    }
    cap.release()
    p = subprocess.run([FFMPEG, "-hide_banner", "-i", str(path)], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", p.stderr)
    info["duration"] = (int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])) if m else info["frames"] / info["fps"]
    info["has_audio"] = bool(re.search(r"Stream #.*Audio", p.stderr))
    return info


def load_audio(path: Path, sr: int = 16000) -> np.ndarray:
    p = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(path), "-vn",
                        "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"], capture_output=True)
    if p.returncode:
        raise RuntimeError("오디오 추출 실패: " + p.stderr.decode("utf-8", "replace")[-500:])
    return np.frombuffer(p.stdout, dtype=np.float32)
