"""단계별 파이프라인 (+ 단계별 캐시). 강의 자료처럼 단계 버튼 하나씩, 또는 전체 실행이 가능하다.

전사 -> 컷 편집 -> 기획(Claude) -> 이미지 생성 -> 개인정보 탐지 -> 최종 렌더
앞 단계 결과가 캐시에 있으면 재사용하고, 없으면 자동으로 먼저 실행한다.
"""
import json
import shutil
from pathlib import Path

from . import config, cut, illustrate, privacy, render, subtitles, transcribe
from .common import ROOT, load_audio, log, probe

STAGES = ["transcribe", "cut", "plan", "image", "privacy", "render"]
STAGE_LABELS = {"transcribe": "전사", "cut": "컷 편집", "plan": "기획", "image": "이미지 생성",
                "privacy": "개인정보 탐지", "render": "최종 렌더"}
CACHE_FILES = {"transcribe": "transcript.json", "cut": "cut.json", "plan": "plan.json",
               "image": "images.json", "privacy": "privacy.json"}


def _abs(p) -> Path:
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


def work_dir(video: Path, o: dict) -> Path:
    d = _abs(o.get("_work") or _abs(o["work_dir"]) / video.stem)
    d.mkdir(parents=True, exist_ok=True)
    return d


def out_path(video: Path, o: dict) -> Path:
    p = _abs(o["_out"]) if o.get("_out") else _abs(o["out_dir"]) / f"{video.stem}_edited.mp4"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def status(video: Path, o: dict) -> dict:
    w = work_dir(video, o)
    s = {k: (w / f).exists() for k, f in CACHE_FILES.items()}
    s["render"] = out_path(video, o).exists()
    return s


def clear_cache(video: Path, o: dict):
    w = work_dir(video, o)
    shutil.rmtree(w, ignore_errors=True)


