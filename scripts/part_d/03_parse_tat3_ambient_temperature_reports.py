#!/usr/bin/env python3
"""Parse exported TAT3 thermal reports for per-image ambient temperature.

The raw TAT3 reports are expected to live in an ignored local directory such
as data/local_external/tat3_reports/raw. This script stores only compact
parsed tables and a summary under outputs/part_d.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from table_io import write_rows

DEFAULT_REPORT_DIR = PROJECT_ROOT / "data" / "local_external" / "tat3_reports" / "raw"
PILOT_PAIRS_XLSX = PROJECT_ROOT / "data" / "metadata" / "part_b_pilot_pairs.xlsx"
VT_PAIRS_XLSX = PROJECT_ROOT / "data" / "metadata" / "vt_pairs.xlsx"
DJI_METADATA_XLSX = PROJECT_ROOT / "data" / "metadata" / "dji_image_metadata.xlsx"

OUTPUT_DIR = PROJECT_ROOT / "outputs" / "part_d" / "qa" / "tat3_parameter_audit"
ALL_ROWS_CSV = OUTPUT_DIR / "part_d_tat3_parameter_audit.csv"
ALL_ROWS_XLSX = OUTPUT_DIR / "part_d_tat3_parameter_audit.xlsx"
PILOT_ROWS_CSV = OUTPUT_DIR / "part_d_tat3_pilot_parameters.csv"
PILOT_ROWS_XLSX = OUTPUT_DIR / "part_d_tat3_pilot_parameters.xlsx"
SUMMARY_MD = PROJECT_ROOT / "outputs" / "part_d" / "summaries" / "part_d_tat3_parameter_ingest_summary.md"

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
FILENAME_RE = re.compile(r"\b(DJI_[A-Z0-9_]+_T\.JPE?G)\b", re.IGNORECASE)
DATETIME_RE = re.compile(r"\b\d{4}[/-]\d{2}[/-]\d{2}\s+\d{2}:\d{2}:\d{2}\b")
NUMBER_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")

FIELD_LABELS: dict[str, tuple[str, ...]] = {
    "distance_m": ("距离", "Distance", "Object Distance"),
    "humidity_percent": ("空气湿度", "相对湿度", "Humidity", "Relative Humidity"),
    "emissivity": ("发射率", "Emissivity"),
    "reflected_temperature_c": (
        "反射温度",
        "Reflected Temperature",
        "Reflected Apparent Temperature",
    ),
    "ambient_temperature_c": (
        "环境温度",
        "Ambient Temperature",
        "Ambient Temp",
        "Atmospheric Temperature",
    ),
    "camera_model": ("设备型号", "Camera Model", "Model"),
    "serial_number": ("序列号", "Serial Number"),
    "focal_length": ("焦距", "Focal Length"),
    "aperture": ("光圈", "Aperture"),
    "image_width": ("宽度", "Width"),
    "image_height": ("高度", "Height"),
    "created_time": ("创建时间", "Created Time", "Create Time"),
    "modified_time": ("修改时间", "Modified Time", "Modify Time"),
    "gps": ("经纬度", "GPS", "Latitude/Longitude"),
}

OUTPUT_COLUMNS = [
    "source_report",
    "report_entry_index",
    "image_name",
    "image_id",
    "ambient_parse_status",
    "ambient_temperature_c",
    "reflected_temperature_c",
    "distance_m",
    "emissivity",
    "humidity_percent",
    "humidity_use_status",
    "report_capture_datetime",
    "created_time",
    "modified_time",
    "gps_latitude_report",
    "gps_longitude_report",
    "camera_model_report",
    "serial_number_report",
    "focal_length_report",
    "aperture_report",
    "image_width_report",
    "image_height_report",
    "is_part_b_pilot",
    "part_b_selection_rank",
    "metadata_match_status",
    "pair_id",
    "location",
    "dataset_folder",
    "capture_date",
    "t_path",
    "v_path",
    "metadata_capture_datetime",
    "metadata_gps_latitude",
    "metadata_gps_longitude",
    "raw_parameter_text",
]

PILOT_COLUMNS = [
    "part_b_selection_rank",
    "image_id",
    "image_name",
    "ambient_parse_status",
    "ambient_temperature_c",
    "reflected_temperature_c",
    "distance_m",
    "emissivity",
    "humidity_percent",
    "humidity_use_status",
    "report_capture_datetime",
    "t_path",
    "source_report",
]


@dataclass
class ReportEntry:
    source_report: Path
    report_entry_index: int
    image_name: str
    lines: list[str]


def relative_posix(path: Path | str) -> str:
    work = Path(path)
    try:
        return work.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return work.as_posix()


def normalize_label(text: str) -> str:
    return text.strip().strip(":：").casefold()


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    match = NUMBER_RE.search(text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    number = parse_float(value)
    if number is None or math.isnan(number):
        return None
    return int(number)


def parse_gps(value: Any) -> tuple[float | None, float | None]:
    if value is None:
        return None, None
    numbers = [float(item.replace(",", ".")) for item in NUMBER_RE.findall(str(value))]
    if len(numbers) < 2:
        return None, None
    return numbers[0], numbers[1]


def as_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    if pd.isna(value):
        return ""
    return value


def image_id_from_name(image_name: str) -> str:
    stem = Path(image_name).stem
    if stem.upper().endswith("_T"):
        return stem[:-2]
    return stem


def extract_docx_paragraphs(path: Path) -> list[str]:
    if path.suffix.lower() != ".docx":
        raise ValueError(f"Only .docx TAT3 exports are currently supported: {path}")
    with zipfile.ZipFile(path) as zf:
        try:
            document_xml = zf.read("word/document.xml")
        except KeyError as exc:
            raise ValueError(f"Not a readable DOCX document: {path}") from exc
    root = ET.fromstring(document_xml)
    lines: list[str] = []
    for paragraph in root.iter(f"{W_NS}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{W_NS}t")).strip()
        if text:
            lines.append(text)
    return lines


def split_report_entries(report_path: Path) -> list[ReportEntry]:
    lines = extract_docx_paragraphs(report_path)
    starts: list[tuple[int, str]] = []
    previous_match_index: int | None = None
    previous_match_name: str | None = None
    for index, line in enumerate(lines):
        match = FILENAME_RE.search(line)
        if not match:
            continue
        image_name = match.group(1).upper()
        is_adjacent_duplicate = (
            previous_match_name == image_name
            and previous_match_index is not None
            and index == previous_match_index + 1
        )
        if not is_adjacent_duplicate:
            starts.append((index, image_name))
        previous_match_index = index
        previous_match_name = image_name

    entries: list[ReportEntry] = []
    for entry_index, (start, image_name) in enumerate(starts, start=1):
        stop = starts[entry_index][0] if entry_index < len(starts) else len(lines)
        entries.append(
            ReportEntry(
                source_report=report_path,
                report_entry_index=entry_index,
                image_name=image_name,
                lines=lines[start:stop],
            )
        )
    return entries


def value_after_label(lines: list[str], labels: tuple[str, ...]) -> str | None:
    normalized_labels = {normalize_label(label) for label in labels}
    for index, line in enumerate(lines):
        normalized_line = normalize_label(line)
        if normalized_line in normalized_labels:
            for next_line in lines[index + 1 :]:
                if next_line.strip():
                    return next_line.strip()
            return None
        for label in labels:
            if normalized_line.startswith(normalize_label(label)):
                trailing = line[len(label) :].strip().strip(":：").strip()
                if trailing:
                    return trailing
    return None


def first_datetime(lines: list[str]) -> str:
    for line in lines:
        match = DATETIME_RE.search(line)
        if match:
            return match.group(0).replace("/", "-")
    return ""


def parse_report_entry(entry: ReportEntry) -> dict[str, Any]:
    values = {field: value_after_label(entry.lines, labels) for field, labels in FIELD_LABELS.items()}
    gps_latitude, gps_longitude = parse_gps(values.get("gps"))
    ambient_temperature = parse_float(values.get("ambient_temperature_c"))
    humidity = parse_float(values.get("humidity_percent"))
    image_name = entry.image_name.upper()

    return {
        "source_report": relative_posix(entry.source_report),
        "report_entry_index": entry.report_entry_index,
        "image_name": image_name,
        "image_id": image_id_from_name(image_name),
        "ambient_parse_status": "ok" if ambient_temperature is not None else "missing",
        "ambient_temperature_c": ambient_temperature,
        "reflected_temperature_c": parse_float(values.get("reflected_temperature_c")),
        "distance_m": parse_float(values.get("distance_m")),
        "emissivity": parse_float(values.get("emissivity")),
        "humidity_percent": humidity,
        "humidity_use_status": "not_used_unreliable_tat3_export",
        "report_capture_datetime": first_datetime(entry.lines),
        "created_time": as_cell(values.get("created_time")),
        "modified_time": as_cell(values.get("modified_time")),
        "gps_latitude_report": gps_latitude,
        "gps_longitude_report": gps_longitude,
        "camera_model_report": as_cell(values.get("camera_model")),
        "serial_number_report": as_cell(values.get("serial_number")),
        "focal_length_report": as_cell(values.get("focal_length")),
        "aperture_report": as_cell(values.get("aperture")),
        "image_width_report": parse_int(values.get("image_width")),
        "image_height_report": parse_int(values.get("image_height")),
        "raw_parameter_text": "\n".join(entry.lines[:34]),
    }


def load_metadata() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    pilot_by_id: dict[str, dict[str, Any]] = {}
    if PILOT_PAIRS_XLSX.exists():
        pilot_df = pd.read_excel(PILOT_PAIRS_XLSX)
        for row in pilot_df.to_dict("records"):
            image_id = str(row.get("image_id", "")).upper()
            if image_id:
                pilot_by_id[image_id] = row

    vt_by_name: dict[str, dict[str, Any]] = {}
    if VT_PAIRS_XLSX.exists():
        vt_df = pd.read_excel(VT_PAIRS_XLSX)
        for row in vt_df.to_dict("records"):
            t_path = str(row.get("t_path", ""))
            image_name = Path(t_path).name.upper()
            if image_name:
                vt_by_name[image_name] = row

    dji_by_name: dict[str, dict[str, Any]] = {}
    if DJI_METADATA_XLSX.exists():
        dji_df = pd.read_excel(DJI_METADATA_XLSX)
        if "image_type" in dji_df.columns:
            dji_df = dji_df[dji_df["image_type"].astype(str).str.casefold() == "thermal"]
        for row in dji_df.to_dict("records"):
            image_name = str(row.get("image_name", "")).upper()
            if image_name:
                dji_by_name[image_name] = row
    return pilot_by_id, vt_by_name, dji_by_name


def merge_metadata(
    parsed_rows: list[dict[str, Any]],
    pilot_by_id: dict[str, dict[str, Any]],
    vt_by_name: dict[str, dict[str, Any]],
    dji_by_name: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in parsed_rows:
        image_id = str(row["image_id"]).upper()
        image_name = str(row["image_name"]).upper()
        pilot = pilot_by_id.get(image_id)
        vt = vt_by_name.get(image_name)
        dji = dji_by_name.get(image_name)

        row["is_part_b_pilot"] = bool(pilot)
        row["part_b_selection_rank"] = as_cell(pilot.get("selection_rank") if pilot else "")
        row["metadata_match_status"] = (
            "part_b_pilot_pair"
            if pilot
            else "vt_pair"
            if vt
            else "dji_metadata"
            if dji
            else "unmatched"
        )
        row["pair_id"] = as_cell((pilot or vt or dji or {}).get("pair_id", ""))
        row["location"] = as_cell((vt or {}).get("location", ""))
        row["dataset_folder"] = as_cell((vt or {}).get("dataset_folder", ""))
        row["capture_date"] = as_cell((vt or {}).get("capture_date", ""))
        row["t_path"] = as_cell((pilot or vt or dji or {}).get("t_path", (dji or {}).get("image_path", "")))
        row["v_path"] = as_cell((pilot or vt or {}).get("v_path", ""))
        row["metadata_capture_datetime"] = as_cell((dji or {}).get("capture_datetime", ""))
        row["metadata_gps_latitude"] = as_cell((dji or {}).get("gps_latitude", ""))
        row["metadata_gps_longitude"] = as_cell((dji or {}).get("gps_longitude", ""))
        rows.append(row)
    return rows


def collect_reports(args: argparse.Namespace) -> list[Path]:
    if args.report:
        reports = [Path(item).expanduser() for item in args.report]
    else:
        report_dir = Path(args.input_dir).expanduser()
        reports = sorted(report_dir.glob("*.docx"))
    missing = [path for path in reports if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing report file(s): " + ", ".join(str(path) for path in missing))
    if not reports:
        raise FileNotFoundError(f"No .docx reports found under {Path(args.input_dir)}")
    return reports


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    for column in columns:
        if column not in df.columns:
            df[column] = ""
    df = df[columns]
    df.to_csv(path, index=False, encoding="utf-8-sig")


def format_number(value: Any, digits: int = 1) -> str:
    number = parse_float(value)
    if number is None:
        return "NA"
    return f"{number:.{digits}f}"


def write_summary(path: Path, rows: list[dict[str, Any]], pilot_rows: list[dict[str, Any]], reports: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ambient_values = [row["ambient_temperature_c"] for row in rows if row.get("ambient_temperature_c") is not None]
    unique_images = {row["image_name"] for row in rows}
    duplicate_images = len(rows) - len(unique_images)
    ok_count = sum(1 for row in rows if row.get("ambient_parse_status") == "ok")
    missing_count = len(rows) - ok_count
    expected_pilots = len(pd.read_excel(PILOT_PAIRS_XLSX)) if PILOT_PAIRS_XLSX.exists() else 0
    covered_pilots = len({row["image_id"] for row in pilot_rows})

    pilot_lines = [
        "| selection_rank | image_id | ambient_temperature_c | reflected_temperature_c | humidity_percent | status |",
        "| --- | --- | ---: | ---: | ---: | --- |",
    ]
    for row in sorted(pilot_rows, key=lambda item: (as_cell(item.get("part_b_selection_rank")) or 9999, item["image_id"])):
        pilot_lines.append(
            "| {rank} | {image_id} | {ambient} | {reflected} | {humidity} | {status} |".format(
                rank=as_cell(row.get("part_b_selection_rank")),
                image_id=row["image_id"],
                ambient=format_number(row.get("ambient_temperature_c")),
                reflected=format_number(row.get("reflected_temperature_c")),
                humidity=format_number(row.get("humidity_percent"), digits=0),
                status=row.get("ambient_parse_status", ""),
            )
        )

    report_list = "\n".join(f"- `{relative_posix(report)}`" for report in reports)
    content = f"""# Part D TAT3 Parameter Ingest

