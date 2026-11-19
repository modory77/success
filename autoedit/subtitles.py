"""자막: 컷 이후 타임라인의 단어 타임스탬프 -> ASS 파일 (영상에 번인)."""
import re
from pathlib import Path

from .common import FONT_NAME


def _t(x: float) -> str:
    x = max(0.0, x)
    h, rem = divmod(x, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def make_cues(words, max_chars=20, max_gap=0.7):
    cues, cur = [], []

    def flush():
        if cur:
            text = " ".join(w["w"] for w in cur).strip()
            text = re.sub(r"\s+([,.!?])", r"\1", text)
            if text:
                cues.append({"s": cur[0]["s"], "e": cur[-1]["e"], "text": text})
            cur.clear()

    for w in words:
        if cur and w["s"] - cur[-1]["e"] > max_gap:
            flush()
        cur.append(w)
        joined = " ".join(x["w"] for x in cur)
        if re.search(r"[.?!…]$", w["w"]) or len(joined) >= max_chars:
            flush()
    flush()
    # 너무 짧은 자막은 최소 노출 시간 확보, 다음 자막과 겹치지 않게
    for i, c in enumerate(cues):
        nxt = cues[i + 1]["s"] if i + 1 < len(cues) else 1e9
        c["e"] = min(max(c["e"] + 0.15, c["s"] + 0.8), nxt - 0.02)
    return [c for c in cues if c["e"] > c["s"]]


def write_ass(words, width, height, path: Path):
    portrait = height > width
    short = min(width, height)
    size = int(short * 0.055)                      # 짧은 변 기준 (세로 영상에서 너무 커지지 않게)
    margin_side = int(width * 0.06)
    # 한 줄에 들어갈 글자 수: 사용 가능한 폭 / 글자 폭(한글은 거의 정사각형)
    max_chars = max(8, min(22, int((width - 2 * margin_side) / (size * 1.02))))
    cues = make_cues(words, max_chars=max_chars)
    # 세로(쇼츠/릴스) 영상은 하단 앱 UI에 가려지지 않도록 위로 올린다
    margin_v = int(height * (0.17 if portrait else 0.07))
    outline = max(2, int(short * 0.004))
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT_NAME},{size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{outline},1,2,{margin_side},{margin_side},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [f"Dialogue: 0,{_t(c['s'])},{_t(c['e'])},Default,,0,0,0,,{c['text']}" for c in cues]
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    return len(cues)
