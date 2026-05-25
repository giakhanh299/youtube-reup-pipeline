# Telegram Command Map

## Scope

This document maps the current Telegram-related handlers in Google Apps Script, Cloudflare Worker, and Python CLI code.

Goals:

- keep the current Google Sheet structure unchanged
- keep the current GAS workflow unchanged
- keep the current Python workflow unchanged
- define a clear Telegram command menu for later wiring

Legacy untracked local files are not part of this command map commit:

- `RUN.py`
- `lay_sub.py`
- `dich_gemini.py`
- `long_tieng_final.py`

## Current GAS Commands And Actions

Current Telegram handling in GAS is in [TelegramChannels.js](/D:/YOUTUBE_AUTOMATION/reup_pipeline_sheet_control_v2/apps_script/TelegramChannels.js).

Current GAS Telegram command:

- `/channels`
  Reads the `Linkchanel douyin` sheet and shows inline buttons for channel rows.

Current GAS callback actions:

- `channels_page_<page>`
  Changes the inline keyboard page for Douyin channels.
- `channel_get_row_<rowNumber>`
  Calls `getDouyinVideoLinksByRow(rowNumber)` and writes fetched video rows into the `Getvideo` sheet.

Current GAS functions that can be triggered manually or by trigger:

- `getDouyinVideoLinks2()`
  Batch fetches Douyin videos for rows marked `Lay` in `Linkchanel douyin`.
- `getDouyinVideoLinksByRow(rowNumber)`
  Fetches Douyin videos for one selected source row.
- `updateDriveLinks()`
  Downloads source MP4 files and uploads them to Google Drive, up to 10 per run.
- `updateDriveLinksUnlimited()`
  Same as above without the 10-file cap.
- `installChannelAddedTrigger()`
  Installs the spreadsheet edit trigger for Cloudflare notification.
- `handleChannelConfigEdit(e)`
  Watches `Linkchanel douyin` column D for `Lay`.
- `notifyCloudflareChannelAdded_(sheet, row)`
  Posts a notification to the Cloudflare Worker endpoint `/gas/channel-added`.

Notes:

- No GAS custom menu or `onOpen()` handler was found.
- GAS Telegram support is currently for Douyin source-channel fetching, not for Python active-channel processing.

## Current Python CLI Commands

Current tracked Python CLI entrypoints relevant to Telegram control:

- `python scripts\run_control_api.py`
  Starts the local FastAPI control API at `/telegram/webhook`.
- `python scripts\run_full_production.py --channel-id <channel_id>`
  Selects the active `CHANNEL_CONFIG` channel and writes `runtime/state/active_channel.json` plus the lock file.
- `python scripts\run_processing_workflow.py`
  Processes the selected active channel, renders final MP4 files, and registers those MP4 files into the upload queue sheet as `pending`.
- `python scripts\upload_from_sheet.py`
  Uploads pending rows from the sheet configured by `upload_sheet_name`.
- `python scripts\finish_active_channel.py`
  Releases the active-channel lock and state.
- `python scripts\finish_active_channel.py --force-clean`
  Admin recovery path. Cleans runtime work folders and releases the lock.

Other tracked Python command surfaces:

- `python scripts\run_scheduler.py`
  Scheduler loop for queue-based processing and upload.
- `python scripts\render_douyin_from_sheet.py`
  Separate sheet-driven render flow.

Important behavior detail:

- `run_full_production.py --channel-id <channel_id>` currently selects the active channel only. It does not start processing by itself.
- `run_control_api.py` currently accepts Telegram commands and records control events, but does not yet execute the Python CLI scripts unless a future action runner is added.

## Commands Already Connected To Telegram

### GAS webhook

Currently connected:

- `/channels`
- inline callback buttons for Douyin row paging and row fetch

### Cloudflare Worker

Current Worker file: [index.js](/D:/YOUTUBE_AUTOMATION/reup_pipeline_sheet_control_v2/workers/telegram-control/src/index.js)

Worker-native replies:

- `/start`
- `/help`
- `/health`

Worker commands that are forwarded to the Python control API when `CONTROL_API_URL` is configured:

- `/status`
- `/run`
- `/pause`
- `/resume`
- `/retry`
- `/render`
- `/upload`
- `/sheet`
- `/logs`

Current limitation:

- these forwarded commands reach the Python control API, but the control API currently records intent only
- they do not yet execute `run_full_production.py`, `run_processing_workflow.py`, `upload_from_sheet.py`, or `finish_active_channel.py`

