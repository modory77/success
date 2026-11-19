"""기획(Claude) + 이미지 생성(OpenAI gpt-image-1 또는 Claude SVG) + 로고 오버레이 준비."""
import base64
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .common import FONT_NAME, KOREAN_FONT, ROOT, log

W, H = 1920, 1080
LOGO_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}

SCENE_ITEM = {
    "type": "object",
    "properties": {
        "start": {"type": "number", "description": "삽입 시작(초, 문장 시작에 맞춤)"},
        "end": {"type": "number", "description": "삽입 종료(초). 길이 3~6초"},
        "concept": {"type": "string", "description": "그림으로 보여줄 개념과 구도를 구체적으로(영어 가능)"},
        "label": {"type": "string", "description": "화면에 넣을 아주 짧은 글자(6자 이내, 없으면 빈 문자열)"},
    },
    "required": ["start", "end", "concept", "label"],
}
OVERLAY_ITEM = {
    "type": "object",
    "properties": {
        "start": {"type": "number"},
        "end": {"type": "number", "description": "길이 2.5~4초"},
        "logo": {"type": "string", "description": "제공된 로고 이름 중 하나(정확히 일치)"},
    },
    "required": ["start", "end", "logo"],
}

PLAN_SYS = """당신은 유튜브 영상 편집자입니다. 타임스탬프가 붙은 대본을 읽고 두 가지를 기획합니다.
(1) scenes: 시청자의 이해를 돕는 '설명 일러스트'를 삽입할 순간.
- 추상 개념, 작동 원리/과정, 비교, 숫자·구조처럼 말만으로 이해하기 어려운 부분에만. 잡담/인사/감정 표현에는 넣지 않는다.
- 각 장면 3~6초, 문장이 시작하는 시점에 맞춘다. 영상 처음 3초 이내와 마지막 3초는 피한다.
- 장면 사이는 최소 {gap}초. 최대 {maxn}개(더 적어도 좋다).
- concept에는 무엇을 어떤 구도로 그릴지 구체적으로. label은 정말 필요할 때만 6자 이내.
(2) overlays: 화자가 아래 '로고 목록'의 회사/제품/서비스를 언급하는 순간에 그 로고를 구석에 잠깐 띄운다.
- 로고 목록: {logos}
- 목록에 있는 이름이 대본에서 실제로 언급될 때만(말하는 시작 시점). 최대 {maxo}개. 목록이 비어 있으면 빈 배열.
- 같은 로고를 5초 안에 반복하지 않는다."""

SVG_SYS = f"""당신은 일러스트레이터입니다. 요청받은 개념을 설명하는 SVG 한 장을 그립니다.
스타일: 플랫 벡터 일러스트 + 손으로 그린 카툰 느낌.
- 캔버스 viewBox="0 0 {W} {H}", 배경은 따뜻한 크림색(#FFF7E8) 사각형 하나.
- 색은 4~6가지 파스텔/비비드 플랫 컬러(채우기), 외곽선은 짙은 갈색(#3B2F2F) 6~8px, stroke-linecap/linejoin="round".
- 단순한 도형 기반의 귀여운 캐릭터/사물, 그림자 대신 단색 면 분할. 그라디언트·사진 질감 금지.
- 글자는 최소화: 라벨 0~2개, 각 6자 이내, 크게(font-size 64 이상), font-family="Malgun Gothic". 문장 금지.
- 핵심 요소가 화면 중앙 80% 안에 오도록 여백을 둔다. 화살표/숫자/아이콘으로 관계를 보여준다.
- <filter>, <defs id="sketch">는 쓰지 말 것(손그림 흔들림 효과는 후처리로 입힌다). 외부 이미지·스크립트 금지.
- 출력은 <svg ...>...</svg> 코드만. 설명 문장 금지."""

SKETCH_DEFS = (
    '<defs><filter id="sketch" x="-2%" y="-2%" width="104%" height="104%">'
    '<feTurbulence type="fractalNoise" baseFrequency="0.018" numOctaves="2" seed="{seed}" result="n"/>'
    '<feDisplacementMap in="SourceGraphic" in2="n" scale="7" xChannelSelector="R" yChannelSelector="G"/>'
    '</filter></defs>'
)

IMAGE_STYLE = (
    "Flat vector illustration with a hand-drawn cartoon feel: thick dark-brown wobbly outlines, "
    "flat pastel and vivid color fills, no gradients, no photo texture, warm cream (#FFF7E8) background, "
    "simple cute characters and objects, explanatory diagram feeling with arrows/icons. "
    "Keep all important elements in the central area with generous margins (the image may be cropped to 16:9). "
)


