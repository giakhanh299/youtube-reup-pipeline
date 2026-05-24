# YouTube Pipeline MCP Server

Remote MCP server for this repository, deployed on Cloudflare Workers with the Agents SDK.

Endpoint:

```text
/mcp
```

The server is intentionally public/authless for now and exposes only non-secret operational metadata. It does not return OAuth tokens, Google credentials, `.env` values, or filesystem secrets.

## Tools

```text
health
telegram_worker_links
telegram_commands
production_command
channel_sheet_columns
describe_channel_column
```

## Local Development

```powershell
npm install
npm run dev
```

Local MCP endpoint:

```text
http://localhost:8788/mcp
```

Test with MCP Inspector:

```powershell
npx @modelcontextprotocol/inspector@latest
```

## Deploy

```powershell
npx wrangler login
npm install
npm run dry-run
npm run deploy
```

Remote endpoint after deploy:

```text
https://youtube-pipeline-mcp.<account>.workers.dev/mcp
```

## Connect From Codex

```powershell
codex mcp add youtube-pipeline -- npx mcp-remote https://youtube-pipeline-mcp.<account>.workers.dev/mcp
```

Restart Codex after updating MCP configuration.
