const COMMAND_REPLIES = {
  "/start": "Telegram control worker is online.",
  "/health": "Worker is healthy.",
  "/process": "Process command received. Configure CONTROL_API_URL to forward pipeline commands.",
  "/queue": "Queue command received. Use /status when CONTROL_API_URL is configured.",
  "/run": "Run command received. Configure CONTROL_API_URL to forward it to the Python control API.",
  "/upload": "Upload command received. Configure CONTROL_API_URL to forward it to the Python control API.",
  "/status": "Status command received. Configure CONTROL_API_URL to read pipeline status.",
  "/private": "Private upload remains the default pipeline policy.",
};

const CONTROL_API_COMMANDS = new Set([
  "/status",
  "/run",
  "/pause",
  "/resume",
  "/retry",
  "/render",
  "/upload",
  "/sheet",
  "/logs",
]);

const HELP_TEXT = [
  "Telegram Control Worker commands:",
  "/start - Check bot startup",
  "/help - Show commands",
  "/health - Check Worker health",
  "/status - Pipeline status via Python control API",
  "/run - Queue production run via Python control API",
  "/pause - Pause local pipeline control state",
  "/resume - Resume local pipeline control state",
  "/retry <job_id> - Retry one job",
  "/render - Queue render action",
  "/upload - Queue upload action when backend is configured",
  "/sheet - Show sheet configuration",
  "/logs - Show recent pipeline logs",
].join("\n");

function jsonResponse(payload, status = 200) {
  return Response.json(payload, { status });
}

function normalizeCommand(text) {
  const firstToken = String(text || "").trim().split(/\s+/, 1)[0] || "";
  return firstToken.split("@", 1)[0].toLowerCase();
}

function replyForCommand(command) {
  if (command === "/help") {
    return HELP_TEXT;
  }
  return COMMAND_REPLIES[command] || HELP_TEXT;
}

function bearerHeaders(env) {
  const headers = {
    "content-type": "application/json",
  };
  if (env.CONTROL_API_TOKEN) {
    headers.authorization = `Bearer ${env.CONTROL_API_TOKEN}`;
  }
  return headers;
}

async function sha256(text) {
  const data = new TextEncoder().encode(String(text || ""));
  const digest = await crypto.subtle.digest("SHA-256", data);
  return new Uint8Array(digest);
}

function equalBytes(left, right) {
  if (left.byteLength !== right.byteLength) {
    return false;
  }
  let diff = 0;
  for (let i = 0; i < left.byteLength; i += 1) {
    diff |= left[i] ^ right[i];
  }
  return diff === 0;
}

async function isValidGasSecret(request, env) {
  if (!env.GAS_SHARED_SECRET) {
    return false;
  }
  const provided = request.headers.get("x-gas-secret") || "";
  const [providedDigest, expectedDigest] = await Promise.all([
    sha256(provided),
    sha256(env.GAS_SHARED_SECRET),
  ]);
  return equalBytes(providedDigest, expectedDigest);
}

async function forwardToControlApi(env, update) {
  if (!env.CONTROL_API_URL) {
    return null;
  }
  const response = await fetch(`${env.CONTROL_API_URL.replace(/\/$/, "")}/telegram/webhook`, {
    method: "POST",
    headers: bearerHeaders(env),
    body: JSON.stringify(update),
  });
  if (!response.ok) {
    throw new Error(`control API failed with status ${response.status}`);
  }
  return response.json();
}

async function sendTelegram(env, chatId, text) {
  if (!env.TELEGRAM_BOT_TOKEN) {
    throw new Error("TELEGRAM_BOT_TOKEN is not configured");
  }

  const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
    },
    body: JSON.stringify({
      chat_id: chatId,
      text,
      disable_web_page_preview: true,
    }),
  });

  if (!response.ok) {
    throw new Error(`Telegram sendMessage failed with status ${response.status}`);
  }
}

async function sendTelegramMethod(env, payload) {
  if (!payload || payload.method !== "sendMessage" || !payload.chat_id || !payload.text) {
    return false;
  }
  await sendTelegram(env, payload.chat_id, payload.text);
  return true;
}

async function handleTelegramUpdate(request, env) {
  let update;
  try {
    update = await request.json();
  } catch (_error) {
    return jsonResponse({ ok: false, error: "invalid_json" }, 400);
  }

  const chatId = update?.message?.chat?.id;
  if (!chatId) {
    return jsonResponse({ ok: true });
  }

  const text = update?.message?.text || "";
  const command = normalizeCommand(text);
  try {
    if (CONTROL_API_COMMANDS.has(command)) {
      const controlReply = await forwardToControlApi(env, update);
      if (await sendTelegramMethod(env, controlReply)) {
        return jsonResponse({ ok: true, source: "control_api" });
      }
    }
    await sendTelegram(env, chatId, replyForCommand(command));
    return jsonResponse({ ok: true });
  } catch (error) {
    console.error("telegram_command_failed", {
      chatId: String(chatId),
      command,
      error: error instanceof Error ? error.message : String(error),
    });
    return jsonResponse({ ok: false, error: "telegram_command_failed" }, 502);
  }
}

async function handleGasChannelAdded(request, env) {
  if (!(await isValidGasSecret(request, env))) {
    return jsonResponse({ ok: false, error: "unauthorized" }, 403);
  }

  let payload;
  try {
    payload = await request.json();
  } catch (_error) {
    return jsonResponse({ ok: false, error: "invalid_json" }, 400);
  }

  const chatId = env.TELEGRAM_ADMIN_CHAT_ID;
  if (!chatId) {
    return jsonResponse({ ok: false, error: "telegram_admin_chat_id_missing" }, 500);
  }

  const text = [
    "New Douyin channel marked for fetch",
    `Sheet: ${payload.sheet || ""}`,
    `Row: ${payload.row || ""}`,
    `Channel: ${payload.channelName || ""}`,
    `Chinese name: ${payload.chineseName || ""}`,
    `secUid: ${payload.secUid || ""}`,
    "",
    "Next local command:",
    "python scripts/run_full_production.py --source google_sheet --max-channels 100 --dry-run",
  ].join("\n");

  await sendTelegram(env, chatId, text);
  return jsonResponse({ ok: true });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/") {
      return new Response("Telegram Control Worker Online", {
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }

    if (request.method === "GET" && url.pathname === "/health") {
      return jsonResponse({
        ok: true,
        service: "telegram-control-worker",
        control_api_configured: Boolean(env.CONTROL_API_URL),
        gas_notify_configured: Boolean(env.GAS_SHARED_SECRET && env.TELEGRAM_ADMIN_CHAT_ID),
      });
    }

    if (request.method === "POST" && (url.pathname === "/" || url.pathname === "/telegram/webhook")) {
      return handleTelegramUpdate(request, env);
    }

    if (request.method === "POST" && url.pathname === "/gas/channel-added") {
      return handleGasChannelAdded(request, env);
    }

    return jsonResponse({ ok: false, error: "not_found" }, 404);
  },
};

export {
  HELP_TEXT,
  normalizeCommand,
  replyForCommand,
  sendTelegram,
  forwardToControlApi,
  handleGasChannelAdded,
};
