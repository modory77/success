"""컷 편집: 무음 구간 단축 + 필러워드("어","음") 제거 + 말더듬(같은 단어 반복) 제거.

동작 규칙(강의 설정과 같은 의미):
- MIN_SILENCE 초 이상 이어지는 무음은 KEEP_SILENCE 초만 남기고 줄인다 (앞뒤 절반씩 남김 -> 리듬 유지)
- MIN_SILENCE 보다 짧은 쉼은 그대로 둔다
- SILENCE_DB 보다 작은 소리를 무음으로 본다. 배경소음이 이보다 크면(야외 바람 등) 소음 바닥 +6dB 로 자동 보정
- 필러워드/말더듬은 해당 구간을 통째로 잘라낸다
"""
import re

import numpy as np

from .common import log, run_ffmpeg, video_codec_args

DT = 0.02          # 분석 프레임(초)
WORD_PAD = (0.05, 0.10)   # 단어 앞/뒤 여유


def _norm(t: str) -> str:
    return re.sub(r"[\s.,!?…~\-·'\"]", "", t).lower()


def is_filler(text: str, fillers: set) -> bool:
    t = _norm(text)
    if not t:
        return False
    return t in fillers or (len(set(t)) == 1 and t[0] in fillers)  # "어어", "음음" 등


def find_stutters(words):
    """같은 짧은 단어가 연달아 반복되면("그 그 그") 마지막 하나만 남기고 나머지 인덱스를 반환."""
    out = set()
    for i in range(len(words) - 1):
        a, b = _norm(words[i]["w"]), _norm(words[i + 1]["w"])
        if a and a == b and len(a) <= 3 and words[i + 1]["s"] - words[i]["e"] < 0.6:
            out.add(i)
    return out


def rms_db(audio, sr=16000):
    f = int(sr * DT)
    n = len(audio) // f
    x = audio[:n * f].reshape(n, f)
    return 20 * np.log10(np.sqrt((x ** 2).mean(1)) + 1e-9)


def _runs(mask):
    """True 구간들의 (시작, 끝) 인덱스 목록."""
    if not mask.any():
        return []
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def build_segments(words, audio, duration, fps, o):
    n = int(duration / DT) + 2
    fillers = set(f.strip() for f in o["fillers"].split(",") if f.strip())
    stut = find_stutters(words) if o["remove_stutters"] else set()
    rm_idx = {i for i, w in enumerate(words) if is_filler(w["w"], fillers)} | stut

    def sl(s, e):
        return slice(max(0, int(s / DT)), min(n, int(np.ceil(e / DT))))

    voiced = np.zeros(n, bool)
    forbid = np.zeros(n, bool)
    for i, w in enumerate(words):
        if i in rm_idx:
            forbid[sl(w["s"] + 0.01, w["e"] - 0.01)] = True
        else:
            voiced[sl(w["s"] - WORD_PAD[0], w["e"] + WORD_PAD[1])] = True
    voiced &= ~forbid

    # 소리 크기 기반: 말 외에 일정 시간 이어지는 큰 소리(웃음/박수/음악)는 살린다
    if audio is not None and len(audio):
        db = np.full(n, -120.0)
        d = rms_db(audio)
        db[:min(n, len(d))] = d[:n]
        floor = np.percentile(db[~voiced & ~forbid], 10) if (~voiced & ~forbid).any() else -90
        thr = max(o["silence_db"], floor + 6)
        loud = (db > thr) & ~voiced & ~forbid
        for a, b in _runs(loud):
            if (b - a) * DT >= 0.4:
                voiced[a:b] = True
        log(f"      무음 기준 {thr:.0f}dB (설정 {o['silence_db']:.0f}dB, 배경소음 약 {floor:.0f}dB)")

    keep = voiced.copy()
    k = int(round(o["keep_silence"] / 2 / DT))
    for a, b in _runs(~voiced):
        dur = (b - a) * DT
        if dur < o["min_silence"] and a > 0 and b < n - 1:
            keep[a:b] = True               # 짧은 쉼은 유지
        else:                              # 긴 무음은 양끝 keep_silence/2 만 남김
            ka = 0 if a == 0 else k
            kb = 0 if b >= n - 1 else k
            keep[a:a + ka] = True
            keep[max(a, b - kb):b] = True
    keep &= ~forbid

    segs = []
    for a, b in _runs(keep):
        s, e = a * DT, min(duration, b * DT)
        s2, e2 = round(s * fps) / fps, round(e * fps) / fps   # 프레임 격자에 스냅 -> A/V 길이 일치
        if segs and s2 <= segs[-1][1] + 1 / fps:
            segs[-1] = (segs[-1][0], max(segs[-1][1], e2))
        elif e2 - s2 >= 3 / fps:
            segs.append((s2, e2))
    n_f = sum(1 for i in rm_idx if i not in stut)
    log(f"[2/6] 컷 편집: 필러워드 {n_f}개, 말더듬 {len(stut)}개 제거, 유지 구간 {len(segs)}개")
    return segs


def timeline_map(segs):
    """원본 시간 -> 컷 후 시간 변환 함수."""
    starts, acc = [], 0.0
    for s, e in segs:
        starts.append(acc)
        acc += e - s

    def f(t):
        for (s, e), ns in zip(segs, starts):
            if s <= t < e:
                return ns + (t - s)
        return None
    f.total = acc
    return f


def remap_words(words, sentences, segs, drop=()):
    """원본 대본을 컷 이후 시간으로 변환. 잘려나간 단어는 제외."""
    f = timeline_map(segs)
    nw = []
    for w in words:
        mid = f((w["s"] + w["e"]) / 2)
        if mid is not None:
            d = w["e"] - w["s"]
            nw.append({"s": max(0.0, mid - d / 2), "e": mid + d / 2, "w": w["w"]})
    ns = []
    for s in sentences:
        a, b = f(s["s"] + 0.01), f(max(s["s"] + 0.02, s["e"] - 0.05))
        if a is not None and b is not None and b > a:
            ns.append({"s": a, "e": b, "text": s["text"]})
        elif a is not None:
            ns.append({"s": a, "e": a + 1.0, "text": s["text"]})
    return nw, ns, f.total


def render_cut(src, segs, fps, has_audio, out, work, codec="auto"):
    sel = "+".join(f"gte(t,{s - 0.5 / fps:.5f})*lt(t,{e - 0.5 / fps:.5f})" for s, e in segs)
    parts = [f"[0:v]fps={fps:.5f},select='{sel}',setpts=N/({fps:.5f}*TB)[v]"]
    maps = ["-map", "[v]"]
    if has_audio:
        fade = 0.008
        lbl = []
        for i, (s, e) in enumerate(segs):
            d = e - s
            parts.append(f"[0:a]atrim={s:.5f}:{e:.5f},asetpts=PTS-STARTPTS,"
                         f"afade=t=in:d={fade},afade=t=out:st={max(0, d - fade):.5f}:d={fade}[a{i}]")
            lbl.append(f"[a{i}]")
        parts.append("".join(lbl) + f"concat=n={len(segs)}:v=0:a=1[a]")
        maps += ["-map", "[a]"]
    graph = ";\n".join(parts)
    log("      컷 영상 렌더링 중...")
    run_ffmpeg(["-i", str(src)] + maps + video_codec_args(codec, 14, "veryfast") +
               ["-c:a", "aac", "-b:a", "256k", str(out)],
               graph=graph, graph_file=work / "cut_graph.txt")
