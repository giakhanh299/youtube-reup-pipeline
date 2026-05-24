# Cloudflare MCP Server

This repository includes a remote MCP server project:

```text
workers/pipeline-mcp
```

It uses Cloudflare Workers, Durable Objects, and the Agents SDK `McpAgent` API.
The MCP transport endpoint is:

```text
/mcp
```

## Purpose

The server exposes safe operational tools for this YouTube automation repository:

```text
health
telegram_worker_links
telegram_commands
production_command
channel_sheet_columns
describe_channel_column
```

It does not expose tokens, Google credentials, `.env` values, or local secret files.

## Validate

```powershell
cd workers\pipeline-mcp
npm install
npm run check
npm run dry-run
```

## Run Locally

```powershell
cd workers\pipeline-mcp
npm run dev
```

Use MCP Inspector against:

```text
http://localhost:8788/mcp
```

## Deploy

```powershell
cd workers\pipeline-mcp
npx wrangler login
npm run deploy
```

After deploy, connect MCP clients to:

```text
https://youtube-pipeline-mcp.<account>.workers.dev/mcp
```

## Codex Client

```powershell
codex mcp add youtube-pipeline -- npx mcp-remote https://youtube-pipeline-mcp.<account>.workers.dev/mcp
```

Restart Codex after adding the server.
