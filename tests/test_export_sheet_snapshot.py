from __future__ import annotations

from pathlib import Path
import csv
import json
import tempfile
import unittest

from scripts.export_sheet_snapshot import (
    SnapshotExportError,
    rows_from_values,
    worksheet_name_from_settings,
    write_snapshot,
)


class ExportSheetSnapshotTests(unittest.TestCase):
    def test_rows_from_values_uses_first_row_as_headers(self) -> None:
        rows = rows_from_values(
            [
                ["video_path", "title", ""],
                ["a.mp4", "Title A", "ignored"],
                ["", "", ""],
                ["b.mp4"],
            ]
        )

        self.assertEqual(
            rows,
            [
                {"video_path": "a.mp4", "title": "Title A"},
                {"video_path": "b.mp4", "title": ""},
            ],
        )

    def test_worksheet_name_uses_google_sheet_name_then_upload_sheet_name(self) -> None:
        self.assertEqual(worksheet_name_from_settings({"google_sheet_name": "Main", "upload_sheet_name": "Upload"}), "Main")
        self.assertEqual(worksheet_name_from_settings({"upload_sheet_name": "Upload"}), "Upload")

    def test_worksheet_name_requires_configured_name(self) -> None:
        with self.assertRaisesRegex(SnapshotExportError, "Missing sheet name"):
            worksheet_name_from_settings({})

    def test_write_snapshot_creates_json_and_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            json_path = Path(temp) / "runtime" / "sheet_snapshot.json"
            csv_path = Path(temp) / "runtime" / "sheet_snapshot.csv"

            write_snapshot([{"video_path": "a.mp4", "title": "Tieu de"}], json_path, csv_path)

            json_data = json.loads(json_path.read_text(encoding="utf-8"))
            with csv_path.open("r", encoding="utf-8", newline="") as handle:
                csv_data = list(csv.DictReader(handle))

        self.assertEqual(json_data[0]["video_path"], "a.mp4")
        self.assertEqual(csv_data[0]["title"], "Tieu de")


if __name__ == "__main__":
    unittest.main()
