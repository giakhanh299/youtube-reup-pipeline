# Telegram Control Worker

Cloudflare Worker webhook endpoint for the Telegram command center. It keeps the existing Python pipeline unchanged and prepares a lightweight 24/7 edge entrypoint for future integration with the FastAPI control API.

Production Worker URL:

```text
https://telegramdieukhien.giakhanh299.workers.dev
```

## Commands

```text
/start
/help
/health
/status
/run
/pause
/resume
/retry <job_id>
/render
/upload
/sheet
/logs
```

If `CONTROL_API_URL` is configured, pipeline commands are forwarded to the Python FastAPI control API at `/telegram/webhook`.
The Python API still enforces its own allowed Telegram chat IDs.

This Worker also exposes:

```text
POST /gas/channel-added
```

Google Apps Script can call this endpoint when a row in `Linkchanel douyin` is marked `Lấy`.
The request must include header `x-gas-secret`, matching the Cloudflare secret `GAS_SHARED_SECRET`.
The Worker sends a Telegram notification to `TELEGRAM_ADMIN_CHAT_ID`.

## Setup

Install dependencies:

```powershell
npm install
```

Log in to Cloudflare:

```powershell
npx wrangler login
```

Create the Telegram bot token secret:

```powershell
npx wrangler secret put TELEGRAM_BOT_TOKEN
```

Optional secrets for GAS and Python API integration:

```powershell
npx wrangler secret put GAS_SHARED_SECRET
npx wrangler secret put TELEGRAM_ADMIN_CHAT_ID
npx wrangler secret put CONTROL_API_URL
npx wrangler secret put CONTROL_API_TOKEN
```

`CONTROL_API_TOKEN` is reserved for deployments that add bearer-token checks to the Python API.

Deploy:

```powershell
npx wrangler deploy
```

Set the Telegram webhook after deploy. Use `/telegram/webhook` so browser checks on `/` can remain a plain health page:

```text
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://telegramdieukhien.giakhanh299.workers.dev/telegram/webhook
```

Do not commit bot tokens, `.dev.vars`, or any secret files.

## Local Development

Run locally:

```powershell
npm run dev
```

Syntax check:

```powershell
npm run check
```

After the webhook is set, test from Telegram:

```text
/start
/health
/help
```

Apps Script setup:

1. In Apps Script Project Settings, add Script Properties:
   - `RAPIDAPI_KEY`
   - `TELEGRAM_CONTROL_URL`, for example `https://telegramdieukhien.giakhanh299.workers.dev`
   - `GAS_SHARED_SECRET`, same value as the Cloudflare Worker secret
2. Run `installChannelAddedTrigger()` once from Apps Script and approve permissions.
3. In the `Linkchanel douyin` tab, set column D to `Lấy` for a channel row.

HTTP checks:

```powershell
curl https://telegramdieukhien.giakhanh299.workers.dev/
curl https://telegramdieukhien.giakhanh299.workers.dev/health
curl -X POST -H "Content-Type: application/json" --data "{}" https://telegramdieukhien.giakhanh299.workers.dev/telegram/webhook
```

If Telegram receives the webhook but the bot does not reply, verify the Cloudflare secret:

```powershell
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler deploy
```

## GitHub Actions Deploy

This repository includes `.github/workflows/deploy-telegram-control-worker.yml`.

Required GitHub repository secret:

```text
CLOUDFLARE_API_TOKEN
```

Store the Telegram bot token in Cloudflare, not GitHub:

```powershell
npx wrangler secret put TELEGRAM_BOT_TOKEN
```

The workflow runs syntax validation and deploys on pushes to `main` that touch the Worker files, or manually through `workflow_dispatch`.
