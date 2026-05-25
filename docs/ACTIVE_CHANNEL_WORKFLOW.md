# Active Channel Workflow

This project keeps the existing processing workflow and adds an active-channel
control layer on top of it.

The old processing scripts remain responsible for video/subtitle/voice work:

```text
RUN.py
lay_sub.py
dich_gemini.py
long_tieng_final.py
```

Those scripts are intentionally not redesigned by the active-channel system.
Google Apps Script still handles video fetching/downloading/preparation before
Python processing starts.

## Purpose

Only one channel may run at a time because the workflow uses shared runtime
folders. Telegram or another controller selects the active channel first, then
the existing workflow runs normally.

Active channel selection controls:

- which `CHANNEL_CONFIG.channel_id` is active
- which `CHANNEL_CONFIG.channel_name` is logged
- which `CHANNEL_CONFIG.youtube_token` / `youtube_oauth_token_json` is used for upload
- which `CHANNEL_CONFIG.source_folder_id` is logged for reference
- whether another channel job is blocked by the active-channel lock

It does not download Google Drive videos in Python and it does not replace the
legacy processing scripts.

## Shared Runtime Folders

The shared folders are configured in `configs/settings.json`:

```json
"shared_input_dir": "runtime/input",
"shared_processing_dir": "runtime/processing",
"shared_output_dir": "runtime/output",
"active_channel_lock_path": "runtime/state/active_channel.lock",
"active_channel_state_path": "runtime/state/active_channel.json"
```

The intended folder roles are:

```text
runtime/input       GAS or existing scripts place prepared input files here.
runtime/processing  Temporary working folder for runtime processing.
runtime/output      Final local output before upload/cleanup.
```

For backward compatibility, the old scripts can still use their existing
hardcoded folders. If you later point them at the shared runtime folders, make
that configurable and keep their old defaults.

## Runtime State Files

### `runtime/state/active_channel.json`

Stores the currently selected channel:

```json
{
  "channel_id": "channel_001",
  "channel_name": "TIN TỨC NỔI BẬT",
  "youtube_token_path": "secrets/youtube_token.pickle",
  "source_folder_id": "optional_google_drive_folder_id",
  "selected_at": "2026-05-25T00:00:00+00:00"
}
```

The uploader reads this file when an upload job does not already specify a token
path. Explicit job token paths still take priority for backward compatibility.

### `runtime/state/active_channel.lock`

Prevents two channel jobs from using the shared folders at the same time. If the
lock exists, selecting another channel should fail until the current channel is
finished or recovered.

## Production Workflow

Run these commands from the repository root:

```powershell
cd D:\YOUTUBE_AUTOMATION\reup_pipeline_sheet_control_v2
```

### Step 1: Select Active Channel

```powershell
python scripts\run_full_production.py --channel-id channel_001
```

This does not run the processing pipeline. It only:

- validates and selects `channel_001` from `CHANNEL_CONFIG`
- writes `runtime/state/active_channel.json`
- creates `runtime/state/active_channel.lock`
- cleans shared runtime folders before start
- prepares upload token selection for the selected channel
- logs selected `channel_id`, `channel_name`, `youtube_token_path`, `source_folder_id`, and shared folders

If you need to keep existing shared-folder files during recovery:

```powershell
python scripts\run_full_production.py --channel-id channel_001 --resume
```

### Step 2: Run Existing Workflow Normally

Use the existing scripts exactly as before.

Full legacy wrapper:

```powershell
python RUN.py
```

Or run individual steps:

```powershell
python lay_sub.py
python dich_gemini.py
python long_tieng_final.py
```

These scripts are intentionally unchanged. GAS and the existing scripts remain
responsible for fetching, preparing, subtitle extraction/translation, and voice
processing according to the current folder behavior.

### Step 3: Finish And Cleanup

After processing/upload finishes:

```powershell
python scripts\finish_active_channel.py
```

This:

- cleans `runtime/input`
- cleans `runtime/processing`
- cleans `runtime/output`
- removes `runtime/state/active_channel.json`
- releases `runtime/state/active_channel.lock`

If you only need to release state without cleanup:

```powershell
python scripts\finish_active_channel.py --no-clean
```

## Architecture

```text
Telegram / GAS selects channel
          |
          v
Python writes active channel state and lock
          |
          v
GAS prepares videos for selected channel
          |
          v
Old workflow scripts process videos unchanged
          |
          v
Uploader reads active channel token when no job token is set
          |
          v
Finish script cleans shared folders and releases lock
```

Python's role in this flow is narrow:

- manage active-channel state
- protect the shared folders with one-channel-at-a-time locking
- expose the selected channel token to upload routing
- clean shared runtime folders before and after a channel session

Python does not implement Google Drive video download by `source_folder_id`.

## Troubleshooting

### Lock File Stuck

Symptom:

```text
active channel job lock exists
```

Cause: a previous workflow crashed or did not run the finish step.

Check current state:

```powershell
Get-Content runtime\state\active_channel.json
Get-Content runtime\state\active_channel.lock
```

If no workflow is running, release and clean:

```powershell
python scripts\finish_active_channel.py
```

If you need to inspect files before cleanup:

```powershell
python scripts\finish_active_channel.py --no-clean
```

### Active Channel Mismatch

Symptom: the selected channel in logs/state is not the channel you expected.

Check:

```powershell
Get-Content runtime\state\active_channel.json
```

Then finish the current session and select the correct channel:

```powershell
python scripts\finish_active_channel.py
python scripts\run_full_production.py --channel-id channel_002
```

### Shared Runtime Folder Not Cleaned

Inspect folders:

```powershell
Get-ChildItem runtime\input
Get-ChildItem runtime\processing
Get-ChildItem runtime\output
```

Clean through the normal finish path:

```powershell
python scripts\finish_active_channel.py
```

### Wrong YouTube Token Used

Check the selected channel state:

```powershell
Get-Content runtime\state\active_channel.json
```

Also check the relevant `CHANNEL_CONFIG` row:

```text
channel_id
channel_name
youtube_token
youtube_oauth_token_json
source_folder_id
enabled
```

Upload jobs with an explicit `youtube_token_path` still override active-channel
state. This is preserved for backward compatibility.

### Interrupted Or Crashed Workflow Recovery

If the process crashes after channel selection:

1. Confirm no script is still running.
2. Inspect `runtime/state/active_channel.json`.
3. Inspect shared folders if needed.
4. Either resume or finish.

Resume without pre-clean:

```powershell
python scripts\run_full_production.py --channel-id channel_001 --resume
```

Finish and clean:

```powershell
python scripts\finish_active_channel.py
```

## Backward Compatibility Notes

- The old processing scripts remain unchanged.
- Existing per-job upload token paths still take priority.
- Existing multi-channel Python processing remains available for current code paths.
- `source_folder_id` is read and logged only; Python does not use it for Drive download.
- The active-channel workflow is an added control layer for single-channel shared-folder operation.
