from __future__ import annotations

from pathlib import Path
ALLOWED_VOICE_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a"}


def _resolve_dir(voices_dir: str | Path) -> Path:
    return Path(voices_dir).expanduser().resolve()


def _validate_voice_name(voice_name: str) -> str:
    name = str(voice_name or "").strip()
    if not name:
        raise FileNotFoundError("voice_name is empty and no default voice is configured")
    candidate = Path(name)
    if candidate.is_absolute() or len(candidate.parts) != 1 or name in {".", ".."}:
        raise ValueError(f"Invalid voice_name, path traversal is not allowed: {voice_name}")
    if candidate.suffix.lower() not in ALLOWED_VOICE_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_VOICE_EXTENSIONS))
        raise ValueError(f"Unsupported voice file extension for {voice_name}. Allowed: {allowed}")
    return name


def list_voice_files(voices_dir: str | Path) -> list[str]:
    """Return allowed voice filenames from a voice directory."""

    root = _resolve_dir(voices_dir)
    if not root.exists():
        return []
    if not root.is_dir():
        raise ValueError(f"voices_dir is not a directory: {root}")
    voices = [
        path.name
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in ALLOWED_VOICE_EXTENSIONS
    ]
    return sorted(voices, key=str.lower)


def resolve_voice_path(
    voice_name: str | None,
    voices_dir: str | Path,
    default_voice_name: str | None = None,
) -> Path:
    """Resolve a configured voice filename to an absolute path under voices_dir."""

    selected = str(voice_name or "").strip() or str(default_voice_name or "").strip()
    safe_name = _validate_voice_name(selected)
    root = _resolve_dir(voices_dir)
    path = (root / safe_name).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Invalid voice_name outside voices_dir: {voice_name}") from exc
    if not path.exists():
        raise FileNotFoundError(f"Voice file not found: {path}")
    if not path.is_file():
        raise FileNotFoundError(f"Voice path is not a file: {path}")
    return path
