# Project Review

## Current Structure

This project is a Google Sheet controlled video processing pipeline. The runnable
code is intentionally small:

- `pipeline.py` is the entrypoint and orchestration layer.
- `processors/sheet_client.py` reads and updates Google Sheets.
- `processors/text_matcher.py` matches videos to subtitle or text files.
- `processors/tts_engine.py` creates narration audio.
- `processors/render_engine.py` runs FFmpeg.
- `sheets_templates/*.csv` define the required Google Sheet tabs.

Root-level documents describe a larger future YouTube automation system, but the
current implementation is focused on rendering prepared videos.

## Current Automation Flow

1. Load `configs/settings.json`.
2. Connect to Google Sheets using the configured service account.
3. Read channel, voice, music, overlay, render preset, and queue rows.
4. If `process_queue_only` is false, scan enabled channel input folders.
5. If `process_queue_only` is true, process `VIDEO_QUEUE` rows with `NEW`.
6. Match each video to `_vi.srt`, `.vi.srt`, `.srt`, or `.txt`.
7. Convert text/subtitles to plain text.
8. Generate temporary TTS audio.
9. Render final video with FFmpeg.
10. Update queue status when running in queue mode.

## Important Files

- `pipeline.py`: current orchestration and compatibility entrypoint.
- `processors/sheet_client.py`: low-level Google Sheet client.
- `repositories/sheet_repository.py`: Phase 1 repository wrapper for Sheet data.
- `services/text_service.py`: Phase 1 text matching and parsing service.
- `services/tts_service.py`: Phase 1 TTS service wrapper.
- `services/render_service.py`: Phase 1 render service wrapper.
- `processors/queue_processor.py`: Phase 1 queue-mode orchestration.
- `processors/folder_processor.py`: Phase 1 folder-mode orchestration.

## Bottlenecks

- FFmpeg rendering is synchronous and single-process.
- Google Sheet reads happen as full worksheet reads.
- Queue rows are not locked, so multiple workers could process the same job.
- TTS output is always temporary and not cached.
- Failed NVENC renders do not automatically retry with `libx264`.

## Potential Errors

- Missing Google credentials or wrong spreadsheet ID stops startup.
- Missing `input_folder`, `output_folder`, video, text, music, or logo paths can
  fail late in the job.
- `local_command` TTS uses `shell=True`; commands must come from trusted config.
- Queue update failures are mostly swallowed after job failure.
- Text output can be empty after SRT cleanup.
- Logo and FFmpeg overlay expressions are passed directly from Sheet values.

## Duplicate Or Overloaded Logic

- `pipeline.py` previously mixed Sheet parsing, config merging, queue processing,
  folder scanning, TTS, text conversion, and render orchestration.
- Sheet row normalization and runtime processing were coupled.
- Queue and folder mode shared job execution logic indirectly through
  `process_one_video`, but each mode handled discovery and validation inline.

## Refactor Roadmap

### Phase 1 - Behavior-Preserving Extraction

- Add `SheetRepository`.
- Add `TextService`.
- Add `TTSService`.
- Add `RenderService`.
- Add `QueueProcessor`.
- Add `FolderProcessor`.
- Keep `pipeline.py` and old function names working.
- Add small tests for pure logic.

### Phase 2 - Validation And Logging

- Validate required Sheet tabs and columns before processing.
- Validate paths and FFmpeg availability before starting a job.
- Write logs to `runtime/logs`.
- Keep secrets and credential paths out of logs.

Phase 2 progress:

- Added `configs/config_loader.py` for JSON settings plus `.env` and environment
  overrides.
- Added `logs/structured_logger.py` for JSONL app, error, retry, render, and
  upload log streams.
- Added `utils/retry.py` with exponential backoff wrappers for Google APIs,
  Selenium, FFmpeg, and HTTP operations.
- Injected retry/logging dependencies into the repository, TTS service, render
  service, and processors.
- Added `repositories/queue_persistence.py` as a no-op persistence contract for
  resumable jobs and failed job recovery.

Architecture decisions:

- Keep `pipeline.py` as the backward-compatible entrypoint.
- Keep Google Sheet as the source of truth for the active queue.
- Use no-op implementations where Phase 2 prepares architecture but should not
  change business behavior.
- Use standard library only for config, logging, and retry utilities.

Remaining technical debt:

- `print()` is still the visible runtime output; structured logs are additive.
- Sheet row validation is still partial and should become explicit before render.
- FFmpeg command construction is still inside `processors/render_engine.py`.
- Queue persistence is prepared as an interface but not backed by disk/database
  storage yet.
- Retry policy is global by default; later phases may need per-operation limits.

Next-phase recommendations:

- Add dry-run validation that checks Sheet rows, file paths, and FFmpeg before
  processing.
- Split FFmpeg command building from execution and test command output directly.
- Add a file-backed queue state store under `runtime/state`.
- Add explicit CLI flags for `--queue`, `--folder`, `--job-id`, and
  `--channel-id`.

### Phase 3 - CLI Controls

- Add `--dry-run`.
- Add `--job-id`.
- Add `--channel-id`.
- Add explicit `--queue` and `--folder` modes.

### Phase 3 - Docker, Isolation, And Worker Preparation

Phase 3 progress:

- Added `Dockerfile`, `docker-compose.yml`, and `.dockerignore`.
- Docker runtime installs Python dependencies and system `ffmpeg`.
- Compose mounts persistent volumes for `runtime/logs`, `runtime/state`, and
  `runtime/temp`.
- Added optional Selenium isolation in
  `integrations/selenium/browser_manager.py`.
- Added Telegram monitoring hooks in `integrations/telegram/notifier.py`.
- Added upload worker scaffold in `workers/upload_worker.py` without enabling
  YouTube uploads.
