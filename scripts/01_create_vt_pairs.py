#!/usr/bin/env python3
"""Create a stable inventory of visible/thermal image pairs."""

from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_ROOT = PROJECT_ROOT / "data" / "raw" / "HKUST"
OUTPUT_CSV = PROJECT_ROOT / "data" / "metadata" / "vt_pairs.csv"

COLUMNS = [
    "pair_id",
    "dataset_folder",
    "location",
    "capture_date",
    "session_folder",
    "base_name",
    "v_path",
    "t_path",
    "status",
    "pilot",
    "notes",
]
VT_SUFFIX_RE = re.compile(r"^(?P<base>.+)_(?P<kind>[VT])$", re.IGNORECASE)
SESSION_DATE_RE = re.compile(r"^DJI_(\d{8})", re.IGNORECASE)
DATASET_DATE_RE = re.compile(r"^(\d{8})")
PILOT_RE = re.compile(r"_0016$")


def format_date(value: str) -> str:
    """Return YYYY-MM-DD for a valid YYYYMMDD value, otherwise empty."""
    try:
        return datetime.strptime(value, "%Y%m%d").date().isoformat()
    except ValueError:
        return ""


def infer_location(dataset_folder: str) -> str:
    lowered = dataset_folder.lower()
    if "gardenhill" in lowered:
        return "GardenHill"
    if "hkust" in lowered:
        return "HKUST"
    return "Unknown"


def find_session(parent: Path) -> str:
    for directory in (parent, *parent.parents):
        if directory == RAW_DATA_ROOT.parent:
            break
        if directory.name.lower().startswith("dji_"):
            return directory.name
    return ""


def infer_capture_date(session_folder: str, dataset_folder: str) -> str:
    if session_folder:
        match = SESSION_DATE_RE.match(session_folder)
        if match:
            session_date = format_date(match.group(1))
            if session_date:
                return session_date

    match = DATASET_DATE_RE.match(dataset_folder)
    return format_date(match.group(1)) if match else ""


def relative_posix(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def pair_id(parent_relative_to_raw: Path, base_name: str) -> str:
    return f"{parent_relative_to_raw.as_posix()}::{base_name}"


def duplicate_note(kind: str, paths: list[Path]) -> str:
    if len(paths) < 2:
        return ""
    joined = ", ".join(relative_posix(path) for path in paths)
    return f"duplicate {kind}: {joined}"


def build_records() -> tuple[list[dict[str, str]], int, int]:
    groups: dict[tuple[str, str], dict[str, list[Path]]] = defaultdict(
        lambda: {"V": [], "T": []}
    )
    jpg_count = 0
    ignored_jpg_count = 0

    for path in sorted(RAW_DATA_ROOT.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg"}:
            continue
        jpg_count += 1
        match = VT_SUFFIX_RE.match(path.stem)
        if not match:
            ignored_jpg_count += 1
            continue
        base_name = match.group("base")
        kind = match.group("kind").upper()
        parent_relative_to_raw = path.parent.relative_to(RAW_DATA_ROOT)
        groups[(parent_relative_to_raw.as_posix(), base_name)][kind].append(path)

    records: list[dict[str, str]] = []
    for (parent_string, base_name), sides in groups.items():
        parent_relative_to_raw = Path(parent_string)
        v_paths = sorted(sides["V"], key=lambda path: path.as_posix())
        t_paths = sorted(sides["T"], key=lambda path: path.as_posix())
        dataset_folder = parent_relative_to_raw.parts[0]
        parent = RAW_DATA_ROOT / parent_relative_to_raw
        session_folder = find_session(parent)

        if len(v_paths) > 1 and len(t_paths) > 1:
            status = "duplicate_V_and_T"
        elif len(v_paths) > 1:
            status = "duplicate_V"
        elif len(t_paths) > 1:
            status = "duplicate_T"
        elif not v_paths:
            status = "missing_V"
        elif not t_paths:
            status = "missing_T"
        else:
            status = "paired"

        notes = [
            note
            for note in (
                duplicate_note("V", v_paths),
                duplicate_note("T", t_paths),
                "" if session_folder else "unable to identify DJI_ session folder",
            )
            if note
        ]
        records.append(
            {
                "pair_id": pair_id(parent_relative_to_raw, base_name),
                "dataset_folder": dataset_folder,
                "location": infer_location(dataset_folder),
                "capture_date": infer_capture_date(session_folder, dataset_folder),
                "session_folder": session_folder,
                "base_name": base_name,
                "v_path": relative_posix(v_paths[0]) if v_paths else "",
                "t_path": relative_posix(t_paths[0]) if t_paths else "",
                "status": status,
                "pilot": "yes" if PILOT_RE.search(base_name) else "no",
                "notes": "; ".join(notes),
            }
        )

    records.sort(
        key=lambda row: (
            row["dataset_folder"].lower(),
            row["session_folder"].lower(),
            row["base_name"].lower(),
            row["pair_id"].lower(),
        )
    )
    return records, jpg_count, ignored_jpg_count


def print_summary(records: list[dict[str, str]], jpg_count: int, ignored: int) -> None:
    counts = defaultdict(int)
    for record in records:
        counts[record["status"]] += 1

    print(f"Raw data root: {RAW_DATA_ROOT}")
    print(f"Output CSV: {OUTPUT_CSV}")
    print(f"JPG/JPEG files inspected: {jpg_count}")
    print(f"Non-V/T JPG/JPEG files ignored: {ignored}")
    print(f"Total pair records: {len(records)}")
    print(f"Paired: {counts['paired']}")
    print(f"Missing V: {counts['missing_V']}")
    print(f"Missing T: {counts['missing_T']}")
    print(f"Duplicate V: {counts['duplicate_V'] + counts['duplicate_V_and_T']}")
    print(f"Duplicate T: {counts['duplicate_T'] + counts['duplicate_V_and_T']}")
    print(f"Pilot records: {sum(row['pilot'] == 'yes' for row in records)}")


def main() -> int:
    if not RAW_DATA_ROOT.is_dir():
        print(f"Error: raw data directory does not exist: {RAW_DATA_ROOT}", file=sys.stderr)
        return 1

    records, jpg_count, ignored_jpg_count = build_records()
    if not records:
        print(
            f"Error: no V/T JPG or JPEG files found below {RAW_DATA_ROOT}",
            file=sys.stderr,
        )
        return 1

    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_CSV.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)

    print_summary(records, jpg_count, ignored_jpg_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
