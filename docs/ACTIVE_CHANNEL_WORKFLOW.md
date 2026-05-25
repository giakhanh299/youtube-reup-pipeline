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

The new clean orchestrator is:

```text
scripts/run_processing_workflow.py
```

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
- download Google Drive videos in Python
- upload YouTube videos

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

### Step 2: Run Processing Workflow

Run the new orchestrator:

```powershell
python scripts\run_processing_workflow.py
```

This script:

- reads `runtime/state/active_channel.json`
- uses the existing configured folder paths
- generates `.srt` subtitles using logic based on `lay_sub.py`
- translates `.srt` files to `_vi.srt` using logic based on `dich_gemini.py`
- creates cloned voice audio with the existing `TTSService` / OmniVoice local setup
- renders per-channel output video with the existing `RenderService`
- logs each step
- does not download from Google Drive
- does not upload to YouTube

Default folders match the current workflow:

```text
processing_source_dir = G:/My Drive/Video Doujin/VIDEO IN PUT GIAKHANH CHANEL
processing_work_dir   = G:/My Drive/Video Doujin/VIDEO IN PUT GIAKHANH CHANEL/DA_XU_LY
```

Voice cloning still comes from Google Sheet config:

- `CHANNEL_CONFIG.voice_id` selects the voice.
- `VOICE_CONFIG.ref_audio_path` and `VOICE_CONFIG.ref_text` are used by OmniVoice.
- `CHANNEL_CONFIG.output_folder` receives the rendered video.
- `processing_keep_voice_audio=false` deletes temporary cloned audio after render.

The translation API key is read from `.env` or the environment. Supported names:

```powershell
SUBTITLE_TRANSLATION_API_KEY=...
DASHSCOPE_API_KEY=...
OPENAI_API_KEY=...
```

For a one-off test without editing config:

```powershell
python scripts\run_processing_workflow.py --source-dir "G:\My Drive\Video Doujin\VIDEO IN PUT GIAKHANH CHANEL" --processing-dir "G:\My Drive\Video Doujin\VIDEO IN PUT GIAKHANH CHANEL\DA_XU_LY"
```

The old scripts remain available as references/manual fallback only:

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
New Python processing orchestrator uses current folder paths
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
