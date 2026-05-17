from __future__ import annotations
from pathlib import Path
import re


def normalize_stem(name: str) -> str:
    stem = Path(name).stem
    stem = stem.replace('_vi', '').replace('.vi', '')
    return stem.strip().lower()


def find_text_for_video(video_path: Path, folder: Path, priority: list[str]) -> Path | None:
    """Tự bắt file text/sub theo tên video.

    Hỗ trợ:
    - abc.mp4 + abc_vi.srt
    - abc.mp4 + abc.srt
    - abc.mp4 + abc.txt
    - nếu tên lệch nhẹ, dùng normalize_stem để bắt.
    """
    raw_stem = video_path.stem

    direct_candidates = []
    for suffix in priority:
        if suffix.startswith('_') or suffix.startswith('.'):
            direct_candidates.append(folder / f"{raw_stem}{suffix}")
        else:
            direct_candidates.append(folder / f"{raw_stem}.{suffix}")

    for p in direct_candidates:
        if p.exists():
            return p

    target = normalize_stem(video_path.name)
    for p in folder.iterdir():
        if p.is_file() and p.suffix.lower() in {'.srt', '.txt'}:
            if normalize_stem(p.name) == target:
                return p
    return None


def srt_to_plain_text(file_path: Path) -> str:
    text = file_path.read_text(encoding='utf-8-sig', errors='ignore')
    if file_path.suffix.lower() == '.txt':
        return re.sub(r'\s+', ' ', text).strip()

    lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.isdigit():
            continue
        if '-->' in line:
            continue
        lines.append(line)
    return re.sub(r'\s+', ' ', ' '.join(lines)).strip()
