from __future__ import annotations

import json
import unittest

from services.metadata_service import MetadataInput, MetadataService, OpenAIMetadataGenerator, TemplateMetadataGenerator


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class MetadataServiceTests(unittest.TestCase):
    def test_template_fallback_generates_vietnamese_metadata(self) -> None:
        service = MetadataService(generator=TemplateMetadataGenerator())

        updates = service.generate(
            {"original_title": "Cute cat", "description": "short summary"},
            {
                "channel_name": "Kenh Test",
                "channel_description": "Kenh giai tri ngan.",
                "title_template": "{channel_name}: {title}",
                "description_template": "{title}\n\nTheo doi {channel_name}",
                "tags_default": "meo,shorts",
            },
        )

        self.assertEqual(updates["final_title"], "Kenh Test: Cute cat")
        self.assertIn("Theo doi Kenh Test", updates["final_description"])
        self.assertEqual(updates["tags"], "meo,shorts")

    def test_does_not_overwrite_existing_metadata_without_force(self) -> None:
        service = MetadataService(generator=TemplateMetadataGenerator())

        updates = service.generate({"final_title": "A", "final_description": "B", "tags": "c"})

        self.assertEqual(updates, {})

    def test_openai_generation_is_mocked(self) -> None:
        payload = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "final_title": "Tieu de AI",
                                "final_description": "Mo ta AI",
                                "tags": "ai,video",
                            }
                        )
                    }
                }
            ]
        }
        generator = OpenAIMetadataGenerator("key", model="mock-model", urlopen=lambda _request, timeout=60: FakeResponse(payload))

        result = generator.generate(MetadataInput(original_title="Original"))

        self.assertEqual(result.final_title, "Tieu de AI")
        self.assertEqual(result.final_description, "Mo ta AI")
        self.assertEqual(result.tags, "ai,video")


if __name__ == "__main__":
    unittest.main()
