"""Exporting functionality for NFView."""
from __future__ import annotations
import csv
import html
import shutil
from pathlib import Path


from nfview.models import ImageScore

def export_report(results, cutoff, destination, mode, report_base=None):
    """Write reports beside the copied folder without modifying originals."""
    destination = Path(destination)
    base = Path(report_base) if report_base else destination.parent / (destination.name + "-culling-report")
    rows = [{"filename": str(r.path), "score": r.score,
             "selected": not r.error and r.score >= cutoff,
             "stackable": (not r.error if mode == "stacking" else ""),
             "error": r.error} for r in results]
    with base.with_suffix(".csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=["filename", "score", "selected", "stackable", "error"])
        writer.writeheader()
        writer.writerows(rows)
    headings = "".join("<th>" + k + "</th>" for k in rows[0]) if rows else ""
    body = "".join("<tr>" + "".join("<td>" + html.escape(str(v)) + "</td>" for v in row.values()) + "</tr>" for row in rows)
    base.with_suffix(".html").write_text("<!doctype html><meta charset=utf-8><title>Culling report</title><style>body{background:#11151b;color:#eee;font:15px system-ui;padding:24px}td,th{text-align:left;padding:10px;border-bottom:1px solid #39414e}table{border-collapse:collapse}</style><h1>Culling report</h1><p>Selected means at or above the keep-percent cutoff. Stackable is blank when alignment was not evaluated.</p><table>" + headings + body + "</table>", encoding="utf-8")
    return base.with_suffix(".csv"), base.with_suffix(".html")

def copy_ranked_images(results: list[ImageScore], cutoff: float, destination: Path) -> tuple[int, int]:
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    skipped = 0
    for result in results:
        if result.error or result.score < cutoff:
            continue
        target = destination / result.path.name
        if target.exists():
            skipped += 1
            continue
        shutil.copy2(result.path, target)
        copied += 1
    return copied, skipped
