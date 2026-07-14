#!/usr/bin/env python3
"""Create a stable inventory of visible/thermal image pairs."""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from table_io import write_rows


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DATA_ROOT = PROJECT_ROOT / "data" / "raw" / "HKUST"
OUTPUT_XLSX = PROJECT_ROOT / "data" / "metadata" / "vt_pairs.xlsx"

# Set this to one generated pair_id after selecting a single pilot record.
PILOT_PAIR_ID: str | None = None
TIMESTAMP_WARNING_SECONDS = 2

COLUMNS = [
    "pair_id",
    "dataset_folder",
    "location",
    "capture_date",
    "session_folder",
    "base_name",
    "sample_number",
    "v_path",
    "t_path",
    "status",
    "match_method",
    "timestamp_difference_seconds",
    "pilot",
    "notes",
]
VT_SUFFIX_RE = re.compile(r"^(?P<base>.+)_(?P<kind>[VT])$", re.IGNORECASE)
SAMPLE_NUMBER_RE = re.compile(r"_(\d+)$")
IMAGE_NAME_RE = re.compile(r"^DJI_(\d{14})_(\d+)$", re.IGNORECASE)
SESSION_DATE_RE = re.compile(r"^DJI_(\d{8})", re.IGNORECASE)
DATASET_DATE_RE = re.compile(r"^(\d{8})")


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


def extract_sample_number(base_name: str) -> str:
    match = SAMPLE_NUMBER_RE.search(base_name)
    return match.group(1) if match else ""


