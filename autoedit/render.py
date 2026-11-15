"""최종 합성: 모자이크(OpenCV) -> ffmpeg 파이프 -> 일러스트/로고 오버레이 + 자막 + 음성 개인정보 무음, 한 번에 인코딩."""
import subprocess
from pathlib import Path

import cv2

from .common import FFMPEG, log, video_codec_args
from .privacy import boxes_for_frame, pixelate

FADE = 0.25
BORDER = "0x3B2F2F"


def _item_chain(n, k, it, w, h, fps):
    """오버레이 한 개의 필터 체인과 위치식을 만든다. kind: full | center | pip | logo"""
    d = it["end"] - it["start"]
    portrait = h > w
    kind = it["kind"]
    if kind == "full":
        pre = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
        pos = "0:0"
    else:
        frac = {"center": 0.88 if portrait else 0.62, "pip": 0.62 if portrait else 0.38,
                "logo": 0.24 if portrait else 0.14}[kind]
        cw = int(w * frac) // 2 * 2
        bw = max(4, int(w * 0.005))
        pre = f"scale={cw}:-2,pad=iw+{2 * bw}:ih+{2 * bw}:{bw}:{bw}:color={BORDER}"
        m = int(w * 0.03)
        pos = {"center": "(main_w-overlay_w)/2:(main_h-overlay_h)/2",
               "pip": f"main_w-overlay_w-{m}:{int(h * (0.08 if portrait else 0.05))}",
               "logo": f"{m}:{int(h * (0.08 if portrait else 0.05))}"}[kind]
    img = (f"[{n}:v]{pre},format=rgba,fade=t=in:st=0:d={FADE}:alpha=1,"
           f"fade=t=out:st={max(0.0, d - FADE):.3f}:d={FADE}:alpha=1,setpts=PTS+{it['start']:.3f}/TB[im{k}]")
    return img, pos


def final_render(cut_video: Path, out: Path, info: dict, scan, step, items, mute_ranges, work: Path,
                 subs: Path | None = None, codec="auto", quality=19):
    w, h, fps = info["width"], info["height"], info["fps"]
    cmd = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", f"{fps:.5f}", "-i", "-",
           "-i", str(cut_video)]
    chains, last = [], "0:v"
    for k, it in enumerate(items):
        d = it["end"] - it["start"]
        cmd += ["-loop", "1", "-framerate", f"{fps:.5f}", "-t", f"{d:.3f}", "-i", it["png"]]
        img, pos = _item_chain(k + 2, k, it, w, h, fps)
        chains.append(img)
        chains.append(f"[{last}][im{k}]overlay={pos}:enable='between(t,{it['start']:.3f},{it['end']:.3f})':"
                      f"eof_action=pass:format=auto[v{k}]")
        last = f"v{k}"
    if subs:  # 자막은 오버레이 위에 얹는다 (cwd=work 기준 상대경로로 윈도우 경로 이스케이프 회피)
        chains.append(f"[{last}]ass=filename={subs.name}:fontsdir=C\\\\:/Windows/Fonts[vs]")
        last = "vs"
    chains.append(f"[{last}]format=yuv420p[vout]")
    maps = ["-map", "[vout]"]
    if info["has_audio"]:
        a = ",".join(f"volume=enable='between(t,{s:.3f},{e:.3f})':volume=0" for s, e, _ in mute_ranges) \
            if mute_ranges else "anull"
        chains.append(f"[1:a]{a}[aout]")
        maps += ["-map", "[aout]"]
    graph_file = work / "final_graph.txt"
    graph_file.write_text(";\n".join(chains), encoding="utf-8")
    err_path = work / "final_ffmpeg.log"

    probe = subprocess.run([FFMPEG, "-hide_banner", "-h", "full"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace").stdout
    flag = "-filter_complex_script" if "filter_complex_script" in probe else "-/filter_complex"
    full = cmd + [flag, str(graph_file)] + maps + video_codec_args(codec, quality) + [
        "-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart", str(out)]

    log("[6/6] 모자이크 + 오버레이 + 자막 합성 렌더링 중...")
    cap = cv2.VideoCapture(str(cut_video))
    with open(err_path, "wb") as ef:
        proc = subprocess.Popen(full, stdin=subprocess.PIPE, stderr=ef, cwd=str(work))
        i = 0
        try:
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                for x1, y1, x2, y2, _ in boxes_for_frame(scan, step, i):
                    pixelate(frame, x1, y1, x2, y2)
                proc.stdin.write(frame.tobytes())
                i += 1
                if i % 600 == 0:
                    log(f"      {i}/{info['frames']} 프레임")
            proc.stdin.close()
        except BrokenPipeError:
            pass
        rc = proc.wait()
    cap.release()
    if rc:
        raise RuntimeError("최종 렌더링 실패:\n" + err_path.read_text(errors="replace")[-2000:])
