"""inbox/ 폴더를 감시하다가 새 영상이 들어오면 자동 편집 -> output/ 저장, 원본은 inbox/done/ 으로 이동."""
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INBOX, DONE, OUT, WORK = ROOT / "inbox", ROOT / "inbox" / "done", ROOT / "output", ROOT / "work"
EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
POLL = 5  # 초


def stable(p: Path) -> bool:
    """파일 복사가 끝났는지(크기가 안 변하는지) 확인."""
    try:
        a = p.stat().st_size
        time.sleep(POLL)
        return a > 0 and a == p.stat().st_size
    except OSError:
        return False


def process(p: Path):
    out = OUT / f"{p.stem}_edited.mp4"
    print(f"\n=== 처리 시작: {p.name} ===", flush=True)
    r = subprocess.run([sys.executable, "-m", "autoedit", str(p), "-o", str(out),
                        "--work", str(WORK / p.stem), *sys.argv[1:]], cwd=ROOT)
    if r.returncode == 0:
        shutil.move(str(p), str(DONE / p.name))
        print(f"=== 완료: {out} (원본은 inbox/done 으로 이동) ===", flush=True)
    else:
        failed = p.with_name(p.name + ".failed")
        p.rename(failed)
        print(f"=== 실패: {p.name} -> {failed.name} 로 표시. 위 로그를 확인하세요 ===", flush=True)


def main():
    for d in (INBOX, DONE, OUT, WORK):
        d.mkdir(parents=True, exist_ok=True)
    print(f"감시 중: {INBOX}\n영상 파일을 이 폴더에 넣으세요. (종료: Ctrl+C)", flush=True)
    while True:
        for p in sorted(INBOX.iterdir()):
            if p.is_file() and p.suffix.lower() in EXTS and stable(p):
                process(p)
        time.sleep(POLL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("종료합니다.")