def extract_timestamp(base_name: str) -> datetime | None:
    match = IMAGE_NAME_RE.match(base_name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def status_for_candidates(v_paths: list[Path], t_paths: list[Path]) -> str:
    if len(v_paths) > 1 and len(t_paths) > 1:
        return "duplicate_V_and_T"
    if len(v_paths) > 1:
        return "duplicate_V"
    if len(t_paths) > 1:
        return "duplicate_T"
    if not v_paths:
        return "missing_V"
    if not t_paths:
        return "missing_T"
    return "paired"


def candidate_note(kind: str, paths: list[Path]) -> str:
    if len(paths) < 2:
        return ""
    joined = ", ".join(relative_posix(path) for path in paths)
    return f"multiple {kind} candidates: {joined}"


def make_record(
    parent_relative_to_raw: Path,
    base_name: str,
    sample_number: str,
    v_paths: list[Path],
    t_paths: list[Path],
    match_method: str,
) -> dict[str, str]:
    v_paths = sorted(v_paths, key=lambda path: path.as_posix())
    t_paths = sorted(t_paths, key=lambda path: path.as_posix())
    status = status_for_candidates(v_paths, t_paths)
    dataset_folder = parent_relative_to_raw.parts[0]
    parent = RAW_DATA_ROOT / parent_relative_to_raw
    session_folder = find_session(parent)
    notes = [
        note
        for note in (
            candidate_note("V", v_paths),
            candidate_note("T", t_paths),
            "" if session_folder else "unable to identify DJI_ session folder",
        )
        if note
    ]

    timestamp_difference = ""
    if status == "paired":
        v_base = VT_SUFFIX_RE.match(v_paths[0].stem).group("base")
        t_base = VT_SUFFIX_RE.match(t_paths[0].stem).group("base")
        v_timestamp = extract_timestamp(v_base)
        t_timestamp = extract_timestamp(t_base)
        if v_timestamp and t_timestamp:
            difference = int(abs((v_timestamp - t_timestamp).total_seconds()))
            timestamp_difference = str(difference)
            if difference > TIMESTAMP_WARNING_SECONDS:
                notes.append(
                    f"timestamp difference {difference} seconds exceeds "
                    f"{TIMESTAMP_WARNING_SECONDS}-second review threshold"
                )
        elif match_method == "session_sample_number":
            notes.append("unable to calculate timestamp difference for fallback match")

        if match_method == "session_sample_number" and v_base != t_base:
            notes.append(f"fallback base names: V={v_base}; T={t_base}")

    if status.startswith("duplicate_"):
        match_method = "ambiguous"

    if match_method == "exact_base_name":
        identifier = base_name
    elif sample_number:
        identifier = f"sample_{sample_number}"
    else:
        identifier = base_name
    record_pair_id = f"{parent_relative_to_raw.as_posix()}::{identifier}"

    return {
        "pair_id": record_pair_id,
        "dataset_folder": dataset_folder,
        "location": infer_location(dataset_folder),
        "capture_date": infer_capture_date(session_folder, dataset_folder),
        "session_folder": session_folder,
        "base_name": base_name,
        "sample_number": sample_number,
        "v_path": relative_posix(v_paths[0]) if len(v_paths) == 1 else "",
        "t_path": relative_posix(t_paths[0]) if len(t_paths) == 1 else "",
        "status": status,
        "match_method": match_method,
        "timestamp_difference_seconds": timestamp_difference,
        "pilot": "yes" if record_pair_id == PILOT_PAIR_ID else "no",
        "notes": "; ".join(notes),
    }


def build_records() -> tuple[list[dict[str, str]], int, int]:
    exact_groups: dict[tuple[str, str], dict[str, list[Path]]] = defaultdict(
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
        parent_relative_to_raw = path.parent.relative_to(RAW_DATA_ROOT).as_posix()
        exact_groups[(parent_relative_to_raw, base_name)][kind].append(path)

    records: list[dict[str, str]] = []
    leftovers: list[tuple[Path, str, str]] = []

    # Stage 1: consume only unambiguous exact base-name pairs.
    for (parent_string, base_name), sides in exact_groups.items():
        v_paths = sides["V"]
        t_paths = sides["T"]
        if len(v_paths) == 1 and len(t_paths) == 1:
            records.append(
                make_record(
                    Path(parent_string),
                    base_name,
                    extract_sample_number(base_name),
                    v_paths,
                    t_paths,
                    "exact_base_name",
                )
            )
        else:
            leftovers.extend((path, base_name, "V") for path in v_paths)
            leftovers.extend((path, base_name, "T") for path in t_paths)

    # Stage 2: pair remaining files only within one parent/session and sample number.
    fallback_groups: dict[tuple[str, str], dict[str, list[tuple[Path, str]]]] = (
        defaultdict(lambda: {"V": [], "T": []})
    )
    no_sample_groups: dict[tuple[str, str], dict[str, list[Path]]] = defaultdict(
        lambda: {"V": [], "T": []}
    )
    for path, base_name, kind in leftovers:
        parent_string = path.parent.relative_to(RAW_DATA_ROOT).as_posix()
        sample_number = extract_sample_number(base_name)
        if sample_number:
            fallback_groups[(parent_string, sample_number)][kind].append((path, base_name))
        else:
            no_sample_groups[(parent_string, base_name)][kind].append(path)

    for (parent_string, sample_number), sides in fallback_groups.items():
        v_items = sides["V"]
        t_items = sides["T"]
        v_paths = [item[0] for item in v_items]
        t_paths = [item[0] for item in t_items]
        all_bases = sorted({item[1] for item in v_items + t_items})
        display_base = all_bases[0] if len(all_bases) == 1 else f"sample_{sample_number}"
        method = (
            "session_sample_number"
            if len(v_paths) == 1 and len(t_paths) == 1
            else "unmatched"
        )
        records.append(
            make_record(
                Path(parent_string),
                display_base,
                sample_number,
                v_paths,
                t_paths,
                method,
            )
        )

    for (parent_string, base_name), sides in no_sample_groups.items():
        records.append(
            make_record(
                Path(parent_string),
                base_name,
                "",
                sides["V"],
                sides["T"],
                "unmatched",
            )
        )

    records.sort(
        key=lambda row: (
            row["dataset_folder"].lower(),
            row["session_folder"].lower(),
            row["sample_number"],
            row["base_name"].lower(),
            row["pair_id"].lower(),
        )
    )
    return records, jpg_count, ignored_jpg_count


def print_summary(records: list[dict[str, str]], jpg_count: int, ignored: int) -> None:
    counts = defaultdict(int)
    methods = defaultdict(int)
    for record in records:
        counts[record["status"]] += 1
        methods[record["match_method"]] += 1

    print(f"Raw data root: {RAW_DATA_ROOT}")
    print(f"Output XLSX: {OUTPUT_XLSX}")
    print(f"JPG/JPEG files inspected: {jpg_count}")
    print(f"Non-V/T JPG/JPEG files ignored: {ignored}")
    print(f"Total pair records: {len(records)}")
    print(f"Paired: {counts['paired']}")
    print(f"Missing V: {counts['missing_V']}")
    print(f"Missing T: {counts['missing_T']}")
    print(f"Ambiguous/duplicate: {methods['ambiguous']}")
    print(f"Exact base-name matches: {methods['exact_base_name']}")
    print(f"Session sample-number matches: {methods['session_sample_number']}")
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

    write_rows(OUTPUT_XLSX, records, COLUMNS)

    print_summary(records, jpg_count, ignored_jpg_count)
    return 0


if __name__ == "__main__":
    sys.exit(main())
