from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from processors.douyin_render_processor import DouyinRenderEngine, DouyinRenderProcessor


class FakeRenderRepository:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []

    def load_render_jobs(self, worksheet_name: str):
        self.loaded_worksheet_name = worksheet_name
        return self.rows

    def update_render_result(
        self,
        worksheet_name: str,
        row_number: int,
        render_status: str,
        audio_path: str = "",
        rendered_video_path: str = "",
        render_error: str = "",
    ) -> None:
        self.updates.append(
            {
                "worksheet_name": worksheet_name,
                "row_number": row_number,
                "render_status": render_status,
                "audio_path": audio_path,
                "rendered_video_path": rendered_video_path,
                "render_error": render_error,
            }
        )


class FakeRenderEngine(DouyinRenderEngine):
    def __init__(self, root: Path):
        super().__init__(root)
        self.rendered = []

    def extract_metadata(self, source_video: Path) -> dict:
        return {"format": {"filename": str(source_video)}}

    def extract_audio(self, source_video: Path, temp_dir: Path) -> Path:
        temp_dir.mkdir(parents=True, exist_ok=True)
        audio = temp_dir / "audio.m4a"
        audio.write_bytes(b"audio")
        return audio

    def create_tts_audio(self, row: dict, settings: dict, temp_dir: Path) -> Path | None:
        if not row.get("tts_text"):
            return None
        temp_dir.mkdir(parents=True, exist_ok=True)
        audio = temp_dir / "tts.mp3"
        audio.write_bytes(b"tts")
        return audio

    def render_video(self, source_video: Path, audio_path: Path, output_video: Path) -> None:
        output_video.parent.mkdir(parents=True, exist_ok=True)
        output_video.write_bytes(b"rendered")
        self.rendered.append((source_video, audio_path, output_video))


class DouyinRenderProcessorTests(unittest.TestCase):
    def test_renders_pending_row_and_updates_sheet(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.mp4"
            source.write_bytes(b"video")
            repository = FakeRenderRepository([(2, {"source_video_path": str(source), "render_status": "pending"})])
            engine = FakeRenderEngine(root)

            results = DouyinRenderProcessor(repository, engine).process(
                {
                    "render_sheet_name": "Douyin Render",
                    "render_status_new": "pending",
                    "render_status_processing": "rendering",
                    "render_status_done": "ready",
                    "render_status_error": "failed",
                    "render_output_dir": "runtime/rendered",
                    "render_temp_dir": "runtime/temp/douyin_render",
                    "video_exts": [".mp4"],
                }
            )

        self.assertEqual(repository.loaded_worksheet_name, "Douyin Render")
        self.assertEqual(results[0].status, "ready")
        self.assertTrue(results[0].rendered_video_path.endswith("source_rendered.mp4"))
        self.assertEqual(repository.updates[0]["render_status"], "rendering")
        self.assertEqual(repository.updates[1]["render_status"], "ready")
        self.assertTrue(repository.updates[1]["audio_path"])
        self.assertTrue(repository.updates[1]["rendered_video_path"])

    def test_uses_tts_audio_when_text_is_present(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.mp4"
            source.write_bytes(b"video")
            repository = FakeRenderRepository([(2, {"source_video_path": str(source), "tts_text": "hello"})])
            engine = FakeRenderEngine(root)

            DouyinRenderProcessor(repository, engine).process({"video_exts": [".mp4"]})

        self.assertTrue(str(engine.rendered[0][1]).endswith("tts.mp3"))

    def test_skips_ready_rows(self) -> None:
        repository = FakeRenderRepository([(2, {"source_video_path": "x.mp4", "render_status": "ready"})])

        results = DouyinRenderProcessor(repository, FakeRenderEngine(Path.cwd())).process({"render_status_done": "ready"})

        self.assertEqual(results, [])
        self.assertEqual(repository.updates, [])

    def test_rejects_missing_source_video(self) -> None:
        repository = FakeRenderRepository([(2, {"source_video_path": "missing.mp4", "render_status": "pending"})])

        results = DouyinRenderProcessor(repository, FakeRenderEngine(Path.cwd())).process({"render_status_new": "pending"})

        self.assertEqual(results[0].status, "failed")
        self.assertIn("source_video_path not found", results[0].error)
        self.assertEqual(repository.updates[0]["render_status"], "failed")

    def test_rejects_unsupported_extension(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.txt"
            source.write_text("not video", encoding="utf-8")
            repository = FakeRenderRepository([(2, {"source_video_path": str(source)})])

            results = DouyinRenderProcessor(repository, FakeRenderEngine(root)).process({"video_exts": [".mp4"]})

        self.assertIn("unsupported source video extension", results[0].error)


if __name__ == "__main__":
    unittest.main()