This summary was generated by `scripts/part_d/03_parse_tat3_ambient_temperature_reports.py`.

## Scope

- Raw TAT3 exports read: {len(reports)}
{report_list}
- Parsed report entries: {len(rows)}
- Unique thermal images: {len(unique_images)}
- Duplicate image entries across reports: {duplicate_images}
- Ambient temperature parse status: ok={ok_count}, missing={missing_count}
- Part B pilot coverage: {covered_pilots}/{expected_pilots}

## Ambient Temperature Range

- Minimum ambient temperature: {format_number(min(ambient_values) if ambient_values else None)} deg C
- Maximum ambient temperature: {format_number(max(ambient_values) if ambient_values else None)} deg C

## Part B Pilot Parameters

{chr(10).join(pilot_lines)}

## Notes

- The required SDK-driving fields are `ambient_temperature_c`, `reflected_temperature_c`, `distance_m`, and `emissivity`.
- `humidity_percent` is retained for SDK reproducibility and marked `not_used_unreliable_tat3_export`; it should not be interpreted as reliable field humidity.
- This ingest does not call the DJI Thermal SDK, extract temperature matrices, or calculate delta T.
- Raw TAT3 reports should remain under ignored local storage such as `data/local_external/tat3_reports/raw/`.
"""
    path.write_text(content, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse TAT3 DOCX report exports for per-image ambient temperature."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help="Directory containing local TAT3 .docx exports.",
    )
    parser.add_argument(
        "--report",
        action="append",
        type=Path,
        help="Specific TAT3 .docx report to parse. Repeat for multiple reports.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reports = collect_reports(args)
    parsed_rows: list[dict[str, Any]] = []
    for report in reports:
        entries = split_report_entries(report)
        parsed_rows.extend(parse_report_entry(entry) for entry in entries)

    pilot_by_id, vt_by_name, dji_by_name = load_metadata()
    rows = merge_metadata(parsed_rows, pilot_by_id, vt_by_name, dji_by_name)
    rows = sorted(rows, key=lambda row: (row["source_report"], row["report_entry_index"], row["image_name"]))
    pilot_rows = [row for row in rows if row.get("is_part_b_pilot")]

    write_csv(ALL_ROWS_CSV, rows, OUTPUT_COLUMNS)
    write_rows(ALL_ROWS_XLSX, rows, OUTPUT_COLUMNS)
    write_csv(PILOT_ROWS_CSV, pilot_rows, PILOT_COLUMNS)
    write_rows(PILOT_ROWS_XLSX, pilot_rows, PILOT_COLUMNS)
    write_summary(SUMMARY_MD, rows, pilot_rows, reports)

    ok_count = sum(1 for row in rows if row.get("ambient_parse_status") == "ok")
    print(f"Parsed {len(rows)} TAT3 report entries from {len(reports)} report(s).")
    print(f"Ambient temperature parsed for {ok_count}/{len(rows)} entries.")
    print(f"Part B pilot rows found: {len({row['image_id'] for row in pilot_rows})}.")
    print(f"Wrote {relative_posix(ALL_ROWS_CSV)}")
    print(f"Wrote {relative_posix(PILOT_ROWS_CSV)}")
    print(f"Wrote {relative_posix(SUMMARY_MD)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
