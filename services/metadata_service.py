from __future__ import annotations

from dataclasses import dataclass
import json
import os
import urllib.request
from typing import Any, Protocol


@dataclass(frozen=True)
class MetadataInput:
    original_title: str = ""
    translated_title: str = ""
    source_url: str = ""
    channel_id: str = ""
    channel_name: str = ""
    channel_description: str = ""
    channel_style_prompt: str = ""
    video_summary: str = ""
    title_template: str = ""
    description_template: str = ""
    tags_default: str = ""


@dataclass(frozen=True)
class GeneratedMetadata:
    final_title: str
    final_description: str
    tags: str


class MetadataGenerator(Protocol):
    def generate(self, metadata_input: MetadataInput) -> GeneratedMetadata:
        raise NotImplementedError


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _format_template(template: str, values: dict[str, str], fallback: str) -> str:
    if not template:
        return fallback
    try:
        return template.format(**values).strip() or fallback
    except Exception:
        return fallback


class TemplateMetadataGenerator:
    """Deterministic Vietnamese fallback when OpenAI is unavailable."""

    def generate(self, metadata_input: MetadataInput) -> GeneratedMetadata:
        base_title = metadata_input.translated_title or metadata_input.original_title or metadata_input.video_summary or "Video moi"
        values = {
            "original_title": metadata_input.original_title,
            "translated_title": metadata_input.translated_title,
            "title": base_title,
            "source_url": metadata_input.source_url,
            "channel_id": metadata_input.channel_id,
            "channel_name": metadata_input.channel_name,
            "channel_description": metadata_input.channel_description,
            "video_summary": metadata_input.video_summary,
        }
        title = _format_template(metadata_input.title_template, values, base_title)
        description_fallback = f"{title}\n\n{metadata_input.channel_description}".strip()
        description = _format_template(metadata_input.description_template, values, description_fallback)
        tags = metadata_input.tags_default or "video, giai tri, shorts"
        return GeneratedMetadata(title[:100], description, tags)


class OpenAIMetadataGenerator:
    """Small OpenAI HTTP client, loaded only when OPENAI_API_KEY exists."""

    def __init__(self, api_key: str, model: str | None = None, urlopen=urllib.request.urlopen):
        self.api_key = api_key
        self.model = model or os.environ.get("OPENAI_METADATA_MODEL", "gpt-4.1-mini")
        self.urlopen = urlopen

    def generate(self, metadata_input: MetadataInput) -> GeneratedMetadata:
        prompt = (
            "Tao metadata YouTube bang tieng Viet. Tieu de tu nhien, hap dan, khong spam. "
            "Tra ve JSON voi final_title, final_description, tags dang chuoi phan tach bang dau phay.\n"
            f"Original title: {metadata_input.original_title}\n"
            f"Translated title: {metadata_input.translated_title}\n"
            f"Source URL: {metadata_input.source_url}\n"
            f"Channel: {metadata_input.channel_name} ({metadata_input.channel_id})\n"
            f"Channel description: {metadata_input.channel_description}\n"
            f"Style: {metadata_input.channel_style_prompt}\n"
            f"Summary: {metadata_input.video_summary}\n"
        )
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "Ban la tro ly viet metadata YouTube tieng Viet."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with self.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
        content = payload["choices"][0]["message"]["content"]
        data = json.loads(content)
        return GeneratedMetadata(
            _clean_text(data.get("final_title"))[:100],
            _clean_text(data.get("final_description")),
            _clean_text(data.get("tags")),
        )


class MetadataService:
    def __init__(self, generator: MetadataGenerator | None = None):
        if generator:
            self.generator = generator
        elif os.environ.get("OPENAI_API_KEY"):
            self.generator = OpenAIMetadataGenerator(os.environ["OPENAI_API_KEY"])
        else:
            self.generator = TemplateMetadataGenerator()

    def generate(self, row: dict, channel_cfg: dict | None = None, force: bool = False) -> dict:
        channel_cfg = channel_cfg or {}
        existing_title = _clean_text(row.get("final_title"))
        existing_description = _clean_text(row.get("final_description"))
        existing_tags = _clean_text(row.get("tags"))
        if not force and existing_title and existing_description and existing_tags:
            return {}

        metadata_input = MetadataInput(
            original_title=_clean_text(row.get("original_title") or row.get("title")),
            translated_title=_clean_text(row.get("translated_title")),
            source_url=_clean_text(row.get("source_url")),
            channel_id=_clean_text(row.get("channel_id")),
            channel_name=_clean_text(channel_cfg.get("channel_name")),
            channel_description=_clean_text(channel_cfg.get("channel_description")),
            channel_style_prompt=_clean_text(channel_cfg.get("channel_style_prompt")),
            video_summary=_clean_text(row.get("video_summary") or row.get("text") or row.get("description")),
            title_template=_clean_text(channel_cfg.get("title_template")),
            description_template=_clean_text(channel_cfg.get("description_template")),
            tags_default=_clean_text(channel_cfg.get("tags_default")),
        )
        generated = self.generator.generate(metadata_input)
        updates = {}
        if force or not existing_title:
            updates["final_title"] = generated.final_title
        if force or not existing_description:
            updates["final_description"] = generated.final_description
        if force or not existing_tags:
            updates["tags"] = generated.tags
        return updates
