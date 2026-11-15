"""옵션 정의: .env(기본값) -> 웹UI/CLI 에서 덮어쓰기. 강의 자료의 설정 항목과 같은 이름을 쓴다."""
import os

from . import common  # noqa: F401  (.env 로딩)


def _b(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on", "y")


def _env(name, default):
    return os.environ.get(name, default)


def defaults() -> dict:
    return {
        # 컷 편집
        "cut": _b(_env("CUT", "true")),
        "silence_db": float(_env("SILENCE_DB", "-35")),
        "min_silence": float(_env("MIN_SILENCE", "0.6")),
        "keep_silence": float(_env("KEEP_SILENCE", "0.3")),
        "remove_stutters": _b(_env("REMOVE_STUTTERS", "true")),
        "fillers": _env("FILLERS", "어,음,으,엄,흠,아,에,으음,어음"),
        # 음성 인식
        "whisper_model": _env("WHISPER_MODEL", "large-v3"),
        "whisper_device": _env("WHISPER_DEVICE", "auto"),
        "language": _env("LANGUAGE", "ko"),
        # 설명 일러스트
        "illustrations": _b(_env("ILLUSTRATIONS", "true")),
        "illustration_mode": _env("ILLUSTRATION_MODE", "cutaway"),  # cutaway | center | pip
        "max_scenes_per_min": float(_env("MAX_SCENES_PER_MIN", "1.5")),
        "claude_model": _env("CLAUDE_MODEL", _env("AUTOEDIT_MODEL", "claude-sonnet-5-5")),
        "image_provider": _env("IMAGE_PROVIDER", "auto"),  # auto | openai | svg
        "image_model": _env("IMAGE_MODEL", "gpt-image-1"),
        "image_quality": _env("IMAGE_QUALITY", "medium"),
        "image_concurrency": int(_env("IMAGE_CONCURRENCY", "6")),  # 이미지 동시 생성 수(병렬)
        # 로고/아이콘 오버레이
        "overlays": _b(_env("OVERLAYS", "true")),
        "overlays_per_min": float(_env("OVERLAYS_PER_MIN", "4.0")),
        "logo_dir": _env("LOGO_DIR", "./로고"),
        # 개인정보
        "mosaic": _b(_env("MOSAIC", "true")),
        "ocr_interval": float(_env("OCR_INTERVAL", "0.5")),
        "blur_faces": _b(_env("BLUR_FACES", "false")),
        "blur_words": _env("BLUR_WORDS", ""),
        "mute_spoken_pii": _b(_env("MUTE_SPOKEN_PII", "false")),
        # 자막 / 출력
        "subtitles": _b(_env("SUBTITLES", "true")),
        "video_codec": _env("VIDEO_CODEC", "auto"),
        "video_quality": int(_env("VIDEO_QUALITY", "19")),
        "out_dir": _env("OUT_DIR", "./output"),
        "work_dir": _env("WORK_DIR", "./work"),
    }


def merge(overrides: dict | None) -> dict:
    o = defaults()
    for k, v in (overrides or {}).items():
        if k not in o or v is None:
            continue
        t = type(o[k])
        try:
            o[k] = _b(v) if t is bool else t(v)
        except (TypeError, ValueError):
            pass
    return o
