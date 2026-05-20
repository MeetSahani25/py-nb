"""
cleanup.py
Deletes daily report folders older than 180 days.
Weekly reports are never deleted.
Run automatically every Friday via GitHub Actions.
"""

import os
import shutil
import json
from datetime import date, timedelta

OUTPUT_DIR  = "reports"
WEEKLY_DIR  = os.path.join(OUTPUT_DIR, "weekly")
MAX_AGE_DAYS = 180

def cleanup_old_daily_reports():
    cutoff = date.today() - timedelta(days=MAX_AGE_DAYS)
    print(f"\n🧹 Cleanup — removing daily reports older than {cutoff} ({MAX_AGE_DAYS} days)\n")

    removed = []
    kept    = []

    if not os.path.exists(OUTPUT_DIR):
        print("  No reports directory found.")
        return

    for entry in sorted(os.listdir(OUTPUT_DIR)):
        entry_path = os.path.join(OUTPUT_DIR, entry)

        # Skip weekly folder and non-directories
        if entry == "weekly" or entry == "index.json":
            continue
        if not os.path.isdir(entry_path):
            continue

        # Try to parse folder name as a date (YYYY-MM-DD)
        try:
            folder_date = date.fromisoformat(entry)
        except ValueError:
            continue

        if folder_date < cutoff:
            shutil.rmtree(entry_path)
            removed.append(entry)
            print(f"  🗑  Deleted: {entry}")
        else:
            kept.append(entry)

    # Update index.json to remove deleted entries
    index_path = os.path.join(OUTPUT_DIR, "index.json")
    if os.path.exists(index_path):
        with open(index_path) as f:
            index = json.load(f)
        before = len(index.get("reports", []))
        index["reports"] = [
            r for r in index.get("reports", [])
            if r["date"] not in removed
        ]
        after = len(index["reports"])
        with open(index_path, "w") as f:
            json.dump(index, f, indent=2)
        print(f"\n  📋 Index updated: {before} → {after} entries")

    print(f"\n✅ Cleanup done — removed {len(removed)}, kept {len(kept)} daily folders")
    if removed:
        print(f"   Removed: {removed}")

if __name__ == "__main__":
    cleanup_old_daily_reports()
