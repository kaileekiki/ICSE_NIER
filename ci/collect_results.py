#!/usr/bin/env python3
"""Collect uploaded replay summaries into compact CSV and Markdown tables."""
from __future__ import annotations
import csv, json, pathlib, sys

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "results")
rows = []
for path in sorted(root.rglob("summary.json")):
    x = json.loads(path.read_text())
    full = x.get("conditions", {}).get("full", {})
    linked = full.get("linked_test_execution", {})
    row = {
        "instance_id": x.get("instance_id"),
        "expected_resolved": x.get("expected_published_resolved"),
        "full_resolved": full.get("resolved"),
        "full_reproduced": x.get("full_verdict_reproduced"),
        "linked_test_exact_in_status": linked.get("exact_in_status"),
        "linked_test_in_raw_log": linked.get("substring_in_post_patch_log"),
        "targeted_resolved": x.get("conditions", {}).get("targeted", {}).get("resolved"),
        "targeted_changed": x.get("conditions", {}).get("targeted", {}).get("verdict_changed_from_full"),
        "sham_resolved": x.get("conditions", {}).get("sham", {}).get("resolved"),
        "sham_changed": x.get("conditions", {}).get("sham", {}).get("verdict_changed_from_full"),
        "image_id": x.get("image_evidence", {}).get("image_id"),
        "errors": len(x.get("errors", [])),
        "summary_path": str(path),
    }
    rows.append(row)
if not rows:
    raise SystemExit("no summary.json files found")
out = root / "combined_results.csv"
with out.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
md = ["| " + " | ".join(rows[0]) + " |", "|" + "|".join(["---"] * len(rows[0])) + "|"]
for row in rows:
    md.append("| " + " | ".join(str(row[k]) for k in row) + " |")
(root / "combined_results.md").write_text("\n".join(md) + "\n")
print(json.dumps({"summaries": len(rows), "csv": str(out)}))
