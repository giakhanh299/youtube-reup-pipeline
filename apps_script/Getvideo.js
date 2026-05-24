// =========================================================================
// QUY TRÌNH TỰ ĐỘNG HÓA VIDEO GIA KHÁNH CHANNEL
// Linkchanel douyin -> Getvideo
// Không dùng Script Properties
// =========================================================================

function getDouyinVideoLinks2() {

  const ss = SpreadsheetApp.getActiveSpreadsheet();

  const sourceSheet = ss.getSheetByName("Linkchanel douyin");
  const targetSheet = ss.getSheetByName("Getvideo");

  if (!sourceSheet || !targetSheet) {
    return "❌ Không tìm thấy tab Linkchanel douyin hoặc Getvideo.";
  }

  // =========================================================================
  // LẤY ID ĐÃ TỒN TẠI ĐỂ TRÁNH TRÙNG
  // =========================================================================

  const existingIds = tgExistingDouyinVideoIds_(targetSheet);

  // =========================================================================
  // ĐỌC TAB LINKCHANNEL DOUYIN
  // =========================================================================

  const lastSourceRow = sourceSheet.getLastRow();

  if (lastSourceRow < 2) {
    return "💡 Tab Linkchanel douyin trống.";
  }

  const sourceData = sourceSheet
    .getRange(2, 1, lastSourceRow - 1, 4)
    .getValues();

  // A = Tên kênh
  // B = Tên trung quốc
  // C = ID User
  // D = Lấy video

  const channels = sourceData
    .filter(row => row[2] && String(row[3]).trim() === "Lấy")
    .map(row => ({
      channelName: String(row[0] || "").trim(),
      chineseName: String(row[1] || "").trim(),
      secUid: String(row[2] || "").trim()
    }));

  if (channels.length === 0) {
    return "💡 Không có kênh nào đang để trạng thái Lấy.";
  }

  const rowsToWrite = [];

  for (const channel of channels) {
    try {
      const result = tgFetchDouyinVideosForChannel_(
        channel.secUid,
        channel.channelName,
        existingIds
      );
      rowsToWrite.push(...result.rows);
    } catch (err) {

      Logger.log(
        "❌ Lỗi kênh " +
        channel.channelName +
        ": " +
        err.message
      );
    }
  }

  // =========================================================================
  // GHI DỮ LIỆU VÀO SHEET
  // =========================================================================

  if (rowsToWrite.length === 0) {
    return "💡 Không có video mới.";
  }

  tgWriteDouyinRows_(targetSheet, rowsToWrite);

  return `✅ Đã thêm ${rowsToWrite.length} video mới vào Getvideo.`;
}

function getDouyinVideoLinksByRow(rowNumber) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sourceSheet = ss.getSheetByName("Linkchanel douyin");
  const targetSheet = ss.getSheetByName("Getvideo");

  if (!sourceSheet || !targetSheet) {
    throw new Error("Không tìm thấy tab Linkchanel douyin hoặc Getvideo.");
  }

  const row = Number(rowNumber);
  if (!row || row < 2 || row > sourceSheet.getLastRow()) {
    throw new Error("Dòng kênh không hợp lệ: " + rowNumber);
  }

  const values = sourceSheet.getRange(row, 1, 1, 4).getValues()[0];
  const channelName = String(values[0] || "").trim();
  const chineseName = String(values[1] || "").trim();
  const douyinUserId = String(values[2] || "").trim();

  if (!douyinUserId) {
    throw new Error("Thiếu ID User Douyin ở dòng " + row);
  }

  const existingIds = tgExistingDouyinVideoIds_(targetSheet);
  const result = tgFetchDouyinVideosForChannel_(
    douyinUserId,
    channelName,
    existingIds
  );
  tgWriteDouyinRows_(targetSheet, result.rows);

  return {
    rowNumber: row,
    channelName: channelName,
    chineseName: chineseName,
    douyinUserId: douyinUserId,
    addedCount: result.addedCount,
    skippedDuplicateCount: result.skippedDuplicateCount
  };
}

