# Codex Task List

## Task 1
Refactor the pipeline so every runtime decision is driven by Google Sheet rows, not local JSON, except `configs/settings.json` for spreadsheet_id and service account path.

## Task 2
Add CLI modes:
- `python pipeline.py --dry-run`
- `python pipeline.py --job-id JOB001`
- `python pipeline.py --channel-id kenh_1`

## Task 3
Improve text matching:
- Match MP4/MKV/AVI with `_vi.srt`, `.srt`, `.txt`.
- Prefer `_vi.srt`.
- Log missing text file as ERROR in VIDEO_QUEUE.

## Task 4
Add local TTS interface:
- `GoogleTTSAdapter`
- `XTTSAdapter`
- `F5TTSAdapter`
- `MockTTSAdapter` for tests.

## Task 5
Improve FFmpeg render:
- Background blur.
- Logo watermark opacity.
- Music mix volume.
- NVENC encoder fallback to libx264.

## Task 6
Add tests for:
- sheet row parsing
- voice config lookup
- channel config lookup
- text matcher
- render command builder

## Task 7
Add safer logging:
- Never print API keys.
- Never commit service account JSON.
- Write logs to `runtime/logs`.