def _client():
    import anthropic
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY 가 없습니다 (.env 에 입력). 일러스트/오버레이 기획은 건너뜁니다.")
    return anthropic.Anthropic()


def list_logos(logo_dir: str) -> dict:
    d = Path(logo_dir)
    if not d.is_absolute():
        d = ROOT / logo_dir
    if not d.exists():
        return {}
    return {p.stem: p for p in sorted(d.iterdir()) if p.suffix.lower() in LOGO_EXTS}


# ---------------------------------------------------------------- 기획
def plan(sentences, duration, o) -> dict:
    """대본 -> {'scenes': [...], 'overlays': [...]}"""
    logos = list_logos(o["logo_dir"]) if o["overlays"] else {}
    want_scenes = o["illustrations"]
    maxn = max(1, int(duration / 60 * o["max_scenes_per_min"] + 0.999)) if want_scenes else 0
    maxo = max(1, int(duration / 60 * o["overlays_per_min"] + 0.999)) if logos else 0
    gap = max(8, int(60 / max(o["max_scenes_per_min"], 0.1) / 2))
    script = "\n".join(f"[{s['s']:.1f}s] {s['text']}" for s in sentences)
    tool = {"name": "plan", "description": "영상 편집 기획",
            "input_schema": {"type": "object", "properties": {
                "scenes": {"type": "array", "items": SCENE_ITEM},
                "overlays": {"type": "array", "items": OVERLAY_ITEM}},
                "required": ["scenes", "overlays"]}}
    r = _client().messages.create(
        model=o["claude_model"], max_tokens=6000,
        system=PLAN_SYS.format(gap=gap, maxn=maxn, maxo=maxo, logos=", ".join(logos) or "(없음)"),
        tools=[tool], tool_choice={"type": "tool", "name": "plan"},
        messages=[{"role": "user", "content": f"영상 길이 {duration:.0f}초. 대본:\n{script}"}])
    raw = next(b.input for b in r.content if b.type == "tool_use")

    scenes, last_end = [], -999
    for sc in sorted(raw.get("scenes", []) if want_scenes else [], key=lambda x: x["start"]):
        s, e = float(sc["start"]), min(float(sc["end"]), float(sc["start"]) + 6.0, duration - 1.0)
        if e - s < 2.5 or s < 3.0 or s < last_end + gap - 4:
            continue
        scenes.append({"start": round(s, 2), "end": round(e, 2), "concept": sc["concept"], "label": sc.get("label", "")})
        last_end = e
    scenes = scenes[:maxn]

    overlays, seen = [], {}
    for ov in sorted(raw.get("overlays", []) if logos else [], key=lambda x: x["start"]):
        name = ov["logo"]
        if name not in logos:
            continue
        s, e = float(ov["start"]), min(float(ov["end"]), float(ov["start"]) + 4.0, duration)
        if e - s < 1.5 or s < seen.get(name, -99) + 5:
            continue
        # 일러스트(전체화면)와 겹치면 건너뜀
        if any(s < sc["end"] and e > sc["start"] for sc in scenes) and o["illustration_mode"] == "cutaway":
            continue
        overlays.append({"start": round(s, 2), "end": round(e, 2), "logo": name})
        seen[name] = e
    return {"scenes": scenes, "overlays": overlays[:maxo]}


# ---------------------------------------------------------------- 이미지
def _extract_svg(text):
    m = re.search(r"<svg.*?</svg>", text, re.S)
    if not m:
        raise ValueError("SVG를 찾지 못함")
    return m.group(0)


def _stylize(svg: str, idx: int) -> str:
    """손그림 흔들림 필터를 전체에 입힌다."""
    m = re.search(r"<svg[^>]*>", svg)
    head, body = svg[:m.end()], svg[m.end():]
    body = body[:body.rfind("</svg>")]
    if "xmlns=" not in head:
        head = head.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    # 필터로 가장자리가 흔들리면 투명 틈이 생기므로, 필터 밖에 배경을 한 겹 더 깐다
    bg = f'<rect x="-50" y="-50" width="{W + 100}" height="{H + 100}" fill="#FFF7E8"/>'
    return head + SKETCH_DEFS.format(seed=idx + 3) + bg + f'<g filter="url(#sketch)">{body}</g></svg>'


def render_svg(svg: str, png_path: Path, width=W, height=H):
    import resvg_py
    data = resvg_py.svg_to_bytes(svg_string=svg, width=width, height=height, font_files=[str(KOREAN_FONT)],
                                 font_family=FONT_NAME)
    png_path.write_bytes(bytes(data))


