import argparse
import sys
from pathlib import Path

from . import cut, pipeline
from .common import log


def main():
    ap = argparse.ArgumentParser(prog="autoedit", description="유튜브 영상 자동 1차 편집기 (웹 UI: ui.bat)")
    ap.add_argument("video", type=Path)
    ap.add_argument("-o", "--output", type=Path, help="결과 파일 (기본: output/<원본>_edited.mp4)")
    ap.add_argument("--stage", default="all", choices=["all"] + pipeline.STAGES, help="특정 단계까지만 실행")
    ap.add_argument("--force", action="store_true", help="대상 단계 캐시 무시하고 다시 실행")
    ap.add_argument("--lang", dest="language")
    ap.add_argument("--model", dest="whisper_model", help="whisper 모델 (large-v3 / medium / small ...)")
    ap.add_argument("--min-silence", type=float, dest="min_silence", help="이 길이(초) 이상 무음만 줄임")
    ap.add_argument("--keep-silence", type=float, dest="keep_silence", help="긴 무음을 이 길이로 줄임")
    ap.add_argument("--silence-db", type=float, dest="silence_db")
    ap.add_argument("--fillers", help="제거할 필러워드(쉼표 구분)")
    ap.add_argument("--no-cut", action="store_false", dest="cut", default=None)
    ap.add_argument("--no-illust", action="store_false", dest="illustrations", default=None)
    ap.add_argument("--no-overlay", action="store_false", dest="overlays", default=None, help="로고 오버레이 끄기")
    ap.add_argument("--illust-mode", dest="illustration_mode", choices=["cutaway", "center", "pip"])
    ap.add_argument("--illust-per-min", type=float, dest="max_scenes_per_min")
    ap.add_argument("--no-privacy", action="store_false", dest="mosaic", default=None)
    ap.add_argument("--blur-faces", action="store_true", dest="blur_faces", default=None, help="얼굴도 모자이크(본인 포함)")
    ap.add_argument("--blur-words", dest="blur_words", help="추가로 가릴 단어(쉼표 구분)")
    ap.add_argument("--ocr-interval", type=float, dest="ocr_interval")
    ap.add_argument("--mute-spoken", action="store_true", dest="mute_spoken_pii", default=None, help="말로 읽은 번호/이메일 음소거")
    ap.add_argument("--no-subs", action="store_false", dest="subtitles", default=None)
    ap.add_argument("--work", type=Path, dest="_work")
    a = vars(ap.parse_args())
    video, target, force, out = a.pop("video"), a.pop("stage"), a.pop("force"), a.pop("output")
    if out:
        a["_out"] = str(out)
    if a.get("_work"):
        a["_work"] = str(a["_work"])
    overrides = {k: v for k, v in a.items() if v is not None}
    try:
        pipeline.run(video, target, overrides, force)
    except Exception as e:
        log(f"\n오류: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