function tgExistingDouyinVideoIds_(targetSheet) {
  const lastTargetRow = targetSheet.getLastRow();
  return new Set(
    lastTargetRow > 1
      ? targetSheet
          .getRange(2, 1, lastTargetRow - 1, 1)
          .getValues()
          .flat()
          .map(String)
      : []
  );
}

function tgFetchDouyinVideosForChannel_(douyinUserId, channelName, existingIds) {
  const apiKey = getRequiredScriptProperty("RAPIDAPI_KEY");
  const apiHost = "douyin-api-new.p.rapidapi.com";
  const apiUrl =
    "https://douyin-api-new.p.rapidapi.com/v1/social/douyin/web/aweme/post";
  const videoPerChannel = 2;

  const payload = {
    sec_user_id: douyinUserId,
    count: 20,
    max_cursor: "0"
  };

  const options = {
    method: "post",
    contentType: "application/json",
    headers: {
      "x-rapidapi-key": apiKey,
      "x-rapidapi-host": apiHost
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };

  const response = UrlFetchApp.fetch(apiUrl, options);
  if (response.getResponseCode() !== 200) {
    throw new Error("API lỗi " + channelName + ": " + response.getContentText());
  }

  const data = JSON.parse(response.getContentText());
  const videos = data.aweme_list || [];
  const rows = [];
  let skippedDuplicateCount = 0;

  for (const item of videos) {
    if (rows.length >= videoPerChannel) {
      break;
    }

    const videoId = String(item.aweme_id || "");
    if (!videoId) {
      continue;
    }

    if (existingIds.has(videoId)) {
      skippedDuplicateCount++;
      continue;
    }

    const video = item.video || {};
    const bitRates = video.bit_rate || [];
    const best =
      bitRates.find(br => String(br.gear_name || "").includes("1080")) ||
      bitRates.find(br => String(br.gear_name || "").includes("720")) ||
      bitRates[0];

    const videoLink =
      best?.play_addr?.url_list?.[0] ||
      video?.play_addr?.url_list?.[0] ||
      "";

    if (!videoLink) {
      continue;
    }

    const createDate = item.create_time
      ? new Date(item.create_time * 1000)
      : new Date();

    const dateStr = Utilities.formatDate(
      createDate,
      Session.getScriptTimeZone(),
      "dd/MM/yyyy HH:mm:ss"
    );
    const duration = Math.floor((video.duration || 0) / 1000);
    const daysAgo =
      Math.floor((new Date() - createDate) / (1000 * 60 * 60 * 24)) + " ngày";
    const originalDesc = item.desc || "";
    let translatedTitle = "";

    try {
      if (originalDesc) {
        translatedTitle = LanguageApp.translate(originalDesc, "zh", "vi")
          .replace(/#\S+/g, "")
          .trim();
      }
    } catch (e) {
      translatedTitle = "Lỗi dịch";
    }

    const row = new Array(11).fill("");
    row[0] = videoId;
    row[1] = dateStr;
    row[2] = duration;
    row[3] = originalDesc;
    row[4] = videoLink;
    row[5] = daysAgo;
    row[6] = "Lấy";
    row[7] = "";
    row[8] = "Hoàn thành";
    row[9] = translatedTitle;
    row[10] = channelName;

    rows.push(row);
    existingIds.add(videoId);
  }

  Utilities.sleep(300);

  return {
    rows: rows,
    addedCount: rows.length,
    skippedDuplicateCount: skippedDuplicateCount
  };
}

function tgWriteDouyinRows_(targetSheet, rowsToWrite) {
  if (!rowsToWrite.length) {
    return;
  }

  targetSheet.insertRowsBefore(2, rowsToWrite.length);

  const targetRange = targetSheet.getRange(
    2,
    1,
    rowsToWrite.length,
    11
  );

  targetRange.setValues(rowsToWrite);
  targetRange
    .setBackground("#FFFFFF")
    .setFontColor("#000000");
}
