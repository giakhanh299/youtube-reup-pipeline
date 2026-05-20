from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.config_loader import ConfigLoader
from processors.sheet_client import SheetConfig

try:
    from gspread.utils import ValidationConditionType
except Exception:
    ValidationConditionType = None


class SheetSchemaSetupError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorksheetSchema:
    name: str
    headers: list[str]
    sample_row: list[str]


SCHEMAS = [
    WorksheetSchema(
        "CHANNEL_CONFIG",
        [
            "channel_id",
            "enabled",
            "input_folder",
            "output_folder",
            "voice_id",
            "music_pack_id",
            "overlay_pack_id",
            "render_preset_id",
            "subtitle_style_id",
            "use_nvenc",
            "background_blur",
            "blur_strength",
            "speed",
            "logo_path",
            "logo_opacity",
            "logo_x",
            "logo_y",
            "music_path",
            "music_volume",
            "channel_description",
            "channel_style_prompt",
            "title_template",
            "description_template",
            "tags_default",
            "metadata_ai_enabled",
        ],
        [
            "kenh_1",
            "TRUE",
            "runtime/input/kenh_1",
            "runtime/output/kenh_1",
            "voice_female_1",
            "music_chill",
            "overlay_logo_1",
            "shorts_blur",
            "sub_yellow",
            "TRUE",
            "TRUE",
            "28",
            "1.0",
            "",
            "0.16",
            "30",
            "40",
            "",
            "0.07",
            "",
            "",
            "{title}",
            "{title}",
            "shorts,reup",
            "FALSE",
        ],
    ),
    WorksheetSchema(
        "VOICE_CONFIG",
        [
            "voice_id",
            "active",
            "engine",
            "tts_engine",
            "language_code",
            "language",
            "name",
            "gender",
            "speaking_rate",
            "speed",
            "pitch",
            "volume_gain_db",
            "command",
            "ref_audio_path",
            "ref_text",
        ],
        ["voice_omnivoice_1", "TRUE", "omnivoice_local", "omnivoice_local", "vi", "vi", "", "", "1.0", "1.0", "0", "0", "", "runtime/ref/ref.wav", ""],
    ),
    WorksheetSchema(
        "MUSIC_PACK",
        ["music_pack_id", "active", "music_path", "music_volume"],
        ["music_chill", "TRUE", "runtime/assets/music/chill.mp3", "0.07"],
    ),
    WorksheetSchema(
        "OVERLAY_PACK",
        ["overlay_pack_id", "active", "logo_path", "logo_opacity", "logo_x", "logo_y", "background_blur", "blur_strength"],
        ["overlay_logo_1", "TRUE", "runtime/assets/logo/logo.png", "0.16", "30", "40", "TRUE", "28"],
    ),
    WorksheetSchema(
        "RENDER_PRESET",
        [
            "render_preset_id",
            "use_nvenc",
            "background_blur",
            "blur_strength",
            "speed",
            "fit_mode",
            "output_width",
            "output_height",
            "keep_original_audio",
            "replace_audio_with_tts",
        ],
        ["shorts_blur", "TRUE", "TRUE", "28", "1.0", "vertical_blur", "1080", "1920", "FALSE", "TRUE"],
    ),
    WorksheetSchema(
        "VIDEO_QUEUE",
        [
            "job_id",
            "status",
            "channel_id",
            "video_path",
            "text_path",
            "output_path",
            "error",
            "title",
            "description",
            "tags",
            "categoryId",
            "privacyStatus",
            "channel_key",
            "upload_status",
            "youtube_video_id",
            "upload_error",
            "upload_time",
            "retry_count",
            "last_error",
            "upload_started_at",
            "upload_finished_at",
            "original_title",
            "translated_title",
            "final_title",
            "final_description",
            "source_url",
            "source_video_id",
            "source_channel_id",
            "source_channel_url",
            "source_video_url",
            "title_original",
            "title_vi",
            "description_vi",
            "script_text",
            "ref_audio_path",
            "ref_text",
            "language",
            "voice_status",
            "voice_output_path",
            "voice_error",
        ],
        ["job_001", "NEW", "kenh_1", "runtime/test/test.mp4", "", "", "", "Sample title", "Sample description", "test,upload", "22", "private", "", "pending", "", "", "", "0", "", "", "", "Original title", "", "", "", "", "", "", "", "", "Original title", "", "", "", "runtime/ref/ref.wav", "", "vi", "pending", "", ""],
    ),
    WorksheetSchema(
        "UPLOADED_VIDEOS",
        [
            "uploaded_id",
            "job_id",
            "channel_id",
            "channel_name",
            "account_name",
            "source_channel_id",
            "source_url",
            "source_video_id",
            "original_title",
            "translated_title",
            "final_title",
            "final_description",
            "tags",
            "categoryId",
            "privacyStatus",
            "youtube_video_id",
            "youtube_url",
            "upload_time",
            "video_path",
            "rendered_video_path",
            "voice_id",
            "render_preset_id",
            "upload_status",
            "ledger_status",
            "notes",
        ],
        ["", "", "", "", "", "", "", "", "", "", "", "", "", "22", "private", "", "", "", "", "", "", "", "uploaded", "active", ""],
    ),
]


