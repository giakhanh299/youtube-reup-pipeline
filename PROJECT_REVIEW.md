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

### Phase 6 - Sheet-Controlled Upload

Phase 6 progress:

- Added config compatibility for legacy `YT_YOUTUBE_TOKEN_PICKLE_PATH`.
- The uploader now supports token files ending in `.pickle` as well as JSON
  OAuth token files.
- Added `processors/sheet_upload_processor.py`.
- Added `scripts/upload_from_sheet.py` as an isolated upload runner.
- Preserved `pipeline.py`; rendering behavior is unchanged.
- Added generic upload-sheet read/write methods to `SheetRepository` and
  `SheetConfig`.
- Mapped the real upload sheet columns:
  `video_path`, `title`, `description`, `tags`, `categoryId`, `privacyStatus`,
  `upload_status`, `youtube_video_id`, `upload_error`, and `upload_time`.
- Added mocked tests for config compatibility, repository delegation, and sheet
  upload processing.

Sheet upload flow:

1. Read rows from `upload_sheet_name`, default `Video đã edit`.
2. Select rows where `upload_status` is blank or `pending`.
3. Upload `video_path` through `YouTubeApiUploader`.
4. Default missing `privacyStatus` to `private`.
5. Default missing `categoryId` to `22`.
6. Write `uploading`, then `uploaded`, YouTube video ID, and UTC upload time.
7. On failure, write `failed` and `upload_error`.

### Phase 7 - Upload Stability And Recovery

Phase 7 progress:

- Prevent duplicate uploads by skipping rows already marked `uploaded` or rows
  that already contain `youtube_video_id`.
- Validate `video_path` exists before upload.
- Validate upload file extensions using `upload_allowed_exts` or `video_exts`.
- Added optional `retry_count`, `last_error`, `upload_started_at`, and
  `upload_finished_at` sheet updates.
- Added retry recovery for rows in `failed` while `retry_count` is below
  `upload_retry_max_attempts`.
- Added crash recovery for stale rows stuck in `uploading` after
  `upload_recover_stale_after_seconds`.
- Added best-effort upload timeout handling via `upload_timeout_seconds`.
- Improved upload logging with start, finish, failure, row number, video path,
  and retry count.
- Added mocked tests for duplicate prevention, validation, retry recovery,
  stale upload recovery, retry limits, and timeout failure handling.

Phase 7 remains intentionally single-worker. It prevents common duplicate
uploads and recovers interrupted rows, but it does not add distributed locks or
multi-account scaling.

### Phase 8 - Douyin Render Pipeline

Phase 8 progress:

- Added `processors/douyin_render_processor.py`.
- Added `scripts/render_douyin_from_sheet.py`.
- Added `sheets_templates/DOUYIN_RENDER.csv`.
- Added SheetRepository methods for render job reads and render result writes.
- Added FFmpeg-backed helpers for source validation, metadata extraction,
  original audio extraction, optional TTS audio creation, and final video render.
- Kept upload flow unchanged; rendering only writes render results back to the
  configured render sheet.
- Added mocked tests for pending-row rendering, TTS audio selection, ready-row
  skips, missing source validation, unsupported extension validation, and
  repository delegation.

Render sheet columns:

```text
source_video_path,audio_path,rendered_video_path,render_status,render_error,
voice_name,voice_speed,voice_pitch,language,tts_text
```

Render flow:

1. Read rows from `render_sheet_name`, default `Douyin Render`.
2. Process rows where `render_status` is blank or `pending`.
3. Validate source file existence and extension.
4. Extract metadata with `ffprobe` when available.
5. Use TTS audio when text is provided, otherwise use existing `audio_path` or
   extract original audio with FFmpeg.
6. Render final output to `render_output_dir`.
7. Write `render_status=ready`, `audio_path`, and `rendered_video_path`, or
   write `render_status=failed` and `render_error`.

### Phase 9 - Channel Config Foundation

Phase 9 progress:

- Added support for a separate `Channel Config` Google Sheet tab.
- Added `SheetRepository.load_upload_channel_configs()`.
- Added enabled-only channel config normalization for upload defaults.
- Added optional `channel_key` support in upload queue rows.
- Kept backward compatibility: rows without `channel_key` still use existing
  global defaults.
