from __future__ import annotations

import unittest

from scripts.setup_google_sheet_schema import (
    SCHEMAS,
    apply_dropdowns,
    ensure_headers_and_sample_row,
    setup_schema,
)


class FakeWorksheet:
    def __init__(self, title: str, values=None, supports_validation: bool = True):
        self.title = title
        self.values = values or []
        self.updates = []
        self.validations = []
        if not supports_validation:
            self.add_validation = None

    def row_values(self, row_number: int):
        if row_number - 1 < len(self.values):
            return self.values[row_number - 1]
        return []

    def get_all_values(self):
        return self.values

    def update(self, cell_range: str, values):
        self.updates.append((cell_range, values))
        row_number = int("".join(ch for ch in cell_range.split(":")[0] if ch.isdigit()))
        while len(self.values) < row_number:
            self.values.append([])
        self.values[row_number - 1] = list(values[0])

    def add_validation(self, cell_range: str, condition_type: str, values, **kwargs):
        self.validations.append((cell_range, condition_type, list(values), kwargs))


class FakeSpreadsheet:
    def __init__(self, worksheets=None):
        self._worksheets = worksheets or []
        self.created = []

    def worksheets(self):
        return self._worksheets

    def add_worksheet(self, title: str, rows: int, cols: int):
        worksheet = FakeWorksheet(title)
        self._worksheets.append(worksheet)
        self.created.append((title, rows, cols))
        return worksheet


class SetupGoogleSheetSchemaTests(unittest.TestCase):
    def test_setup_schema_creates_missing_tabs(self) -> None:
        spreadsheet = FakeSpreadsheet([])

        results = setup_schema(spreadsheet)

        self.assertEqual({name for name, _rows, _cols in spreadsheet.created}, {schema.name for schema in SCHEMAS})
        self.assertIn("VIDEO_QUEUE", results)

    def test_ensure_headers_appends_missing_headers_without_deleting_existing_data(self) -> None:
        schema = next(item for item in SCHEMAS if item.name == "RENDER_PRESET")
        worksheet = FakeWorksheet("RENDER_PRESET", [["render_preset_id", "speed"], ["custom", "1.0"]])

        headers = ensure_headers_and_sample_row(worksheet, schema)

        self.assertIn("fit_mode", headers)
        self.assertIn("replace_audio_with_tts", headers)
        self.assertEqual(worksheet.values[1], ["custom", "1.0"])

    def test_sample_row_added_only_when_sheet_has_no_data_rows(self) -> None:
        schema = next(item for item in SCHEMAS if item.name == "VOICE_CONFIG")
        worksheet = FakeWorksheet("VOICE_CONFIG", [[]])

        ensure_headers_and_sample_row(worksheet, schema)

        self.assertEqual(worksheet.values[1][0], "voice_female_1")

    def test_apply_dropdowns_for_matching_headers(self) -> None:
        worksheet = FakeWorksheet("VIDEO_QUEUE")

        count = apply_dropdowns(worksheet, ["status", "privacyStatus", "not_dropdown"])

        self.assertEqual(count, 2)
        self.assertEqual(worksheet.validations[0][0], "A2:A1000")
        self.assertEqual(worksheet.validations[1][0], "B2:B1000")


if __name__ == "__main__":
    unittest.main()