def _read(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def _write(p: Path, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _invalidate_after(stage: str, w: Path, out: Path):
    for s in STAGES[STAGES.index(stage) + 1:]:
        f = CACHE_FILES.get(s)
        if f and (w / f).exists():
            (w / f).unlink()


# ------------------------------------------------------------------ 단계 구현
def _st_transcribe(src, o, w, ctx):
    info = probe(src)
    if info["has_audio"]:
        words, sents = transcribe.transcribe(src, o["whisper_model"], o["language"], o["whisper_device"])
    else:
        words, sents = [], []
    data = {"words": words, "sentences": sents}
    _write(w / CACHE_FILES["transcribe"], data)
    return data


def _st_cut(src, o, w, ctx):
    t = ctx["transcribe"]
    info = probe(src)
    words, sents = t["words"], t["sentences"]
    cut_video = w / "cut.mp4"
    if not o["cut"] or not words:
        data = {"cut_video": str(src), "info": info, "words": words, "sentences": sents, "segs": None}
        log("[2/6] 컷 편집: 건너뜀")
    else:
        audio = load_audio(src)
        segs = cut.build_segments(words, audio, info["duration"], info["fps"], o)
        if not segs:
            raise RuntimeError("유지할 구간이 없습니다. 음성이 인식되지 않았을 수 있어요.")
        cwords, csents, total = cut.remap_words(words, sents, segs)
        cut.render_cut(src, segs, info["fps"], info["has_audio"], cut_video, w, o["video_codec"])
        cinfo = probe(cut_video)
        log(f"      {info['duration']:.1f}초 -> {cinfo['duration']:.1f}초 "
            f"({100 - cinfo['duration'] / info['duration'] * 100:.0f}% 단축)")
        data = {"cut_video": str(cut_video), "info": cinfo, "words": cwords, "sentences": csents,
                "segs": [list(s) for s in segs]}
    _write(w / CACHE_FILES["cut"], data)
    return data


def _st_plan(src, o, w, ctx):
    c = ctx["cut"]
    log("[3/6] 설명 일러스트 / 로고 오버레이 기획 중... (Claude)")
    if not (o["illustrations"] or o["overlays"]) or not c["sentences"]:
        data = {"scenes": [], "overlays": []}
    else:
        try:
            data = illustrate.plan(c["sentences"], c["info"]["duration"], o)
        except Exception as e:
            log(f"      기획 단계 실패 -> 건너뜀 (캐시하지 않음): {str(e)[:200]}")
            return {"scenes": [], "overlays": []}
    log(f"      일러스트 {len(data['scenes'])}개, 로고 오버레이 {len(data['overlays'])}개")
    _write(w / CACHE_FILES["plan"], data)
    return data


def _st_image(src, o, w, ctx):
    p = ctx["plan"]
    scenes = illustrate.generate_images(p["scenes"], w, o) if p["scenes"] else []
    if not p["scenes"]:
        log("[4/6] 이미지 생성: 만들 장면 없음")
    logos = illustrate.prepare_logos(p["overlays"], o, w) if p["overlays"] else []
    data = {"scenes": scenes, "logos": logos}
    _write(w / CACHE_FILES["image"], data)
    return data


def _st_privacy(src, o, w, ctx):
    c = ctx["cut"]
    ci = c["info"]
    scan, step = {}, 1
    if o["mosaic"]:
        extra = [x.strip() for x in o["blur_words"].split(",") if x.strip()]
        scan, step = privacy.scan_video(Path(c["cut_video"]), ci["fps"], ci["width"], ci["height"],
                                        ROOT / "models", o["ocr_interval"], o["blur_faces"], extra)
    else:
        log("[5/6] 개인정보 모자이크: 건너뜀")
    mute = privacy.spoken_pii_ranges(c["words"]) if o["mute_spoken_pii"] else []
    data = {"step": step, "scan": {str(k): [list(b) for b in v] for k, v in scan.items()},
            "mute": [list(m) for m in mute]}
    _write(w / CACHE_FILES["privacy"], data)
    return data


def _st_render(src, o, w, ctx):
    c, im, pv = ctx["cut"], ctx["image"], ctx["privacy"]
    ci = c["info"]
    mode = {"cutaway": "full", "center": "center", "pip": "pip"}.get(o["illustration_mode"], "full")
    items = [{**s, "kind": mode} for s in im["scenes"]] + list(im["logos"])
    scan = {int(k): [tuple(b) for b in v] for k, v in pv["scan"].items()}
    subs = None
    if o["subtitles"] and c["words"]:
        subs = w / "subs.ass"
        n = subtitles.write_ass(c["words"], ci["width"], ci["height"], subs)
        log(f"      자막 {n}줄 생성")
    out = out_path(src, o)
    render.final_render(Path(c["cut_video"]), out, ci, scan, pv["step"], items,
                        [tuple(m) for m in pv["mute"]], w, subs, o["video_codec"], o["video_quality"])
    report = {
        "output": str(out),
        "illustrations": [{"start": s["start"], "end": s["end"], "concept": s["concept"], "source": s.get("source")}
                          for s in im["scenes"]],
        "logo_overlays": [{"start": l["start"], "end": l["end"], "logo": l["logo"]} for l in im["logos"]],
        "mosaic": [{"time": round(int(k) * pv["step"] / ci["fps"], 2),
                    "boxes": [{"kind": b[4], "xyxy": b[:4]} for b in v]}
                   for k, v in sorted(pv["scan"].items(), key=lambda x: int(x[0])) if v],
        "muted_audio": [{"start": round(s, 2), "end": round(e, 2), "text": t} for s, e, t in pv["mute"]],
    }
    _write(w / "report.json", report)
    log(f"\n완료: {out}")
    log(f"검수용 리포트(모자이크/일러스트/무음 처리 위치): {w / 'report.json'}")
    return report


RUNNERS = {"transcribe": _st_transcribe, "cut": _st_cut, "plan": _st_plan, "image": _st_image,
           "privacy": _st_privacy, "render": _st_render}


def run(video, target="all", overrides=None, force=False):
    """target: 단계 이름 또는 'all'. force: 대상 단계(all 이면 전부)의 캐시를 무시하고 다시 실행."""
    src = Path(video).resolve()
    o = config.merge(overrides)
    if overrides:
        for k in ("_out", "_work"):
            if overrides.get(k):
                o[k] = overrides[k]
    w = work_dir(src, o)
    last = STAGES[-1] if target == "all" else target
    ctx = {}
    info = probe(src)
    log(f"입력: {src.name} ({info['width']}x{info['height']}, {info['fps']:.2f}fps, {info['duration']:.1f}초)")
    for st in STAGES[:STAGES.index(last) + 1]:
        cache = w / CACHE_FILES[st] if st in CACHE_FILES else None
        forced = force and (target == "all" or st == target)
        if cache and cache.exists() and not forced:
            ctx[st] = _read(cache)
            log(f"[{STAGES.index(st) + 1}/6] {STAGE_LABELS[st]}: 저장된 결과 재사용")
            continue
        if cache and cache.exists():
            cache.unlink()
        if st != "render":
            _invalidate_after(st, w, out_path(src, o))
        ctx[st] = RUNNERS[st](src, o, w, ctx)
    return ctx
