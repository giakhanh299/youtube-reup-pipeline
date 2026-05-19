from __future__ import annotations
from pathlib import Path
from typing import Any
import csv


def _clean_key(key: str) -> str:
    return str(key).strip()


def _clean_value(value: Any) -> Any:
    if value is None:
        return ""
    value = str(value).strip()
    if value.upper() == "TRUE":
        return True
    if value.upper() == "FALSE":
        return False
    return value


def to_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y", "on", "bật", "bat"}


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "."))
    except Exception:
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return default


def row_id(row: dict, preferred: str) -> str:
    return str(row.get(preferred, "")).strip()


class SheetConfig:
    """Đọc toàn bộ config từ Google Sheet.

    Cần service account JSON có quyền xem/sửa Sheet.
    Share Google Sheet cho email client_email trong file JSON.
    """

    def __init__(self, spreadsheet_id: str, service_account_json: str):
        self.spreadsheet_id = spreadsheet_id
        self.service_account_json = service_account_json
        self._gc = None
        self._sh = None

    def connect(self):
        import gspread
        self._gc = gspread.service_account(filename=self.service_account_json)
        self._sh = self._gc.open_by_key(self.spreadsheet_id)
        return self

    def rows(self, worksheet_name: str) -> list[dict]:
        if self._sh is None:
            self.connect()
        ws = self._sh.worksheet(worksheet_name)
        data = ws.get_all_records()
        cleaned: list[dict] = []
        for row in data:
            item = {_clean_key(k): _clean_value(v) for k, v in row.items()}
            if any(str(v).strip() for v in item.values()):
                cleaned.append(item)
        return cleaned

    def rows_with_numbers(self, worksheet_name: str) -> list[tuple[int, dict]]:
        if self._sh is None:
            self.connect()
        ws = self._sh.worksheet(worksheet_name)
        data = ws.get_all_records()
        cleaned: list[tuple[int, dict]] = []
        for row_number, row in enumerate(data, start=2):
            item = {_clean_key(k): _clean_value(v) for k, v in row.items()}
            if any(str(v).strip() for v in item.values()):
                cleaned.append((row_number, item))
        return cleaned

    def map_by(self, worksheet_name: str, key_col: str) -> dict[str, dict]:
        result = {}
        for row in self.rows(worksheet_name):
            key = row_id(row, key_col)
            if key:
                result[key] = row
        return result

    def update_status_by_job_id(self, job_id: str, status: str, output_path: str = "", error: str = "") -> None:
        if self._sh is None:
            self.connect()
        import gspread
        ws = self._sh.worksheet("VIDEO_QUEUE")
        headers = ws.row_values(1)
        id_col = headers.index("job_id") + 1
        status_col = headers.index("status") + 1 if "status" in headers else None
        output_col = headers.index("output_path") + 1 if "output_path" in headers else None
        error_col = headers.index("error") + 1 if "error" in headers else None
        cell = ws.find(job_id, in_column=id_col)
        if not cell:
            return
        updates = []
        if status_col:
            updates.append({"range": gspread.utils.rowcol_to_a1(cell.row, status_col), "values": [[status]]})
        if output_col:
            updates.append({"range": gspread.utils.rowcol_to_a1(cell.row, output_col), "values": [[output_path]]})
        if error_col:
            updates.append({"range": gspread.utils.rowcol_to_a1(cell.row, error_col), "values": [[error[:1000]]]})
        if updates:
            ws.batch_update(updates)

    def update_upload_result(
        self,
        worksheet_name: str,
        row_number: int,
        upload_status: str,
        youtube_video_id: str = "",
        upload_error: str = "",
        upload_time: str = "",
        retry_count: int | str | None = None,
        last_error: str = "",
        upload_started_at: str = "",
        upload_finished_at: str = "",
    ) -> None:
        if self._sh is None:
            self.connect()
        import gspread
        ws = self._sh.worksheet(worksheet_name)
        headers = ws.row_values(1)
        updates = []
        values_by_column = {
            "upload_status": upload_status,
            "youtube_video_id": youtube_video_id,
            "upload_error": upload_error[:1000],
            "upload_time": upload_time,
            "last_error": last_error[:1000],
            "upload_started_at": upload_started_at,
            "upload_finished_at": upload_finished_at,
        }
        if retry_count is not None:
            values_by_column["retry_count"] = retry_count
        for header, value in values_by_column.items():
            if header in headers:
                col = headers.index(header) + 1
                updates.append({"range": gspread.utils.rowcol_to_a1(row_number, col), "values": [[value]]})
        if updates:
            ws.batch_update(updates)


def load_csv_rows(path: str | Path) -> list[dict]:
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [{_clean_key(k): _clean_value(v) for k, v in row.items()} for row in reader]