## Missing Telegram Commands

These commands are not currently wired end to end:

- `/channel_list`
- `/select_channel channel_001`
- `/start_channel channel_001`
- `/process`
- `/finish`
- `/unlock`

Also missing:

- a clear split between GAS Douyin-source actions and Python active-channel actions in one Telegram command menu

## Which Commands Should Run In GAS

These should stay on the GAS side because they operate on the Douyin source sheets and RapidAPI fetch flow:

- legacy `/channels`
- inline Douyin source-channel paging
- inline Douyin row fetch action
- any future alias such as `/douyin_channels`

These actions are source acquisition actions, not local render/upload actions.

## Which Commands Should Be Forwarded To Local Python API Or Local Agent

These should be handled by the local Python side because they depend on local runtime state, local files, FFmpeg, OmniVoice, upload tokens, and `runtime/state/active_channel.json`:

- `/channel_list`
- `/select_channel channel_001`
- `/start_channel channel_001`
- `/process`
- `/upload`
- `/finish`
- `/status`
- `/unlock`

Recommended execution mapping:

- `/channel_list`
  Local Python API should list enabled rows from `CHANNEL_CONFIG`.
- `/select_channel channel_001`
  Should run `python scripts\run_full_production.py --channel-id channel_001`
- `/start_channel channel_001`
  Recommended composite local-agent action:
  `python scripts\run_full_production.py --channel-id channel_001`
  then `python scripts\run_processing_workflow.py`
- `/process`
  Should run `python scripts\run_processing_workflow.py`
- `/upload`
  Should run `python scripts\upload_from_sheet.py`
- `/finish`
  Should run `python scripts\finish_active_channel.py`
- `/status`
  Should read local control state, active channel state, queue state, and recent logs
- `/unlock`
  Recommended admin recovery command:
  `python scripts\finish_active_channel.py --force-clean`

## Proposed Telegram Command Menu

Recommended final user-facing menu:

- `/help`
- `/channel_list`
- `/select_channel channel_001`
- `/start_channel channel_001`
- `/process`
- `/upload`
- `/finish`
- `/status`
- `/unlock`

Recommended compatibility aliases:

- keep `/channels` as the GAS Douyin-source command
- keep `/run <channel_id>` as a temporary alias for `/select_channel <channel_id>` or `/start_channel <channel_id>`

## Command Flow

Primary command flow when Telegram is fronted by Cloudflare Worker:

`Telegram -> Cloudflare Worker -> local Python API/agent`

GAS-specific source-channel flow:

`Telegram -> GAS webhook -> Linkchanel douyin / Getvideo sheet actions`

Cloudflare notification flow from GAS:

`GAS trigger -> Cloudflare Worker /gas/channel-added -> Telegram admin message`

Recommended split when the production bot uses the Cloudflare Worker URL `https://telegramdieukhien.giakhanh299.workers.dev/telegram/webhook`:

- Worker-native:
  `/help`, `/health`
- Worker-forwarded to local Python API:
  `/channel_list`, `/select_channel`, `/start_channel`, `/process`, `/upload`, `/finish`, `/status`, `/unlock`
- GAS-only source actions:
  `/channels` and its inline callbacks

## Recommended Final Mapping

| Telegram command | Target | Current status | Recommended implementation |
| --- | --- | --- | --- |
| `/help` | Cloudflare Worker | already connected | keep native Worker reply |
| `/channel_list` | local Python API/agent | missing | list enabled `CHANNEL_CONFIG` rows |
| `/select_channel channel_001` | local Python API/agent | missing | call `run_full_production.py --channel-id` |
| `/start_channel channel_001` | local Python API/agent | missing | select channel then run processing |
| `/process` | local Python API/agent | missing | call `run_processing_workflow.py` |
| `/upload` | local Python API/agent | partially connected | execute `upload_from_sheet.py` instead of recording intent only |
| `/finish` | local Python API/agent | missing | call `finish_active_channel.py` |
| `/status` | local Python API/agent | partially connected | keep control API reply, expand with active-channel info |
| `/unlock` | local Python API/agent | missing | call `finish_active_channel.py --force-clean` |
| `/channels` | GAS | already connected | keep as Douyin-source legacy command |

## Constraints

- Google Sheet structure must remain unchanged.
- GAS workflow must remain unchanged.
- Python processing and upload workflows must remain separate.
- The Telegram command menu should be an orchestration layer on top of the existing GAS and Python components, not a rewrite of them.
