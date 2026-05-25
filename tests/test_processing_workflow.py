from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

from services.active_channel_state import ActiveChannelState
from services.processing_workflow import ProcessingWorkflow, SubtitleItem, SubtitleSegment, safe_channel_name, shift_time


class FakeTranscriber:
    def __init__(self) -> None:
        self.videos = []

    def transcribe(self, video_path: Path) -> list[SubtitleSegment]:
        self.videos.append(video_path)
        return [
            SubtitleSegment(0.0, 1.5, "hello"),
            SubtitleSegment(2.0, 4.0, "world"),
        ]


class FakeTranslator:
    def __init__(self) -> None:
        self.batches = []

    def translate_batch(self, batch: list[SubtitleItem]) -> dict[str, str]:
        self.batches.append(batch)
        return {item.id: f"vi {item.text}" for item in batch}


class FakeTTSService:
    def __init__(self) -> None:
        self.calls = []

    def create_voice(self, text: str, output_file: Path, voice_cfg: dict, google_key_dir: str = "") -> None:
        self.calls.append(
            {
                "text": text,
                "output_file": output_file,
                "voice_cfg": voice_cfg,
                "google_key_dir": google_key_dir,
            }
        )
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_bytes(b"voice")


class FakeRenderService:
    def __init__(self) -> None:
        self.calls = []

    def render_video(self, input_video: Path, voice_audio: Path, output_video: Path, channel_cfg: dict) -> None:
        self.calls.append(
            {
                "input_video": input_video,
                "voice_audio": voice_audio,
                "output_video": output_video,
                "channel_cfg": channel_cfg,
            }
        )
        output_video.parent.mkdir(parents=True, exist_ok=True)
        output_video.write_bytes(b"rendered")


class FakeSheetRepository:
    def __init__(self) -> None:
        self.channel_updates = []
        self.upload_rows = []

    def update_channel_fields_by_channel_id(self, channel_id: str, fields: dict, worksheet_name: str = "CHANNEL_CONFIG") -> None:
        self.channel_updates.append(
            {
                "channel_id": channel_id,
                "fields": fields,
                "worksheet_name": worksheet_name,
            }
        )

    def append_row_by_headers(self, worksheet_name: str, row_data: dict) -> int:
        self.upload_rows.append(
            {
                "worksheet_name": worksheet_name,
                "row_data": row_data,
            }
        )
        return len(self.upload_rows) + 1


class FakeLogger:
    def __init__(self) -> None:
        self.worker_calls = []

    def worker(self, event: str, **fields) -> None:
        self.worker_calls.append({"event": event, "fields": fields})


class ProcessingWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        base = Path.home() / ".codex" / "memories"
        if not base.exists():
            base = Path(tempfile.gettempdir())
        self.root = base / f"test_processing_workflow_{uuid.uuid4().hex}"
        self.root.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_generates_and_translates_subtitles_using_existing_folders(self) -> None:
        source_dir = self.root / "legacy_input"
        processing_dir = self.root / "legacy_input" / "DA_XU_LY"
        source_dir.mkdir(parents=True)
        (source_dir / "clip.mp4").write_bytes(b"video")
        active = ActiveChannelState(
            channel_id="channel_002",
            channel_name="Gia Khanh Chanel",
            youtube_token_path="tokens/ch2.pickle",
            source_folder_id="drive_folder_2",
        )
        transcriber = FakeTranscriber()
        translator = FakeTranslator()
        workflow = ProcessingWorkflow(
            self.root,
            {
                "processing_source_dir": str(source_dir),
                "processing_work_dir": str(processing_dir),
                "subtitle_translation_batch_size": 10,
                "subtitle_translation_batch_delay_seconds": 0,
            },
            active,
            transcriber=transcriber,
            translator=translator,
        )

        result = workflow.run()

        self.assertEqual(result.active_channel_id, "channel_002")
        self.assertEqual(result.subtitles_created, 1)
        self.assertEqual(result.subtitles_translated, 1)
        self.assertFalse((source_dir / "clip.mp4").exists())
        self.assertTrue((processing_dir / "clip.mp4").exists())
        self.assertTrue((processing_dir / "clip.srt").exists())
        vi_srt = processing_dir / "clip_vi.srt"
        self.assertTrue(vi_srt.exists())
        self.assertIn("vi hello", vi_srt.read_text(encoding="utf-8"))
        self.assertEqual(transcriber.videos, [source_dir / "clip.mp4"])
        self.assertEqual(len(translator.batches), 1)

    def test_missing_source_folder_is_created_and_does_not_fail(self) -> None:
        source_dir = self.root / "runtime" / "input"
        processing_dir = self.root / "runtime" / "processing"
        active = ActiveChannelState(
            channel_id="channel_002",
            channel_name="Gia Khanh Chanel",
            youtube_token_path="tokens/ch2.pickle",
            source_folder_id="drive_folder_2",
        )
        workflow = ProcessingWorkflow(
            self.root,
            {
                "processing_source_dir": str(source_dir),
                "processing_work_dir": str(processing_dir),
                "subtitle_translation_batch_size": 10,
                "subtitle_translation_batch_delay_seconds": 0,
                "temp_dir": "runtime/temp",
            },
            active,
            transcriber=FakeTranscriber(),
            translator=FakeTranslator(),
            tts_service=FakeTTSService(),
            render_service=FakeRenderService(),
            channel_cfg={"voice_id": "voice_omnivoice_1", "output_folder": str(self.root / "runtime" / "output" / "existing_channel")},
            voices={
                "voice_omnivoice_1": {
                    "active": True,
                    "tts_engine": "omnivoice_local",
                    "ref_audio_path": str(self.root / "voices" / "ref.wav"),
                    "ref_text": "reference voice",
                }
            },
        )

        result = workflow.run()

        self.assertTrue(source_dir.is_dir())
        self.assertTrue(processing_dir.is_dir())
        self.assertEqual(result.subtitles_created, 0)
        self.assertEqual(result.subtitles_translated, 0)
        self.assertEqual(result.videos_rendered, 0)

    def test_voice_clone_and_render_use_channel_voice_config(self) -> None:
        source_dir = self.root / "legacy_input"
        processing_dir = self.root / "legacy_input" / "DA_XU_LY"
        output_dir = self.root / "runtime" / "output" / "channel_001_tin_tuc_noi_bat"
        source_dir.mkdir(parents=True)
        (source_dir / "clip.mp4").write_bytes(b"video")
        active = ActiveChannelState(
            channel_id="channel_002",
            channel_name="Gia Khanh Chanel",
            youtube_token_path="tokens/ch2.pickle",
            source_folder_id="drive_folder_2",
        )
        tts_service = FakeTTSService()
        render_service = FakeRenderService()
        workflow = ProcessingWorkflow(
            self.root,
            {
                "processing_source_dir": str(source_dir),
                "processing_work_dir": str(processing_dir),
                "subtitle_translation_batch_size": 10,
                "subtitle_translation_batch_delay_seconds": 0,
                "temp_dir": "runtime/temp",
            },
            active,
            transcriber=FakeTranscriber(),
            translator=FakeTranslator(),
            tts_service=tts_service,
            render_service=render_service,
            channel_cfg={"voice_id": "voice_omnivoice_1", "output_folder": str(output_dir)},
            voices={
                "voice_omnivoice_1": {
                    "active": True,
                    "tts_engine": "omnivoice_local",
                    "ref_audio_path": str(self.root / "voices" / "ref.wav"),
                    "ref_text": "reference voice",
                }
            },
        )

        result = workflow.run()

        self.assertEqual(result.voice_tracks_created, 1)
        self.assertEqual(result.videos_rendered, 1)
        self.assertTrue(output_dir.is_dir())
        self.assertEqual(tts_service.calls[0]["voice_cfg"]["tts_engine"], "omnivoice_local")
        self.assertEqual(tts_service.calls[0]["voice_cfg"]["omnivoice_model_path"], "")
        self.assertIn("vi hello", tts_service.calls[0]["text"])
        self.assertEqual(render_service.calls[0]["input_video"], processing_dir / "clip.mp4")
        self.assertEqual(render_service.calls[0]["channel_cfg"]["subtitle_path"], str(processing_dir / "clip_vi.srt"))
        self.assertTrue((output_dir / "channel_002_clip.mp4").exists())

    def test_rendered_file_registers_pending_upload_row(self) -> None:
        source_dir = self.root / "legacy_input"
        processing_dir = self.root / "legacy_input" / "DA_XU_LY"
        source_dir.mkdir(parents=True)
        (source_dir / "clip.mp4").write_bytes(b"video")
        active = ActiveChannelState(
            channel_id="channel_002",
            channel_name="Gia Khanh Chanel",
            youtube_token_path="tokens/ch2.pickle",
            source_folder_id="drive_folder_2",
        )
        sheet_repo = FakeSheetRepository()
        workflow = ProcessingWorkflow(
            self.root,
            {
                "processing_source_dir": str(source_dir),
                "processing_work_dir": str(processing_dir),
                "subtitle_translation_batch_size": 10,
                "subtitle_translation_batch_delay_seconds": 0,
                "temp_dir": "runtime/temp",
                "upload_sheet_name": "YouTube Upload Queue",
            },
            active,
            transcriber=FakeTranscriber(),
            translator=FakeTranslator(),
            tts_service=FakeTTSService(),
            render_service=FakeRenderService(),
            sheet_repository=sheet_repo,
            channel_cfg={"voice_id": "voice_omnivoice_1", "output_folder": str(self.root / "runtime" / "output" / "existing_channel")},
            voices={
                "voice_omnivoice_1": {
                    "active": True,
                    "tts_engine": "omnivoice_local",
                    "ref_audio_path": str(self.root / "voices" / "ref.wav"),
                    "ref_text": "reference voice",
                }
            },
        )

        workflow.run()

        self.assertEqual(sheet_repo.upload_rows[0]["worksheet_name"], "YouTube Upload Queue")
        self.assertEqual(sheet_repo.upload_rows[0]["row_data"]["video_path"], str(self.root / "runtime" / "output" / "existing_channel" / "channel_002_clip.mp4"))
        self.assertEqual(sheet_repo.upload_rows[0]["row_data"]["upload_status"], "pending")

    def test_rendered_file_registers_youtube_token_path(self) -> None:
        source_dir = self.root / "legacy_input"
        processing_dir = self.root / "legacy_input" / "DA_XU_LY"
        source_dir.mkdir(parents=True)
        (source_dir / "clip.mp4").write_bytes(b"video")
        active = ActiveChannelState(
            channel_id="channel_002",
            channel_name="Gia Khanh Chanel",
            youtube_token_path="secrets/channel_002_token.pickle",
            source_folder_id="drive_folder_2",
        )
        sheet_repo = FakeSheetRepository()
        workflow = ProcessingWorkflow(
            self.root,
            {
                "processing_source_dir": str(source_dir),
                "processing_work_dir": str(processing_dir),
                "subtitle_translation_batch_size": 10,
                "subtitle_translation_batch_delay_seconds": 0,
                "temp_dir": "runtime/temp",
                "upload_sheet_name": "YouTube Upload Queue",
            },
            active,
            transcriber=FakeTranscriber(),
            translator=FakeTranslator(),
            tts_service=FakeTTSService(),
            render_service=FakeRenderService(),
            sheet_repository=sheet_repo,
            channel_cfg={"voice_id": "voice_omnivoice_1", "output_folder": str(self.root / "runtime" / "output" / "existing_channel")},
            voices={
                "voice_omnivoice_1": {
                    "active": True,
                    "tts_engine": "omnivoice_local",
                    "ref_audio_path": str(self.root / "voices" / "ref.wav"),
                    "ref_text": "reference voice",
                }
            },
        )

        workflow.run()

        self.assertEqual(sheet_repo.upload_rows[0]["row_data"]["youtube_token_path"], "secrets/channel_002_token.pickle")

    def test_workflow_passes_configured_omnivoice_model_path_to_tts(self) -> None:
        source_dir = self.root / "legacy_input"
        processing_dir = self.root / "legacy_input" / "DA_XU_LY"
        source_dir.mkdir(parents=True)
        (source_dir / "clip.mp4").write_bytes(b"video")
        active = ActiveChannelState(
            channel_id="channel_002",
            channel_name="Gia Khanh Chanel",
            youtube_token_path="tokens/ch2.pickle",
            source_folder_id="drive_folder_2",
        )
        tts_service = FakeTTSService()
        workflow = ProcessingWorkflow(
            self.root,
            {
                "processing_source_dir": str(source_dir),
                "processing_work_dir": str(processing_dir),
                "subtitle_translation_batch_size": 10,
                "subtitle_translation_batch_delay_seconds": 0,
                "temp_dir": "runtime/temp",
                "omnivoice_model_path": r"D:\models\OmniVoice",
            },
            active,
            transcriber=FakeTranscriber(),
            translator=FakeTranslator(),
            tts_service=tts_service,
            render_service=FakeRenderService(),
            channel_cfg={"voice_id": "voice_omnivoice_1", "output_folder": str(self.root / "runtime" / "output" / "existing_channel")},
            voices={
                "voice_omnivoice_1": {
                    "active": True,
                    "tts_engine": "omnivoice_local",
                    "ref_audio_path": str(self.root / "voices" / "ref.wav"),
                    "ref_text": "reference voice",
                }
            },
        )

        workflow.run()

        self.assertEqual(tts_service.calls[0]["voice_cfg"]["omnivoice_model_path"], r"D:\models\OmniVoice")

    def test_empty_output_folder_generates_local_folder_and_updates_sheet(self) -> None:
        source_dir = self.root / "legacy_input"
        processing_dir = self.root / "legacy_input" / "DA_XU_LY"
        source_dir.mkdir(parents=True)
        (source_dir / "clip.mp4").write_bytes(b"video")
        active = ActiveChannelState(
            channel_id="channel_002",
            channel_name="Gia Khanh Chanel",
            youtube_token_path="tokens/ch2.pickle",
            source_folder_id="drive_folder_2",
        )
        sheet_repo = FakeSheetRepository()
        workflow = ProcessingWorkflow(
            self.root,
            {
                "processing_source_dir": str(source_dir),
                "processing_work_dir": str(processing_dir),
                "subtitle_translation_batch_size": 10,
                "subtitle_translation_batch_delay_seconds": 0,
                "temp_dir": "runtime/temp",
            },
            active,
            transcriber=FakeTranscriber(),
            translator=FakeTranslator(),
            tts_service=FakeTTSService(),
            render_service=FakeRenderService(),
            sheet_repository=sheet_repo,
            channel_cfg={"voice_id": "voice_omnivoice_1", "output_folder": ""},
            voices={
                "voice_omnivoice_1": {
                    "active": True,
                    "tts_engine": "omnivoice_local",
                    "ref_audio_path": str(self.root / "voices" / "ref.wav"),
                    "ref_text": "reference voice",
                }
            },
        )

        result = workflow.run()
        generated_relative = f"runtime/output/channel_002_{safe_channel_name('Gia Khanh Chanel')}"
        expected_output = self.root / generated_relative

        self.assertEqual(result.videos_rendered, 1)
        self.assertTrue(expected_output.is_dir())
        self.assertEqual(sheet_repo.channel_updates, [{"channel_id": "channel_002", "fields": {"output_folder": generated_relative}, "worksheet_name": "CHANNEL_CONFIG"}])
        self.assertEqual(workflow.channel_cfg["output_folder"], generated_relative)

    def test_existing_output_folder_is_preserved(self) -> None:
        source_dir = self.root / "legacy_input"
        processing_dir = self.root / "legacy_input" / "DA_XU_LY"
        output_dir = self.root / "runtime" / "output" / "existing_channel"
        source_dir.mkdir(parents=True)
        (source_dir / "clip.mp4").write_bytes(b"video")
        active = ActiveChannelState(
            channel_id="channel_002",
            channel_name="Gia Khanh Chanel",
            youtube_token_path="tokens/ch2.pickle",
            source_folder_id="drive_folder_2",
        )
        sheet_repo = FakeSheetRepository()
        workflow = ProcessingWorkflow(
            self.root,
            {
                "processing_source_dir": str(source_dir),
                "processing_work_dir": str(processing_dir),
                "subtitle_translation_batch_size": 10,
                "subtitle_translation_batch_delay_seconds": 0,
                "temp_dir": "runtime/temp",
            },
            active,
            transcriber=FakeTranscriber(),
            translator=FakeTranslator(),
            tts_service=FakeTTSService(),
            render_service=FakeRenderService(),
            sheet_repository=sheet_repo,
            channel_cfg={"voice_id": "voice_omnivoice_1", "output_folder": str(output_dir)},
            voices={
                "voice_omnivoice_1": {
                    "active": True,
                    "tts_engine": "omnivoice_local",
                    "ref_audio_path": str(self.root / "voices" / "ref.wav"),
                    "ref_text": "reference voice",
                }
            },
        )

        result = workflow.run()

        self.assertEqual(result.videos_rendered, 1)
        self.assertTrue(output_dir.is_dir())
        self.assertEqual(sheet_repo.channel_updates, [])
        self.assertEqual(workflow.channel_cfg["output_folder"], str(output_dir))

    def test_shift_time_clamps_to_zero(self) -> None:
        self.assertEqual(shift_time("00:00:01,000 --> 00:00:03,000", seconds_offset=-2), "00:00:00,000 --> 00:00:01,000")

    def test_logger_strips_duplicate_active_channel_fields(self) -> None:
        active = ActiveChannelState(
            channel_id="channel_002",
            channel_name="Gia Khanh Chanel",
            youtube_token_path="tokens/ch2.pickle",
            source_folder_id="drive_folder_2",
        )
        logger = FakeLogger()
        workflow = ProcessingWorkflow(self.root, {}, active, logger=logger)

        workflow.log("processing_started", channel_id="override", channel_name="override", source_folder_id="override", foo="bar")

        self.assertEqual(logger.worker_calls[0]["fields"]["channel_id"], "channel_002")
        self.assertEqual(logger.worker_calls[0]["fields"]["channel_name"], "Gia Khanh Chanel")
        self.assertEqual(logger.worker_calls[0]["fields"]["source_folder_id"], "drive_folder_2")
        self.assertEqual(logger.worker_calls[0]["fields"]["foo"], "bar")


if __name__ == "__main__":
    unittest.main()
