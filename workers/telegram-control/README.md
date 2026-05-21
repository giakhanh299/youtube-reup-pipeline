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
/upload
/process
/queue
/private
```

`/upload`, `/process`, `/queue`, and `/private` are mock replies for now. They do not call the Python pipeline yet.

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
