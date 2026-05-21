from __future__ import annotations

from pathlib import Path
import shutil
import unittest
import uuid

from services.channel_sheet_registry import ChannelSheetConfig
from workers.channel_worker import ChannelWorker


class FakeRegistry:
    def __init__(self, channels):
        self.channels = channels

    def enabled_channels(self, max_channels=None):
        return self.channels[:max_channels]


class FakeJobProcessor:
    def __init__(self):
        self.calls = []

    def process_one_video(self, video, text_file, channel_id, channel_cfg, voices, settings, job_row=None):
        self.calls.append(
            {
                "video": video,
                "text_file": text_file,
                "channel_id": channel_id,
                "channel_cfg": channel_cfg,
                "voices": voices,
                "settings": settings,
                "job_row": job_row,
            }
        )
        output = Path(channel_cfg["output_folder"]) / f"{video.stem}.mp4"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"rendered")
        return str(output)


class FakeUploader:
    def __init__(self):
        self.jobs = []

    def upload(self, job):
        self.jobs.append(job)
        return "yt_1"


class ChannelWorkerSheetControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path.cwd() / "runtime" / "test_channel_worker" / uuid.uuid4().hex
        self.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_worker_uses_sheet_channel_values_for_render_and_upload(self) -> None:
        input_folder = self.root / "input"
        input_folder.mkdir()
        video = input_folder / "video.mp4"
        subtitle = input_folder / "video_vi.srt"
        video.write_bytes(b"video")
        subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nhello", encoding="utf-8")
        channel = ChannelSheetConfig(
            channel_id="ch1",
            channel_name="Channel 1",
            input_folder=str(input_folder),
            voice_name="cute.wav",
            voice_path=str(self.root / "voices" / "cute.wav"),
            youtube_oauth_token_json=str(self.root / "tokens" / "ch1.json"),
            privacy_status="private",
            enabled=True,
            daily_limit=1,
            ref_text="sample ref",
            raw={"title": "Sheet title"},
        )
        job_processor = FakeJobProcessor()
        uploader = FakeUploader()
        worker = ChannelWorker(
            FakeRegistry([channel]),
            job_processor,
            uploader,
            {"render_output_dir": str(self.root / "rendered"), "voice_engine": "google"},
        )

        results = worker.process(max_channels=100)

        self.assertEqual(results[0].status, "done")
        self.assertEqual(job_processor.calls[0]["channel_id"], "ch1")
        self.assertEqual(job_processor.calls[0]["job_row"]["voice_name"], "cute.wav")
        self.assertEqual(job_processor.calls[0]["job_row"]["ref_audio_path"], channel.voice_path)
        self.assertEqual(job_processor.calls[0]["settings"]["voice_engine"], "omnivoice_local")
        self.assertEqual(uploader.jobs[0].youtube_token_path, channel.youtube_oauth_token_json)
        self.assertEqual(uploader.jobs[0].privacy_status, "private")


if __name__ == "__main__":
    unittest.main()
