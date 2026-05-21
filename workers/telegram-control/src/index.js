const COMMAND_REPLIES = {
  "/start": "Bot điều khiển hệ thống reup đã online ✅",
  "/health": "Worker sống 24/7 ✅",
  "/upload": "Upload command received. Future integration will call the Python control API.",
  "/process": "Process command received. Future integration will call the Python control API.",
  "/queue": "Queue command received. Future integration will read the pipeline queue status.",
  "/private": "Private command received. Future integration will manage privacy defaults.",
};

const HELP_TEXT = [
  "Telegram Control Worker commands:",
  "/start - Check bot startup",
  "/help - Show commands",
  "/health - Check Worker health",
  "/upload - Mock upload control",
  "/process - Mock pipeline processing control",
  "/queue - Mock queue status",
  "/private - Mock privacy control",
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

async function handleTelegramUpdate(request, env, ctx) {
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
  const reply = replyForCommand(command);
  try {
    await sendTelegram(env, chatId, reply);
    return jsonResponse({ ok: true });
  } catch (error) {
    console.error("telegram_send_failed", {
      chatId: String(chatId),
      error: error instanceof Error ? error.message : String(error),
    });
    return jsonResponse({ ok: false, error: "telegram_send_failed" }, 502);
  }
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/") {
      return new Response("Telegram Control Worker Online ✅", {
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }

    if (request.method === "GET" && url.pathname === "/health") {
      return jsonResponse({ ok: true, service: "telegram-control-worker" });
    }

    if (request.method === "POST" && (url.pathname === "/" || url.pathname === "/telegram/webhook")) {
      return handleTelegramUpdate(request, env, ctx);
    }

    return jsonResponse({ ok: false, error: "not_found" }, 404);
  },
};

export { HELP_TEXT, normalizeCommand, replyForCommand, sendTelegram };