- Added crash-safe JSON queue state storage in
  `repositories/queue_persistence.py`.
- Queue mode now records job state under `runtime/state/queue` while keeping
  Google Sheet as the active source of truth.

Docker architecture:

```text
host runtime/logs  -> /app/runtime/logs
host runtime/state -> /app/runtime/state
host runtime/temp  -> /app/runtime/temp
host configs       -> /app/configs:ro
```

The container default command remains:

```text
python pipeline.py
```

Queue architecture:

- Google Sheet remains the control plane.
- `JsonQueuePersistence` stores local crash recovery snapshots.
- `NullQueuePersistence` remains available for tests and no-op mode.
- Failed jobs can be recovered later from persisted `ERROR` states.

Worker strategy:

- `UploadWorker` only processes supplied `READY_UPLOAD` job states.
- It accepts an injected upload client, queue persistence, notifier, and logger.
- With no upload client configured, it skips safely instead of attempting upload.

Selenium isolation strategy:

- `BrowserManager` accepts a driver factory instead of importing Selenium at
  module load time.
- Browser startup and operations use retry wrappers.
- Cleanup always calls `quit()` when available.
- Crash recovery is modeled as cleanup followed by a fresh start.

Next scaling recommendations:

- Add a real YouTube upload client behind `UploadClient`.
- Add a worker entrypoint separate from `pipeline.py`.
- Add file locking around `JsonQueuePersistence` if multiple local workers share
  the same state directory.
- Add browser profile volume mapping only when Selenium upload is actively used.
- Add health checks and explicit dry-run validation before running in Docker.

### Phase 4 - Testable Render And TTS

- Split FFmpeg command construction from execution.
- Add NVENC fallback to `libx264`.
- Add typed TTS adapters: Google, local command, and mock.
- Add TTS caching under `runtime/cache`.

### Phase 4 - Docker Smoke Test And Runtime Validation

Phase 4 progress:

- Added `scripts/check_runtime.py`.
- Added `scripts/docker_smoke_test.py`.
- Added Docker usage documentation in `DOCKER_RUN.md`.
- Renamed the Docker Compose service to `app` so the supported commands are:

```text
docker compose build
docker compose run --rm app python scripts/check_runtime.py
docker compose run --rm app python scripts/docker_smoke_test.py
```

Runtime validation coverage:

- Loads settings through `ConfigLoader`.
- Verifies `runtime/logs`, `runtime/state/queue`, and `runtime/temp` are
  writable.
- Writes a structured app log.
- Writes and reads a queue state snapshot.
- Verifies `ffmpeg` is available on `PATH`.

Smoke test coverage:

- Imports the current entrypoint and Phase 1-3 modules.
- Runs the runtime validation script.
- Avoids Google Sheet connection and does not execute render/upload business
  logic.

Phase 4 results:

- Local Python test suite passed after adding Docker config and script tests.
- Docker commands are documented and supported by Compose config.
- Local runtime script verified config loading, writable logs/state/temp
  directories, log writing, and queue persistence.
- Local runtime script failed at FFmpeg validation because `ffmpeg` is not
  available on the host `PATH`.
- Docker execution could not be verified in this environment because `docker`
  is not installed or not available on `PATH`.
- The Docker image installs `ffmpeg`, so `scripts/check_runtime.py` is expected
  to validate FFmpeg inside the container once Docker is available.

### Phase 5 - Production Queue Safety

- Add worker locks.
- Add retry counts.
- Add timestamps.
- Add `worker_id`.
- Prevent duplicate processing of the same job.

### Phase 6 - Upload Handoff

- Keep rendering separate from uploading.
- Let upload tooling consume `READY_UPLOAD` jobs.
- Add upload-safe metadata fields later without changing render jobs.

### Phase 5 - YouTube Data API Upload

Phase 5 progress:

- Added `integrations/youtube/youtube_api_uploader.py`.
- Implemented a YouTube Data API v3 resumable upload client.
- Kept Selenium optional and outside the upload flow.
- Preserved `UploadWorker`'s injected-client architecture.
- Added upload lifecycle tracking with lowercase states:
  `pending`, `uploading`, `uploaded`, `failed`, and `retrying`.
- Kept existing queue status compatibility with `READY_UPLOAD`, `UPLOADING`,
  `UPLOADED`, and `ERROR`.
- Added upload metadata fields to persisted queue snapshots:
  `title`, `description`, `tags`, `category_id`, and `privacy_status`.
- Added OAuth credential settings:
  `youtube_oauth_credentials_json`, `youtube_oauth_token_json`, and
  `youtube_upload_chunk_size`.
- Updated `VIDEO_QUEUE` template with upload metadata columns.
- Added `YOUTUBE_API_SETUP.md`.
- Added mocked uploader tests; tests do not perform real uploads.

Upload architecture:

- `QueueProcessor` still renders videos and marks completed render jobs as
  `READY_UPLOAD`.
- `UploadWorker` consumes `READY_UPLOAD` queue states and delegates upload to an
  injected client.
- `YouTubeApiUploader` implements that client contract with
  `upload(job) -> video_id`.
- The uploader defaults `privacyStatus` to `private` and `categoryId` to `22`.
- Google API libraries are imported lazily so module import and smoke tests do
  not require OAuth credentials.

## Production-Ready Target Architecture

```text
reup_pipeline_sheet_control_v2/
  pipeline.py
  repositories/
    sheet_repository.py
  services/
    text_service.py
    tts_service.py
    render_service.py
  processors/
    folder_processor.py
    queue_processor.py
    sheet_client.py
    text_matcher.py
    tts_engine.py
    render_engine.py
  tests/
    test_sheet_repository.py
    test_text_service.py
```

This keeps the existing layout recognizable while creating clear boundaries for
future production hardening.
