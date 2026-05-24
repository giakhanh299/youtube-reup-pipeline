function doPost(e) {
  return telegramWebhook(e);
}

function telegramWebhook(e) {
  let update;
  try {
    update = JSON.parse(e.postData.contents || "{}");
  } catch (error) {
    return tgTextResponse_("invalid_json");
  }

  const callback = update.callback_query;
  if (callback && callback.data) {
    tgHandleChannelCallback_(callback);
    return tgTextResponse_("ok");
  }

  const message = update.message || {};
  const chatId = message.chat && message.chat.id;
  const text = String(message.text || "").trim();

  if (chatId && text === "/channels") {
    tgShowDouyinChannels_(chatId, 1);
    return tgTextResponse_("ok");
  }

  return tgTextResponse_("ok");
}

function tgShowDouyinChannels_(chatId, page) {
  const channels = tgGetDouyinChannels_();
  if (!channels.length) {
    tgSendMessage_(chatId, "Không có kênh nào trong tab Linkchanel douyin.");
    return;
  }

  const perPage = 10;
  const totalPages = Math.max(1, Math.ceil(channels.length / perPage));
  const safePage = Math.min(Math.max(Number(page) || 1, 1), totalPages);
  const start = (safePage - 1) * perPage;
  const pageChannels = channels.slice(start, start + perPage);

  tgSendMessage_(
    chatId,
    "Chọn kênh Douyin để lấy video:\nTrang " + safePage + "/" + totalPages,
    tgBuildChannelKeyboard_(pageChannels, safePage, totalPages)
  );
}

function tgBuildChannelKeyboard_(channels, page, totalPages) {
  const inlineKeyboard = channels.map(channel => [{
    text: channel.channelName || channel.chineseName || ("Dòng " + channel.rowNumber),
    callback_data: "channel_get_row_" + channel.rowNumber
  }]);

  const pageButtons = [];
  if (page > 1) {
    pageButtons.push({
      text: "‹ Trước",
      callback_data: "channels_page_" + (page - 1)
    });
  }
  if (page < totalPages) {
    pageButtons.push({
      text: "Sau ›",
      callback_data: "channels_page_" + (page + 1)
    });
  }
  if (pageButtons.length) {
    inlineKeyboard.push(pageButtons);
  }

  return {
    inline_keyboard: inlineKeyboard
  };
}

function tgGetDouyinChannels_() {
  const sheet = SpreadsheetApp
    .getActiveSpreadsheet()
    .getSheetByName("Linkchanel douyin");

  if (!sheet) {
    throw new Error("Không tìm thấy tab Linkchanel douyin");
  }

  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return [];
  }

  return sheet
    .getRange(2, 1, lastRow - 1, 4)
    .getValues()
    .map((row, index) => ({
      rowNumber: index + 2,
      channelName: String(row[0] || "").trim(),
      chineseName: String(row[1] || "").trim(),
      douyinUserId: String(row[2] || "").trim(),
      status: String(row[3] || "").trim()
    }))
    .filter(channel =>
      channel.channelName ||
      channel.chineseName ||
      channel.douyinUserId
    );
}

function tgHandleChannelCallback_(callback) {
  const data = String(callback.data || "");
  const chatId = callback.message && callback.message.chat && callback.message.chat.id;

  if (data.indexOf("channels_page_") === 0) {
    const page = Number(data.replace("channels_page_", ""));
    tgAnswerCallback_(callback.id, "Đang mở trang " + page);
    tgShowDouyinChannels_(chatId, page);
    return;
  }

  if (data.indexOf("channel_get_row_") === 0) {
    const rowNumber = Number(data.replace("channel_get_row_", ""));
    tgAnswerCallback_(callback.id, "Đang lấy video...");
    tgProcessDouyinChannelRow_(chatId, rowNumber);
    return;
  }

  tgAnswerCallback_(callback.id, "Lệnh không hợp lệ");
}

function tgProcessDouyinChannelRow_(chatId, rowNumber) {
  try {
    const result = getDouyinVideoLinksByRow(rowNumber);
    tgSendMessage_(
      chatId,
      [
        "Đã xử lý kênh: " + (result.channelName || result.chineseName || ("Dòng " + result.rowNumber)),
        "Đã thêm: " + result.addedCount,
        "Bỏ qua trùng: " + result.skippedDuplicateCount
      ].join("\n")
    );
  } catch (error) {
    tgSendMessage_(chatId, "❌ " + error.message);
  }
}

function tgSendMessage_(chatId, text, replyMarkup) {
  const token = getRequiredScriptProperty("TELEGRAM_BOT_TOKEN");
  const payload = {
    chat_id: chatId,
    text: text,
    disable_web_page_preview: true
  };
  if (replyMarkup) {
    payload.reply_markup = replyMarkup;
  }

  UrlFetchApp.fetch("https://api.telegram.org/bot" + token + "/sendMessage", {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
}

function tgAnswerCallback_(callbackId, text) {
  if (!callbackId) {
    return;
  }
  const token = getRequiredScriptProperty("TELEGRAM_BOT_TOKEN");
  UrlFetchApp.fetch("https://api.telegram.org/bot" + token + "/answerCallbackQuery", {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({
      callback_query_id: callbackId,
      text: text || ""
    }),
    muteHttpExceptions: true
  });
}

function tgTextResponse_(text) {
  return ContentService
    .createTextOutput(String(text || "ok"))
    .setMimeType(ContentService.MimeType.TEXT);
}
