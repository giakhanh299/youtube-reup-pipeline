from __future__ import annotations

from pathlib import Path
import csv
import json
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.config_loader import ConfigLoader
from processors.sheet_client import SheetConfig


class SnapshotExportError(RuntimeError):
    pass


def _required_text(settings: dict, key: str, message: str) -> str:
    value = str(settings.get(key, "")).strip()
    if not value:
        raise SnapshotExportError(message)
    return value


def worksheet_name_from_settings(settings: dict) -> str:
    name = str(settings.get("google_sheet_name", "")).strip()
    if not name:
        name = str(settings.get("upload_sheet_name", "")).strip()
    if not name:
        raise SnapshotExportError("Missing sheet name: set google_sheet_name or upload_sheet_name in configs/settings.json")
    return name


def rows_from_values(values: list[list[Any]]) -> list[dict]:
    if not values:
        return []
    headers = [str(header).strip() for header in values[0]]
    if not any(headers):
        return []

    rows: list[dict] = []
    for raw_row in values[1:]:
        row = {}
        has_value = False
        for index, header in enumerate(headers):
            if not header:
                continue
            value = raw_row[index] if index < len(raw_row) else ""
            if str(value).strip():
                has_value = True
            row[header] = value
        if has_value:
            rows.append(row)
    return rows


def write_snapshot(rows: list[dict], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    headers: list[str] = []
    for row in rows:
        for key in row:
            if key not in headers:
                headers.append(key)

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def export_snapshot(settings: dict, root: Path = ROOT) -> tuple[Path, Path, int]:
    spreadsheet_id = _required_text(settings, "spreadsheet_id", "Missing spreadsheet id: set spreadsheet_id in configs/settings.json")
    service_account_json = _required_text(
        settings,
        "service_account_json",
        "Missing config: set service_account_json in configs/settings.json",
    )
    worksheet_name = worksheet_name_from_settings(settings)

    sheet = SheetConfig(spreadsheet_id, service_account_json)
    try:
        sheet.connect()
    except Exception as exc:
        raise SnapshotExportError(f"Google Sheets auth failed: {exc}") from exc

    try:
        worksheet = sheet._sh.worksheet(worksheet_name)
        values = worksheet.get_all_values()
    except Exception as exc:
        raise SnapshotExportError(f"Google Sheets API failed while reading worksheet '{worksheet_name}': {exc}") from exc

    rows = rows_from_values(values)
    runtime_dir = root / "runtime"
    json_path = runtime_dir / "sheet_snapshot.json"
    csv_path = runtime_dir / "sheet_snapshot.csv"
    write_snapshot(rows, json_path, csv_path)
    return json_path, csv_path, len(rows)


def main() -> int:
    try:
        settings = ConfigLoader(ROOT).load_settings()
        json_path, csv_path, count = export_snapshot(settings, ROOT)
        print(f"OK exported {count} rows")
        print(f"OK JSON: {json_path}")
        print(f"OK CSV: {csv_path}")
        return 0
    except FileNotFoundError as exc:
        print(f"ERROR missing config: {exc}", file=sys.stderr)
        return 1
    except SnapshotExportError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR snapshot export failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
