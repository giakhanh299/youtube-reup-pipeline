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
