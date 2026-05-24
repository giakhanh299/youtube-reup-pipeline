import { McpAgent } from "agents/mcp";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

const TELEGRAM_WORKER_URL = "https://telegramdieukhien.giakhanh299.workers.dev";
const TELEGRAM_WEBHOOK_URL = `${TELEGRAM_WORKER_URL}/telegram/webhook`;
const PRODUCTION_COMMAND = "python scripts/run_full_production.py --source google_sheet --max-channels 100";

const CHANNEL_COLUMNS = [
  "channel_id",
  "channel_name",
  "input_folder",
  "output_folder",
  "voice_id",
  "voice_name",
  "youtube_token",
  "youtube_oauth_token_json",
  "privacyStatus",
  "enabled",
  "daily_limit",
  "worker_id",
  "last_error",
  "music_pack_id",
  "overlay_pack_id",
  "render_preset_id",
];

const TELEGRAM_COMMANDS = [
  "/start",
  "/help",
  "/health",
  "/upload",
  "/process",
  "/queue",
  "/private",
];

function text(content) {
  return { content: [{ type: "text", text: content }] };
}

function json(content) {
  return text(JSON.stringify(content, null, 2));
}

export class PipelineMCP extends McpAgent {
  server = new McpServer({ name: "youtube-pipeline-mcp", version: "1.0.0" });

  async init() {
    this.server.tool("health", {}, async () =>
      json({
        ok: true,
        service: "youtube-pipeline-mcp",
        mcp_endpoint: "/mcp",
        telegram_worker_url: TELEGRAM_WORKER_URL,
      }),
    );

    this.server.tool("telegram_worker_links", {}, async () =>
      json({
        worker_url: TELEGRAM_WORKER_URL,
        webhook_url: TELEGRAM_WEBHOOK_URL,
        supported_commands: TELEGRAM_COMMANDS,
      }),
    );

    this.server.tool("telegram_commands", {}, async () => text(TELEGRAM_COMMANDS.join("\n")));

    this.server.tool("production_command", {}, async () =>
      json({
        command: PRODUCTION_COMMAND,
        notes: [
          "Google Sheet remains the primary control system.",
          "Default privacy remains private.",
          "Voice generation uses local OmniVoice only.",
          "Secrets and tokens are never returned by this MCP server.",
        ],
      }),
    );

    this.server.tool("channel_sheet_columns", {}, async () => text(CHANNEL_COLUMNS.join("\n")));

    this.server.tool(
      "describe_channel_column",
      { column: z.string().min(1) },
      async ({ column }) => {
        const normalized = column.trim();
        const descriptions = {
          channel_id: "Stable channel key used to route jobs and output.",
          channel_name: "Human-readable channel/account label.",
          input_folder: "Sheet-defined folder containing input videos for this channel.",
          output_folder: "Sheet-defined destination for rendered per-channel videos.",
          voice_id: "Key resolved through VOICE_CONFIG.",
          voice_name: "Reference voice filename resolved under runtime/voices.",
          youtube_token: "Preferred per-channel YouTube OAuth token path.",
          youtube_oauth_token_json: "Compatibility token path column.",
          privacyStatus: "YouTube privacy; defaults to private when blank.",
          enabled: "Whether the channel should be processed.",
          daily_limit: "Maximum videos to process for this channel in one production run.",
          worker_id: "Operator-assigned worker label for orchestration.",
          last_error: "Sheet-visible last channel error field.",
          music_pack_id: "Key resolved through MUSIC_PACK.",
          overlay_pack_id: "Key resolved through OVERLAY_PACK.",
          render_preset_id: "Key resolved through RENDER_PRESET.",
        };
        return text(descriptions[normalized] || `Unknown or custom column: ${normalized}`);
      },
    );
  }
}

const mcpHandler = PipelineMCP.serve("/mcp");

export default {
  fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/") {
      return Response.json({
        ok: true,
        service: "youtube-pipeline-mcp",
        mcp_endpoint: "/mcp",
      });
    }
    return mcpHandler.fetch(request, env, ctx);
  },
};
