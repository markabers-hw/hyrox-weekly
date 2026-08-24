#!/usr/bin/env python3
"""
Non-destructive YouTube-only backfill for a single week.

Unlike batch_yolo.py, this does NOT clear existing content — it only runs
YouTube discovery, selects the top N videos, and generates their blurbs.
Existing podcast/article selections for the week are left untouched.

Created to recover Jun 15-21 2026 videos after the YouTube Search API daily
quota was exhausted (each of ~257 channel searches costs 100 units vs a
10k/day quota). Run right after the midnight-Pacific quota reset.

Usage:
    python backfill_youtube_week.py --week 2026-06-15
"""
import argparse
from datetime import datetime, timezone, timedelta

import batch_yolo as by


def curate_youtube_only(week_start, week_end):
    """Select top-N YouTube items for the week by the same rules as auto_curate_yolo."""
    priority_sources = by.supabase_get('priority_sources', 'is_active=eq.true') or []
    priority_names = {p['source_name'].lower() for p in priority_sources}
    limit = by.YOLO_CONFIG['yolo_max_youtube']

    ws = week_start.strftime('%Y-%m-%d')
    end_date = (week_end + timedelta(days=1)).strftime('%Y-%m-%d')

    content = by.supabase_get('content_items',
        f'platform=eq.youtube&status=eq.discovered'
        f'&published_date=gte.{ws}&published_date=lt.{end_date}'
        f'&select=id,title,view_count,creators(name)'
        f'&order=view_count.desc.nullslast') or []

    def sort_key(item):
        creator = (item.get('creators', {}).get('name') or '').lower() if item.get('creators') else ''
        return (0 if creator in priority_names else 1, -(item.get('view_count') or 0))

    content.sort(key=sort_key)
    selected = content[:limit]
    for i, item in enumerate(selected):
        by.supabase_patch('content_items', f'id=eq.{item["id"]}', {
            'status': 'selected',
            'display_order': (i + 1) * 10,
            'selection_method': 'yolo',
            'updated_at': datetime.now(timezone.utc).isoformat(),
        })
    return len(selected)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--week', required=True, help='Monday date YYYY-MM-DD')
    args = parser.parse_args()

    week_start, week_end = by.resolve_week(args.week)
    ws = week_start.strftime('%Y-%m-%d')
    we = week_end.strftime('%Y-%m-%d')
    print(f"=== YouTube backfill for {ws} .. {we} @ {datetime.now(timezone.utc).isoformat()} ===")

    # 1. Discover (non-destructive; no clear_content_for_week)
    ok, output, found, saved = by.run_discovery_script('youtube_discovery.py', ws, we)
    print(f"[discovery] ok={ok} found={found} saved={saved}")
    if '429' in output or 'Quota exceeded' in output:
        print("[discovery] WARNING: hit YouTube quota (429) during run — coverage may be partial")

    # 2. Select top-N YouTube videos (leaves podcasts/articles alone)
    n = curate_youtube_only(week_start, week_end)
    print(f"[curate] selected {n} youtube videos")

    # 3. Blurbs for anything selected-but-unblurbed (only the new videos qualify)
    res = by.generate_blurbs(week_start, week_end)
    print(f"[blurbs] {res}")

    print(f"=== DONE: {n} videos selected for {ws} .. {we} ===")
    return 0 if n > 0 else 2


if __name__ == '__main__':
    raise SystemExit(main())
