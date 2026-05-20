from __future__ import annotations

import unittest

from processors.sheet_client import SheetConfig


class FakeCell:
    def __init__(self, row):
        self.row = row


class FakeLedgerWorksheet:
    def __init__(self):
        self.headers = ["uploaded_id", "job_id", "youtube_video_id", "youtube_url"]
        self.rows = []
        self.updated = []

    def row_values(self, row_number):
        return self.headers

    def find(self, value, in_column=None):
        for index, row in enumerate(self.rows, start=2):
            if row[in_column - 1] == value:
                return FakeCell(index)
        return None

    def append_row(self, values, value_input_option=None):
        self.rows.append(values)

    def update(self, cell_range, values):
        self.updated.append((cell_range, values))
        row_number = int("".join(ch for ch in cell_range.split(":")[0] if ch.isdigit()))
        self.rows[row_number - 2] = values[0]


class FakeSpreadsheet:
    def __init__(self, worksheet):
        self._worksheet = worksheet

    def worksheet(self, name):
        return self._worksheet


class UploadedLedgerTests(unittest.TestCase):
    def test_upsert_uploaded_video_appends_then_updates_by_job_id(self) -> None:
        worksheet = FakeLedgerWorksheet()
        sheet = SheetConfig("", "")
        sheet._sh = FakeSpreadsheet(worksheet)

        first = sheet.upsert_uploaded_video(
            {"uploaded_id": "u1", "job_id": "job_1", "youtube_video_id": "yt1", "youtube_url": "url1"}
        )
        second = sheet.upsert_uploaded_video(
            {"uploaded_id": "u1", "job_id": "job_1", "youtube_video_id": "yt1", "youtube_url": "url2"}
        )

        self.assertEqual(first, "appended")
        self.assertEqual(second, "updated")
        self.assertEqual(len(worksheet.rows), 1)
        self.assertEqual(worksheet.rows[0][3], "url2")

    def test_upsert_uploaded_video_updates_by_youtube_video_id(self) -> None:
        worksheet = FakeLedgerWorksheet()
        worksheet.rows.append(["old", "old_job", "yt1", "old_url"])
        sheet = SheetConfig("", "")
        sheet._sh = FakeSpreadsheet(worksheet)

        result = sheet.upsert_uploaded_video(
            {"uploaded_id": "u1", "job_id": "job_1", "youtube_video_id": "yt1", "youtube_url": "new_url"}
        )

        self.assertEqual(result, "updated")
        self.assertEqual(len(worksheet.rows), 1)
        self.assertEqual(worksheet.rows[0][1], "job_1")


if __name__ == "__main__":
    unittest.main()
