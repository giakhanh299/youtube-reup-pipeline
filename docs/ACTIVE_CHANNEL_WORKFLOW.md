# Active Channel Workflow

This project keeps the existing folder layout and processing workflow. The
active-channel system is only a small control layer for selecting the channel
and upload token.

Reference-only legacy scripts:

```text
lay_sub.py
dich_gemini.py
long_tieng_final.py
```

These files are not integrated, rewritten, or forced into the new workflow.
They remain examples of the old subtitle, translation, and local dubbing logic.

## What Active Channel Does

Active channel selection controls:

- selected `CHANNEL_CONFIG.channel_id`
- selected `CHANNEL_CONFIG.channel_name`
- selected `CHANNEL_CONFIG.youtube_token` / `youtube_oauth_token_json`
- logged `CHANNEL_CONFIG.source_folder_id`
- one-channel-at-a-time lock protection

Python does not use `source_folder_id` to download from Google Drive. GAS still
handles video fetching/downloading and sheet workflow.

## What Active Channel Does Not Do

The active-channel layer does not:

- change the Google Sheet layout
- change existing folder paths
- force `runtime/input`, `runtime/processing`, or `runtime/output`
- run or rewrite `lay_sub.py`
- run or rewrite `dich_gemini.py`
- run or rewrite `long_tieng_final.py`
- replace the existing processing pipeline

The current working folder behavior stays the source of truth for processing.

## Runtime State Files

### `runtime/state/active_channel.json`

Stores the selected channel:

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

Prevents two channel sessions from running at the same time. If the lock exists,
selecting another channel fails until the current channel is finished or
recovered.

## Production Workflow

Run commands from the repository root:

```powershell
cd D:\YOUTUBE_AUTOMATION\reup_pipeline_sheet_control_v2
```

### Step 1: Select Active Channel

```powershell
python scripts\run_full_production.py --channel-id channel_001
```

This only:

- validates and selects `channel_001` from `CHANNEL_CONFIG`
- writes `runtime/state/active_channel.json`
- creates `runtime/state/active_channel.lock`
- prepares upload token selection for the selected channel
- logs selected `channel_id`, `channel_name`, `youtube_token_path`, and `source_folder_id`

It does not run video processing and does not change existing folder paths.

### Step 2: Run Current Workflow

Run the current working process normally. GAS still handles video
fetching/downloading and preparation. Existing Python scripts or other tools
continue using their current folders.

Examples:

```powershell
python RUN.py
```

or:

```powershell
python lay_sub.py
python dich_gemini.py
python long_tieng_final.py
```

These scripts are intentionally unchanged.

### Step 3: Finish Active Channel

```powershell
python scripts\finish_active_channel.py
```

This:

- removes `runtime/state/active_channel.json`
- releases `runtime/state/active_channel.lock`

It does not clean processing folders by default, because the active-channel
layer must not assume or change the current folder structure.

Optional cleanup is available only if your runtime folder settings are
configured intentionally:

```powershell
python scripts\finish_active_channel.py --clean-runtime
```

## Architecture

```text
Telegram/GAS selects channel
          |
          v
Python writes active channel state and lock
          |
          v
GAS prepares videos using existing workflow
          |
          v
Current processing workflow runs with current folder paths
          |
          v
Uploader reads active channel token when no job token is set
          |
          v
Finish script releases active channel state and lock
```

## Troubleshooting

### Lock File Stuck

Symptom:

```text
active channel job lock exists
```

Check:

```powershell
Get-Content runtime\state\active_channel.json
Get-Content runtime\state\active_channel.lock
```

If no workflow is running:

```powershell
python scripts\finish_active_channel.py
```

### Active Channel Mismatch

Check selected channel:

```powershell
Get-Content runtime\state\active_channel.json
```

Then finish and select the correct channel:

```powershell
python scripts\finish_active_channel.py
python scripts\run_full_production.py --channel-id channel_002
```

### Wrong YouTube Token Used

Check `active_channel.json` and the selected `CHANNEL_CONFIG` row:

```text
channel_id
channel_name
youtube_token
youtube_oauth_token_json
source_folder_id
enabled
```

If an upload job explicitly sets `youtube_token_path`, that explicit token still
wins. This preserves old behavior.

### Interrupted Or Crashed Workflow Recovery

1. Confirm no script is still running.
2. Inspect `runtime/state/active_channel.json`.
3. Preserve any working folders you need.
4. Release the lock:

```powershell
python scripts\finish_active_channel.py
```

## Backward Compatibility Notes

- Existing Google Sheet layout is unchanged.
- Existing folder paths are unchanged.
- GAS still handles video fetching/downloading.
- Legacy scripts are reference examples only.
- Existing explicit upload token paths still take priority.
