from __future__ import annotations

from pathlib import Path
import json
import os
from typing import Any


DEFAULT_ENV_FILE = ".env"


def load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_env_file(path: str | Path) -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _coerce_like(current_value: Any, value: str) -> Any:
    if isinstance(current_value, bool):
        return value.strip().lower() in {"true", "1", "yes", "y", "on"}
    if isinstance(current_value, int) and not isinstance(current_value, bool):
        try:
            return int(value)
        except ValueError:
            return current_value
    if isinstance(current_value, float):
        try:
            return float(value)
        except ValueError:
            return current_value
    if isinstance(current_value, list):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


def apply_env_overrides(settings: dict, env: dict[str, str] | None = None, prefix: str = "YT_") -> dict:
    env_values = env if env is not None else os.environ
    merged = dict(settings)
    for key, current_value in settings.items():
        env_key = f"{prefix}{key}".upper()
        if env_key in env_values:
            merged[key] = _coerce_like(current_value, env_values[env_key])

    legacy_aliases = {
        "YOUTUBE_TOKEN_PICKLE_PATH": ("youtube_oauth_token_json", "YOUTUBE_OAUTH_TOKEN_JSON"),
        "YOUTUBE_DEFAULT_PRIVACY": ("youtube_default_privacy", "YOUTUBE_DEFAULT_PRIVACY"),
        "YOUTUBE_CATEGORY_ID": ("youtube_default_category_id", "YOUTUBE_DEFAULT_CATEGORY_ID"),
        "SUBTITLE_TRANSLATION_API_KEY": ("subtitle_translation_api_key", "SUBTITLE_TRANSLATION_API_KEY"),
        "DASHSCOPE_API_KEY": ("subtitle_translation_api_key", "SUBTITLE_TRANSLATION_API_KEY"),
        "QWEN_API_KEY": ("subtitle_translation_api_key", "SUBTITLE_TRANSLATION_API_KEY"),
        "OPENAI_API_KEY": ("subtitle_translation_api_key", "SUBTITLE_TRANSLATION_API_KEY"),
        "SUBTITLE_TRANSLATION_BASE_URL": ("subtitle_translation_base_url", "SUBTITLE_TRANSLATION_BASE_URL"),
        "SUBTITLE_TRANSLATION_MODEL": ("subtitle_translation_model", "SUBTITLE_TRANSLATION_MODEL"),
        "OMNIVOICE_MODEL_PATH": ("omnivoice_model_path", "OMNIVOICE_MODEL_PATH"),
    }
    for env_key, (setting_key, canonical_env_name) in legacy_aliases.items():
        prefixed_key = f"{prefix}{env_key}"
        canonical_prefixed_key = f"{prefix}{canonical_env_name}"
        if canonical_prefixed_key in env_values:
            continue
        if prefixed_key in env_values:
            merged[setting_key] = env_values[prefixed_key]
        elif env_key in env_values:
            merged[setting_key] = env_values[env_key]
    return merged


class ConfigLoader:
    """Loads JSON settings and optional environment overrides."""

    def __init__(self, root: Path, env_file: str = DEFAULT_ENV_FILE, env_prefix: str = "YT_"):
        self.root = root
        self.env_file = env_file
        self.env_prefix = env_prefix

    def load_settings(self, settings_path: str | Path = "configs/settings.json") -> dict:
        path = Path(settings_path)
        if not path.is_absolute():
            path = self.root / path
        settings = load_json(path)

        file_env = load_env_file(self.root / self.env_file)
        merged_env = {**file_env, **os.environ}
        return apply_env_overrides(settings, merged_env, self.env_prefix)