def _openai_image(sc, png_path: Path, o):
    from openai import OpenAI
    label = sc.get("label") or ""
    text_rule = (f'The only text allowed is the short Korean label "{label}", written exactly, large and legible.'
                 if label else "Do not include any text, letters or numbers.")
    prompt = f"{IMAGE_STYLE}{text_rule}\nScene to illustrate: {sc['concept']}"
    r = OpenAI().images.generate(model=o["image_model"], prompt=prompt, size="1536x1024",
                                 quality=o["image_quality"], n=1)
    png_path.write_bytes(base64.b64decode(r.data[0].b64_json))


def _use_openai(o):
    return o["image_provider"].lower() in ("auto", "openai") and bool(os.environ.get("OPENAI_API_KEY"))


def _openai_image_retry(sc, png, o, tries=4):
    """동시에 많이 요청하면 속도 제한(429)에 걸릴 수 있어, 그때만 점점 길게 쉬었다가 재시도한다."""
    import time
    for attempt in range(tries):
        try:
            return _openai_image(sc, png, o)
        except Exception as e:  # noqa: BLE001
            msg = str(e).lower()
            retryable = "429" in msg or "rate" in msg or "timeout" in msg or "overloaded" in msg or "503" in msg
            if "no credits" in msg or "insufficient_quota" in msg or "billing" in msg:
                retryable = False   # 크레딧 부족은 재시도해도 소용없음
            if not retryable or attempt == tries - 1:
                raise
            time.sleep(4 * 2 ** attempt)


def make_image(idx, sc, work: Path, o):
    png = work / f"scene_{idx:02d}.png"
    if _use_openai(o):
        try:
            _openai_image_retry(sc, png, o)
            return {**sc, "png": str(png), "source": "openai"}
        except Exception as e:
            log(f"      장면 {idx}: OpenAI 이미지 실패 -> SVG로 대체 ({str(e)[:140]})")
    last_err = None
    for _ in range(2):
        try:
            r = _client().messages.create(
                model=o["claude_model"], max_tokens=8000, system=SVG_SYS,
                messages=[{"role": "user", "content": f"그릴 개념: {sc['concept']}\n화면 글자(없으면 생략): {sc['label']}"}])
            svg = _stylize(_extract_svg(r.content[0].text), idx)
            (work / f"scene_{idx:02d}.svg").write_text(svg, encoding="utf-8")
            render_svg(svg, png)
            return {**sc, "png": str(png), "source": "svg"}
        except Exception as e:
            last_err = e
    log(f"      장면 {idx} 생성 실패, 건너뜀: {str(last_err)[:140]}")
    return None


def generate_images(scenes, work: Path, o):
    """장면 이미지를 병렬로 생성한다(동시 요청 수 = image_concurrency). 결과 순서는 장면 순서 그대로."""
    import time
    from concurrent.futures import as_completed
    workers = max(1, min(int(o.get("image_concurrency", 6)), len(scenes) or 1))
    log(f"[4/6] 일러스트 이미지 생성 중... ({'OpenAI gpt-image-1' if _use_openai(o) else 'Claude SVG'}, "
        f"{len(scenes)}장, 동시 {workers}장씩)")
    t0, res, done = time.time(), [None] * len(scenes), 0
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(make_image, i, sc, work, o): i for i, sc in enumerate(scenes)}
        for f in as_completed(futs):
            res[futs[f]] = f.result()
            done += 1
            log(f"      {done}/{len(scenes)} 완료 ({time.time() - t0:.0f}초)")
    return [r for r in res if r]


# ---------------------------------------------------------------- 로고
def prepare_logos(overlays, o, work: Path):
    logos = list_logos(o["logo_dir"])
    out = []
    for i, ov in enumerate(overlays):
        p = logos.get(ov["logo"])
        if not p:
            continue
        src = p
        if p.suffix.lower() == ".svg":
            src = work / f"logo_{i:02d}_src.png"
            import resvg_py
            src.write_bytes(bytes(resvg_py.svg_to_bytes(svg_path=str(p), width=600, font_files=[str(KOREAN_FONT)])))
        # 투명 배경 로고도 잘 보이도록 흰 카드 위에 올려 PNG로 저장
        from PIL import Image
        im = Image.open(src).convert("RGBA")
        pad = max(12, im.width // 12)
        card = Image.new("RGBA", (im.width + 2 * pad, im.height + 2 * pad), (255, 255, 255, 255))
        card.alpha_composite(im, (pad, pad))
        png = work / f"logo_{i:02d}.png"
        card.convert("RGB").save(png)
        out.append({**ov, "png": str(png), "kind": "logo"})
    return out