DROPDOWN_VALUES = {
    "status": ["NEW", "PROCESSING", "READY_UPLOAD", "UPLOADED", "ERROR"],
    "upload_status": ["pending", "uploading", "uploaded", "failed", "skipped"],
    "privacyStatus": ["private", "unlisted", "public"],
    "channel_id": ["kenh_1"],
    "voice_id": ["voice_omnivoice_1"],
    "tts_engine": ["omnivoice_local"],
    "engine": ["omnivoice_local"],
    "voice_status": ["pending", "processing", "done", "error"],
    "music_pack_id": ["music_chill", "music_dark"],
    "overlay_pack_id": ["overlay_logo_1", "overlay_logo_2"],
    "render_preset_id": ["shorts_blur", "shorts_blur_fast"],
    "fit_mode": ["vertical_blur", "contain", "cover"],
    "background_blur": ["TRUE", "FALSE"],
    "keep_original_audio": ["TRUE", "FALSE"],
    "replace_audio_with_tts": ["TRUE", "FALSE"],
    "ledger_status": ["active", "private", "public", "deleted", "error", "duplicate"],
    "metadata_ai_enabled": ["TRUE", "FALSE"],
}


def _required_text(settings: dict, key: str) -> str:
    value = str(settings.get(key, "")).strip()
    if not value:
        raise SheetSchemaSetupError(f"Missing required config: {key}")
    return value


def _worksheets_by_title(spreadsheet: Any) -> dict[str, Any]:
    return {ws.title: ws for ws in spreadsheet.worksheets()}


def _ensure_worksheet(spreadsheet: Any, schema: WorksheetSchema) -> Any:
    worksheets = _worksheets_by_title(spreadsheet)
    if schema.name in worksheets:
        return worksheets[schema.name]
    rows = max(100, len(schema.sample_row) + 10)
    cols = max(26, len(schema.headers) + 5)
    return spreadsheet.add_worksheet(title=schema.name, rows=rows, cols=cols)


def _merge_headers(existing: list[str], required: list[str]) -> list[str]:
    merged = [header for header in existing if str(header).strip()]
    for header in required:
        if header not in merged:
            merged.append(header)
    return merged


def _update_row(worksheet: Any, row_number: int, values: list[str]) -> None:
    end_col = _column_letter(len(values))
    cell_range = f"A{row_number}:{end_col}{row_number}"
    try:
        worksheet.update(values=[values], range_name=cell_range)
    except TypeError:
        worksheet.update(cell_range, [values])


def _column_letter(index: int) -> str:
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters or "A"


def ensure_headers_and_sample_row(worksheet: Any, schema: WorksheetSchema) -> list[str]:
    existing_headers = [str(value).strip() for value in worksheet.row_values(1)]
    headers = _merge_headers(existing_headers, schema.headers)
    if headers != existing_headers:
        _update_row(worksheet, 1, headers)

    data_rows = worksheet.get_all_values()[1:]
    has_data = any(any(str(cell).strip() for cell in row) for row in data_rows)
    if not has_data:
        sample_by_header = dict(zip(schema.headers, schema.sample_row))
        sample = [sample_by_header.get(header, "") for header in headers]
        _update_row(worksheet, 2, sample)
    return headers


def apply_dropdowns(worksheet: Any, headers: list[str]) -> int:
    applied = 0
    add_validation = getattr(worksheet, "add_validation", None)
    if not callable(add_validation) or ValidationConditionType is None:
        return applied
    for header, values in DROPDOWN_VALUES.items():
        if header not in headers:
            continue
        col = _column_letter(headers.index(header) + 1)
        cell_range = f"{col}2:{col}1000"
        try:
            add_validation(cell_range, ValidationConditionType.one_of_list, values, strict=True, showCustomUi=True)
            applied += 1
        except TypeError:
            add_validation(cell_range, ValidationConditionType.one_of_list, values)
            applied += 1
    return applied


def setup_schema(spreadsheet: Any) -> dict[str, dict[str, int]]:
    results: dict[str, dict[str, int]] = {}
    for schema in SCHEMAS:
        worksheet = _ensure_worksheet(spreadsheet, schema)
        headers = ensure_headers_and_sample_row(worksheet, schema)
        validations = apply_dropdowns(worksheet, headers)
        results[schema.name] = {"headers": len(headers), "validations": validations}
    return results


def connect_spreadsheet(settings: dict) -> Any:
    spreadsheet_id = _required_text(settings, "spreadsheet_id")
    service_account_json = _required_text(settings, "service_account_json")
    sheet = SheetConfig(spreadsheet_id, service_account_json)
    try:
        sheet.connect()
    except Exception as exc:
        raise SheetSchemaSetupError(f"Google Sheets auth/connect failed: {exc}") from exc
    return sheet._sh


def main() -> int:
    try:
        settings = ConfigLoader(ROOT).load_settings()
        spreadsheet = connect_spreadsheet(settings)
        results = setup_schema(spreadsheet)
        for name, result in results.items():
            print(f"OK {name}: {result['headers']} headers, {result['validations']} dropdowns")
        print("OK Google Sheet schema setup complete")
        return 0
    except SheetSchemaSetupError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR schema setup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
