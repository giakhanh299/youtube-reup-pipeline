# Google Sheet Setup

Run this command from the repository root to create or repair the required
Google Sheet tabs, headers, sample rows, and dropdowns:

```powershell
python scripts\setup_google_sheet_schema.py
```

The script reads `spreadsheet_id` and `service_account_json` from
`configs/settings.json` through the existing project config/auth path.

It is safe to run multiple times:

- Existing worksheets are reused.
- Existing data rows are not deleted.
- Missing headers are appended.
- Sample rows are only added to empty sheets.
- Dropdown/data validation is applied where supported by the Google Sheets
  client.

Managed tabs:

```text
CHANNEL_CONFIG
VOICE_CONFIG
MUSIC_PACK
OVERLAY_PACK
RENDER_PRESET
VIDEO_QUEUE
```

Dropdown fields include status, upload status, privacy, channel, voice, music,
overlay, render preset, and render controls.

## Scheduler

Start the VIDEO_QUEUE automation scheduler from the repository root:

```powershell
python scripts\run_scheduler.py
```

The scheduler loops `VIDEO_QUEUE`, renders `NEW` jobs, uploads `READY_UPLOAD`
jobs, writes status updates back to Google Sheets, logs heartbeat/statistics to
`runtime/logs/scheduler.log`, and uses a local lock file to avoid duplicate
local scheduler instances.

## Telegram Control API

Start the Telegram control API from the repository root:

```powershell
python scripts\run_control_api.py
```

The API exposes:

```text
GET  /health
POST /telegram/webhook
```

Configure these values in `.env` or environment variables:

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_CHAT_IDS=123456789,987654321
PUBLIC_WEBHOOK_URL=https://your-public-url/telegram/webhook
```

Only chat IDs in `TELEGRAM_ALLOWED_CHAT_IDS` are accepted. Telegram replies do
not include tokens, credential paths, or other secret values.

Supported Telegram commands:

```text
/help
/status
/run <channel_id>
/pause
/resume
/retry <job_id>
/render
/upload
/sheet
/logs
```

Pause/resume and command intents are written locally under:

```text
runtime/state/control_state.json
runtime/state/control_events.jsonl
```

## Active Channel Workflow

The active-channel workflow keeps the existing GAS and legacy processing scripts
unchanged while adding one-channel-at-a-time token selection and lock
protection.

Detailed documentation:

```text
docs/ACTIVE_CHANNEL_WORKFLOW.md
```

Production outline:

```powershell
python scripts\run_full_production.py --channel-id channel_001
python scripts\run_processing_workflow.py
python scripts\finish_active_channel.py
```

The old scripts are still available as references/manual fallback:

```powershell
python lay_sub.py
python dich_gemini.py
python long_tieng_final.py
```

`scripts\run_processing_workflow.py` also uses the selected channel's
`voice_id` and `VOICE_CONFIG` row to create OmniVoice/local cloned audio, then
renders the processed video to the channel `output_folder`. It does not upload.

State files:

```text
runtime/state/active_channel.json
runtime/state/active_channel.lock
```

GAS still handles video fetching/downloading. Python only stores the selected
channel, protects the active channel with a lock, and routes upload token
selection. Existing folder paths and processing scripts remain unchanged.

Cloudflare Tunnel can expose the local API for Telegram webhook testing:

```powershell
cloudflared tunnel --url http://localhost:8000
```

Then set the Telegram webhook URL to the tunnel URL plus `/telegram/webhook`.

## OmniVoice TTS

`VOICE_CONFIG` supports OmniVoice clone voices with:

```text
tts_engine=omnivoice
ref_audio_path
ref_text
language
speed
pitch
```

Manual test command:

```powershell
python scripts\test_omnivoice_tts.py --text "Xin chao day la giong clone test" --ref-audio runtime/test/Khanh2.wav --ref-text "Xin chao, day la giong clone mau." --output runtime/test/omnivoice_test.wav
```

The OmniVoice package/model is loaded lazily only when this engine is used.

## Metadata And Uploaded Ledger

Generate missing VIDEO_QUEUE metadata:

```powershell
python scripts\generate_video_metadata.py --limit 10
python scripts\generate_video_metadata.py --limit 10 --dry-run
python scripts\generate_video_metadata.py --force --limit 10
```

If `OPENAI_API_KEY` is set, metadata generation uses OpenAI. Otherwise it falls
back to templates from `CHANNEL_CONFIG`.

Successful uploads can be written to the global `UPLOADED_VIDEOS` ledger. The
ledger stores history across all channels while `VIDEO_QUEUE` remains the active
queue.
