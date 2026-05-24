function updateDriveLinks() {

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

  // =========================================================================
  // CHỈ UPLOAD TỐI ĐA 10 VIDEO MỖI LẦN CHẠY
  // =========================================================================

  const MAX_UPLOAD_PER_RUN = 10;

  // =========================================================================
  // FOLDER DRIVE
  // =========================================================================

  const folderName = "Video Douyin";

  const folderIterator =
    DriveApp.getFoldersByName(folderName);

  const folder = folderIterator.hasNext()
    ? folderIterator.next()
    : DriveApp.createFolder(folderName);

  // =========================================================================
  // ĐỌC DỮ LIỆU
  // =========================================================================

  const data = sheet
    .getRange(2, 1, lastRow - 1, 11)
    .getValues();

  let success = 0;

  for (let i = 0; i < data.length; i++) {

    // Nếu đã đủ 10 video thì dừng
    if (success >= MAX_UPLOAD_PER_RUN) {
      break;
    }

    const row = data[i];

    const videoId = row[0];       // A
    const mp4Link = row[4];       // E
    const driveLink = row[7];     // H
    const title = row[9];         // J

    // Đã có link Drive => bỏ qua
    if (driveLink) {
      continue;
    }

    // Không có link mp4 => bỏ qua
    if (!mp4Link) {
      continue;
    }

    try {

      Logger.log(
        "⬇️ Đang tải video: " + videoId
      );

      // =========================================================================
      // TẢI VIDEO
      // =========================================================================

      const response =
        UrlFetchApp.fetch(mp4Link);

      const blob = response.getBlob();

      // =========================================================================
      // TÊN FILE
      // =========================================================================

      const safeName =
        String(title || videoId)
          .replace(/[/\\?%*:|"<>]/g, "-")
          .substring(0, 80);

      // =========================================================================
      // UPLOAD DRIVE
      // =========================================================================

      const file =
        folder.createFile(blob);

      file.setName(safeName + ".mp4");

      // Public link
      file.setSharing(
        DriveApp.Access.ANYONE_WITH_LINK,
        DriveApp.Permission.VIEW
      );

      // =========================================================================
      // GHI LINK DRIVE VÀO CỘT H
      // =========================================================================

      sheet
        .getRange(i + 2, 8)
        .setValue(file.getUrl());

      success++;

      Logger.log(
        "✅ Upload thành công: " + safeName
      );

      // Nghỉ tránh rate limit
      Utilities.sleep(1000);

    } catch (e) {

      Logger.log(
        "❌ Lỗi dòng " +
        (i + 2) +
        ": " +
        e.message
      );
    }
  }

  return "✅ Đã upload " + success + " video lên Google Drive";
}