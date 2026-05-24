function getRequiredScriptProperty(name) {
  const value = PropertiesService.getScriptProperties().getProperty(name);
  if (!value) {
    throw new Error("Missing Script Property: " + name);
  }
  return value;
}

function getOptionalScriptProperty(name, defaultValue) {
  const value = PropertiesService.getScriptProperties().getProperty(name);
  return value || defaultValue || "";
}

function updateDriveLinksUnlimited() {

  const sheet = SpreadsheetApp
    .getActiveSpreadsheet()
    .getSheetByName("Getvideo");

  if (!sheet) {
    return "❌ Không tìm thấy tab Getvideo";
  }

  const lastRow = sheet.getLastRow();

  if (lastRow < 2) {
    return "❌ Không có dữ liệu";
  }

  // Folder Drive
  const folderName = "Video Douyin";

  const folderIterator =
    DriveApp.getFoldersByName(folderName);

  const folder = folderIterator.hasNext()
    ? folderIterator.next()
    : DriveApp.createFolder(folderName);

  // Lấy toàn bộ data
  const data = sheet
    .getRange(2, 1, lastRow - 1, 11)
    .getValues();

  let success = 0;

  for (let i = 0; i < data.length; i++) {

    const row = data[i];

    const videoId = row[0];       // A
    const title = row[9];         // J
    const mp4Link = row[4];       // E
    const currentDrive = row[7];  // H

    // Nếu đã có link Drive thì bỏ qua
    if (currentDrive) {
      continue;
    }

    // Không có link mp4 thì bỏ qua
    if (!mp4Link) {
      continue;
    }

    try {

      // Tải video
      const response =
        UrlFetchApp.fetch(mp4Link);

      const blob = response.getBlob();

      // Tên file an toàn
      const safeName =
        String(title || videoId)
          .replace(/[/\\?%*:|"<>]/g, "-")
          .substring(0, 80);

      // Upload Drive
      const file =
        folder.createFile(blob);

      file.setName(safeName + ".mp4");

      // Public link
      file.setSharing(
        DriveApp.Access.ANYONE_WITH_LINK,
        DriveApp.Permission.VIEW
      );

      // Ghi link vào cột H
      sheet.getRange(i + 2, 8)
        .setValue(file.getUrl());

      success++;

      Utilities.sleep(500);

    } catch (e) {

      Logger.log(
        "❌ Lỗi dòng " +
        (i + 2) +
        ": " +
        e.message
      );
    }
  }

  return "✅ Đã upload " + success + " video lên Drive";
}

function installChannelAddedTrigger() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const existing = ScriptApp.getProjectTriggers()
    .filter(trigger => trigger.getHandlerFunction() === "handleChannelConfigEdit");
  for (const trigger of existing) {
    ScriptApp.deleteTrigger(trigger);
  }
  ScriptApp.newTrigger("handleChannelConfigEdit")
    .forSpreadsheet(ss)
    .onEdit()
    .create();
  return "✅ Đã cài trigger tự động báo Cloudflare khi kênh được đánh dấu Lấy";
}

function handleChannelConfigEdit(e) {
  if (!e || !e.range) {
    return;
  }

  const sheet = e.range.getSheet();
  if (sheet.getName() !== "Linkchanel douyin") {
    return;
  }

  const row = e.range.getRow();
  const column = e.range.getColumn();
  if (row < 2 || column !== 4) {
    return;
  }

  if (String(e.value || "").trim() !== "Lấy") {
    return;
  }

  notifyCloudflareChannelAdded_(sheet, row);
}

function notifyCloudflareChannelAdded_(sheet, row) {
  const workerUrl = getOptionalScriptProperty("TELEGRAM_CONTROL_URL", "");
  const sharedSecret = getOptionalScriptProperty("GAS_SHARED_SECRET", "");
  if (!workerUrl || !sharedSecret) {
    Logger.log("Cloudflare notify skipped: TELEGRAM_CONTROL_URL or GAS_SHARED_SECRET is missing");
    return;
  }

  const values = sheet.getRange(row, 1, 1, 4).getValues()[0];
  const payload = {
    source: "apps_script",
    event: "channel_marked_for_fetch",
    sheet: sheet.getName(),
    row: row,
    channelName: String(values[0] || "").trim(),
    chineseName: String(values[1] || "").trim(),
    secUid: String(values[2] || "").trim(),
    status: String(values[3] || "").trim()
  };

  try {
    UrlFetchApp.fetch(workerUrl.replace(/\/$/, "") + "/gas/channel-added", {
      method: "post",
      contentType: "application/json",
      headers: {
        "x-gas-secret": sharedSecret
      },
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    });
  } catch (error) {
    Logger.log("Cloudflare notify failed: " + error.message);
  }
}
