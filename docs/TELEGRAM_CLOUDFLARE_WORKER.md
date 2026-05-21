# Telegram Cloudflare Worker

This repository includes a standalone Cloudflare Worker at:

```text
workers/telegram-control
```

The Worker handles Telegram webhook updates 24/7 at the edge and sends command replies through Telegram Bot API using only the `TELEGRAM_BOT_TOKEN` secret.

The existing Python pipeline is unchanged. `/upload`, `/process`, `/queue`, and `/private` currently return mock replies. They are placeholders for future calls into `services/control_api.py`.

Production Worker URL:

```text
https://telegramdieukhien.giakhanh299.workers.dev
```

## Worker Endpoints

```text
GET  /
GET  /health
POST /telegram/webhook
```

`GET /` returns:

```text
Telegram Control Worker Online ✅
```

`POST /` accepts Telegram webhook updates and reads:

```text
update.message.chat.id
update.message.text
```

If no `chat.id` exists, the Worker returns `{ "ok": true }` without sending a Telegram message.

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

## Install Wrangler

From `workers/telegram-control`:

```powershell
npm install
```

## Login

```powershell
npx wrangler login
```

## Add Telegram Secret

```powershell
npx wrangler secret put TELEGRAM_BOT_TOKEN
```

Never put the bot token in `wrangler.toml`, source files, docs, or Git-tracked files.

## Deploy

```powershell
npx wrangler deploy
```

## Set Telegram Webhook

Use the deployed Worker URL:

```text
https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://telegramdieukhien.giakhanh299.workers.dev/telegram/webhook
```

The Worker also accepts `POST /` for backward compatibility, but `/telegram/webhook` is the recommended webhook path.

## Test

Send these messages to the bot:

```text
/start
/health
/help
```

HTTP endpoint checks:

```powershell
curl https://telegramdieukhien.giakhanh299.workers.dev/
curl https://telegramdieukhien.giakhanh299.workers.dev/health
curl -X POST -H "Content-Type: application/json" --data "{}" https://telegramdieukhien.giakhanh299.workers.dev/telegram/webhook
```

Expected unauthenticated webhook probe:

```json
{"ok":true}
```

If Telegram updates reach the Worker but no bot message is sent, re-create the Cloudflare secret and redeploy:

```powershell
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler deploy
```

## Future FastAPI Integration

The next integration step is to add a non-secret Worker environment variable for the local/public FastAPI control API URL and forward selected commands to:

```text
POST /telegram/webhook
GET  /health
```

That should be done without exposing secrets in Telegram responses or Worker logs.

## GitHub Actions Deployment

Workflow:

```text
.github/workflows/deploy-telegram-control-worker.yml
```

Required GitHub repository secret:

```text
CLOUDFLARE_API_TOKEN
```

Cloudflare Worker secret, created outside GitHub:

```powershell
npx wrangler secret put TELEGRAM_BOT_TOKEN
```

The workflow installs Worker dependencies, runs `npm run check`, and deploys with:

```powershell
npx wrangler deploy
```