- Added per-channel default application for privacy, category, tags, title
  templates, and description templates.
- Added `sheets_templates/CHANNEL_CONFIG_UPLOAD.csv`.
- Added mocked tests for enabled-only config loading, channel defaults, missing
  channel handling, and no-channel backward compatibility.

Channel Config columns:

```text
channel_key,channel_name,account_name,youtube_token_path,voice_name,
voice_speed,voice_pitch,language,default_categoryId,default_privacyStatus,
title_template,description_template,tags_default,enabled,notes
```

Upload queue change:

- `channel_key` is optional.
- When present, it must match an enabled `Channel Config` row.
- When absent, existing settings are used.
- Missing `privacyStatus` still defaults to `private`.

### Phase 10 - Multi-Account Upload Foundation

Phase 10 progress:

- Added `workers/multi_account_upload_worker.py`.
- Added `MultiAccountUploader`, a safe routing wrapper that implements the same
  `upload(job) -> video_id` contract as the single-account uploader.
- Added account metadata to `QueueJobState`: `channel_key`, `account_name`, and
  `youtube_token_path`.
- Upload jobs now inherit account metadata from `Channel Config` when
  `channel_key` is present.
- The router caches one uploader instance per account and applies the matching
  `youtube_token_path` to that account's uploader settings.
- Added per-account locks so uploads for the same account cannot run through the
  same router concurrently.
- Added token conflict protection: one account cannot be reused with a different
  token path inside the same router instance.
- Added `upload_worker_count` as a configurable assignment hint; default remains
  single-worker behavior.
- Added mocked tests for account routing, uploader reuse, token conflict
  protection, and backward-compatible default account routing.

Phase 10 does not add distributed cloud workers or parallel scheduler execution.
Single-account upload remains functional because `MultiAccountUploader` defaults
to the configured global token path when no account metadata is present.

### Phase 11 - Scheduler And Automation Daemon

Phase 11 progress:

- Added `services/scheduler_service.py`.
- Added `scripts/scheduler_daemon.py`.
- Added a `scheduler` service to `docker-compose.yml`.
- Added configurable intervals:
  `scheduler_processing_interval_seconds`,
  `scheduler_upload_interval_seconds`,
  `scheduler_retry_interval_seconds`, and
  `scheduler_heartbeat_interval_seconds`.
- Scheduler tasks run cooperatively in a continuous loop with graceful shutdown
  via SIGINT/SIGTERM.
- Added heartbeat logging through the existing structured logger.
- Added task result counts and failure counts for runtime monitoring.
- Added retry interval behavior for failed task cycles.
- Scheduler wiring uses `DouyinRenderProcessor` followed by
  `SheetUploadProcessor` with `MultiAccountUploader`.
- Crash recovery remains in the processors: render/upload rows are skipped,
  retried, or recovered based on sheet status and timestamps.
- Added mocked tests for intervals, retry scheduling, heartbeat logging, and
  Docker Compose scheduler config.

Scheduler command:

```text
python scripts/scheduler_daemon.py
```

Docker scheduler command:

```text
docker compose up scheduler
```

### Phase 12 - Optional Dashboard

Phase 12 progress:

- Added `services/dashboard_service.py`.
- Added `scripts/dashboard.py`.
- Added a `dashboard` service to `docker-compose.yml`.
- Dashboard uses only the standard library HTTP server.
- Dashboard reads local runtime queue snapshots and structured JSONL logs.
- Dashboard exposes:
  - `GET /` for the HTML UI.
  - `GET /api/status` for queue counts, jobs, account usage, retry counts,
    throughput counters, and log tails.
  - `POST /api/control` for control intents: `retry`, `skip`, `pause`, and
    `resume`.
- Dashboard controls write local intent files under `runtime/state/dashboard`;
  they do not call render/upload business logic directly.
- Added mocked/lightweight tests for queue aggregation, log reading, control
  event writing, pause state writing, and invalid action validation.

Dashboard command:

```text
python scripts/dashboard.py
```

Docker dashboard command:

```text
docker compose up dashboard
```

Dashboard architecture remains optional and decoupled. It is a monitoring and
control-intent surface, not a business logic executor.

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
