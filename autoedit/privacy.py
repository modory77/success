"""개인정보 탐지: 화면 속 글자(OCR) 패턴 + (선택) 얼굴 + 음성 속 숫자/이메일."""
import re
import urllib.request
from pathlib import Path

import cv2
import numpy as np

from .common import log

PII_PATTERNS = {
    "phone": r"0\d{1,2}[\s\-.]?\d{3,4}[\s\-.]?\d{4}",
    "rrn": r"\d{6}\s?[-~]\s?[1-4]\d{6}",
    "card": r"(?:\d{4}[\s\-]){3}\d{4}",
    "account": r"\d{2,6}-\d{2,6}-\d{2,8}(?:-\d{1,4})?",
    "email": r"[\w.+\-]+\s?@\s?[\w\-]+\.[\w.\-]+",
    "address": r"[가-힣0-9]+(?:로|길)\s?\d+(?:-\d+)?(?:번길)?",
    "biz_no": r"\d{3}-\d{2}-\d{5}",
}
YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/"
             "face_detection_yunet_2023mar.onnx")


def find_pii(text: str, extra_words=()):
    """텍스트에서 (종류, 시작인덱스, 끝인덱스) 목록."""
    hits = []
    for kind, pat in PII_PATTERNS.items():
        for m in re.finditer(pat, text):
            hits.append((kind, m.start(), m.end()))
    for w in extra_words:
        for m in re.finditer(re.escape(w), text):
            hits.append(("keyword", m.start(), m.end()))
    return hits


def _ocr_boxes(ocr, frame, extra_words, scale):
    small = cv2.resize(frame, None, fx=scale, fy=scale) if scale != 1 else frame
    res, _ = ocr(small)
    boxes = []
    for pts, text, conf in res or []:
        hits = find_pii(text, extra_words)
        if not hits:
            continue
        pts = np.array(pts) / scale
        x1, y1 = pts.min(0)
        x2, y2 = pts.max(0)
        n = max(len(text), 1)
        for kind, a, b in hits:
            # 줄 전체가 아니라 매칭된 부분만 (글자 수 비례, 양옆 2글자 여유)
            cw = (x2 - x1) / n
            bx1 = x1 + max(0, a - 2) * cw if (b - a) < n * 0.9 else x1
            bx2 = x1 + min(n, b + 2) * cw if (b - a) < n * 0.9 else x2
            boxes.append((int(bx1), int(y1), int(bx2), int(y2), kind))
    return boxes


def _face_detector(w, h, models_dir: Path):
    path = models_dir / "face_detection_yunet_2023mar.onnx"
    if not path.exists():
        models_dir.mkdir(parents=True, exist_ok=True)
        log("      얼굴 인식 모델 다운로드 중 (약 230KB)...")
        urllib.request.urlretrieve(YUNET_URL, path)
    return cv2.FaceDetectorYN.create(str(path), "", (w, h), 0.7)


def scan_video(video: Path, fps, w, h, models_dir: Path, ocr_interval=0.5, faces=False, extra_words=()):
    """샘플링 프레임별 모자이크 박스를 구한다. 반환: {샘플인덱스: [(x1,y1,x2,y2,kind)]}, step(프레임)"""
    from rapidocr_onnxruntime import RapidOCR
    ocr = RapidOCR()
    fd = _face_detector(w, h, models_dir) if faces else None
    step = max(1, int(round(fps * ocr_interval)))
    scale = min(1.0, 1600 / w)
    cap = cv2.VideoCapture(str(video))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    result, prev_small, prev_boxes, i = {}, None, [], 0
    log(f"[5/6] 개인정보 탐지 중... (프레임 {total}개, {ocr_interval}초 간격 검사)")
    while True:
        ok = cap.grab()
        if not ok:
            break
        if i % step == 0:
            _, frame = cap.retrieve()
            gray = cv2.cvtColor(cv2.resize(frame, (160, 90)), cv2.COLOR_BGR2GRAY)
            if prev_small is not None and np.mean(cv2.absdiff(gray, prev_small)) < 1.2:
                boxes = prev_boxes  # 화면이 거의 안 바뀜 -> 재사용 (속도 최적화)
            else:
                boxes = _ocr_boxes(ocr, frame, extra_words, scale)
                if fd is not None:
                    fd.setInputSize((w, h))
                    _, found = fd.detect(frame)
                    for f in (found if found is not None else []):
                        fx, fy, fw, fh = f[:4]
                        m = 0.25
                        boxes.append((int(fx - fw * m), int(fy - fh * m), int(fx + fw * (1 + m)),
                                      int(fy + fh * (1 + m)), "face"))
                prev_small, prev_boxes = gray, boxes
            result[i // step] = boxes
            if (i // step) % 50 == 0:
                log(f"      {i}/{total} 프레임")
        i += 1
    cap.release()
    return result, step


def boxes_for_frame(scan, step, i):
    """프레임 i에 적용할 박스: 인접 샘플의 박스를 합쳐 깜빡임/놓침을 줄인다."""
    k = i // step
    out = []
    for kk in (k - 1, k, k + 1) if (i % step) < step / 2 else (k, k + 1, k + 2):
        out += scan.get(kk, [])
    return out


def pixelate(frame, x1, y1, x2, y2, margin=8):
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1 - margin), max(0, y1 - margin)
    x2, y2 = min(w, x2 + margin), min(h, y2 + margin)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return
    roi = frame[y1:y2, x1:x2]
    bs = max(10, int((y2 - y1) * 0.6))
    small = cv2.resize(roi, (max(1, (x2 - x1) // bs), max(1, (y2 - y1) // bs)), interpolation=cv2.INTER_LINEAR)
    frame[y1:y2, x1:x2] = cv2.resize(small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)


def spoken_pii_ranges(words, pad=0.1):
    """대본에서 전화번호/이메일 등 말로 읽은 구간(초) 찾기 -> 오디오 무음 처리용."""
    ranges = []
    n = len(words)
    num = lambda t: bool(re.fullmatch(r"[\d\-.]+", t.strip(",")))
    i = 0
    while i < n:
        t = words[i]["w"]
        if "@" in t:
            ranges.append((words[i]["s"] - pad, words[i]["e"] + pad, t))
        elif num(t):
            # 숫자 토큰이 연달아 나오는 구간("010 1234 5678", "010-1234-5678")을 묶는다
            j = i
            while j + 1 < n and num(words[j + 1]["w"]) and words[j + 1]["s"] - words[j]["e"] < 0.6:
                j += 1
            run = words[i:j + 1]
            if sum(c.isdigit() for x in run for c in x["w"]) >= 7:
                ranges.append((run[0]["s"] - pad, run[-1]["e"] + pad, " ".join(x["w"] for x in run)))
            i = j
        i += 1
    merged = []
    for s, e, t in ranges:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(e, merged[-1][1]), merged[-1][2])
        else:
            merged.append((s, e, t))
    return merged

