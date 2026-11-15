"""음성 -> 단어 단위 타임스탬프 대본 (faster-whisper, 로컬 실행)."""
from pathlib import Path

from .common import cuda_ok, load_audio, log

# Whisper는 "어/음" 같은 군더더기를 기본적으로 지워버리는 경향이 있어, 프롬프트로 그대로 받아적게 유도한다.
PROMPTS = {
    "ko": "음, 어... 그러니까 어, 이게 음 그렇거든요. 아 네, 어 그래서 음 이렇게 됩니다.",
    "en": "Um, uh, so, like, you know, uh, this is, um, how it works.",
}


def _transcribe_once(audio, model_name, lang, device, compute):
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device=device, compute_type=compute)
    segs, _ = model.transcribe(
        audio, language=lang, word_timestamps=True, beam_size=5,
        vad_filter=False, condition_on_previous_text=False,
        initial_prompt=PROMPTS.get(lang), temperature=0.0,
    )
    words, sentences = [], []
    for s in segs:
        sentences.append({"s": s.start, "e": s.end, "text": s.text.strip()})
        for w in s.words or []:
            words.append({"s": w.start, "e": w.end, "w": w.word.strip()})
    return words, sentences


def transcribe(video: Path, model_name: str = "large-v3", lang: str = "ko", device: str = "auto"):
    audio = load_audio(video)
    log(f"[1/6] 음성 인식 중... (모델: {model_name})")
    if device == "cpu":
        return _transcribe_once(audio, model_name, lang, "cpu", "int8")
    if cuda_ok():
        try:
            return _transcribe_once(audio, model_name, lang, "cuda", "float16")
        except Exception as e:  # CUDA DLL 부재 등
            log(f"      GPU 사용 불가({type(e).__name__}) -> CPU로 진행합니다")
    else:
        log("      GPU 라이브러리를 불러올 수 없어(보안 정책 등) CPU로 진행합니다 (느릴 수 있음. 빠르게 하려면 --model medium)")
    return _transcribe_once(audio, model_name, lang, "cpu", "int8")

