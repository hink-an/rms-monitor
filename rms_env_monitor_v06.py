"""RMS monitor v0.6: OFFLINE snapshot comparison test.

This program does not access the network, does not change prior snapshots,
and never modifies RMS production data. Use the same v0.5 snapshot as both
--previous and --current to verify 0 new / 5 unchanged before live testing.
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.6"
FORBIDDEN_OUTPUT_NAMES = {
    "rms-monitor-results.json",
    "rms_運用データ.json",
    "計測器管理_運用データ.json",
}


def load_snapshot(filename):
    path = Path(filename)
    if not path.is_file():
        raise ValueError(f"Snapshot unavailable: {path}. Comparison NOT performed.")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"Snapshot unreadable: {path}. Comparison NOT performed: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError(f"Invalid schema_version in {path}. Comparison NOT performed.")
    records = data.get("records")
    if not isinstance(records, list):
        raise ValueError(f"Missing records array in {path}. Comparison NOT performed.")
    ids = []
    for number, record in enumerate(records, 1):
        if not isinstance(record, dict) or not isinstance(record.get("id"), str) or not record["id"].strip():
            raise ValueError(f"Invalid record #{number} in {path}. Comparison NOT performed.")
        ids.append(record["id"])
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate record IDs in {path}. Comparison NOT performed.")
    return data


def compare(current, previous):
    old_ids = {record["id"] for record in previous["records"]}
    new_ids = {record["id"] for record in current["records"]}
    return {
        "mode": "COMPARED",
        "new_candidate_ids": sorted(new_ids - old_ids),
        "unchanged_ids": sorted(new_ids & old_ids),
        "removed_from_current_list_ids": sorted(old_ids - new_ids),
        "note": "ID-based comparison only. Not evidence of a law change or repeal.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", required=True, help="Existing baseline test JSON")
    parser.add_argument("--current", required=True, help="Current test JSON (same file allowed for initial test)")
    parser.add_argument("--output", default="rms-env-monitor-v06-test.json", help="New TEST result JSON")
    args = parser.parse_args()
    output = Path(args.output)
    source_paths = [Path(args.previous), Path(args.current)]
    if output.name.casefold() in {name.casefold() for name in FORBIDDEN_OUTPUT_NAMES}:
        parser.error("Refusing to overwrite a protected RMS data file")
    if output.resolve() in {path.resolve() for path in source_paths}:
        parser.error("Output must NOT overwrite either input snapshot")
    if output.exists():
        parser.error("Output already exists; choose a different name to preserve the previous test")

    try:
        prior = load_snapshot(args.previous)
        current = load_snapshot(args.current)
        diff = compare(current, prior)
    except ValueError as exc:
        parser.error(str(exc))

    result = {
        "schema_version": 1,
        "monitor_version": VERSION,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "comparison_kind": "OFFLINE_SNAPSHOT_TEST",
        "source_list": current.get("source_list"),
        "coverage": current.get("coverage"),
        "legal_change_verified": False,
        "records": current["records"],
        "comparison": diff,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Comparison mode: {diff['mode']}")
    print(f"New candidates: {len(diff['new_candidate_ids'])}")
    print(f"Unchanged: {len(diff['unchanged_ids'])}")
    print(f"Absent from current snapshot: {len(diff['removed_from_current_list_ids'])}")
    print(f"Saved TEST result: {output}")
    print("NOT VERIFIED: legal changes, article publication dates, applicability.")
    print("Production RMS data not modified.")


if __name__ == "__main__":
    main()
