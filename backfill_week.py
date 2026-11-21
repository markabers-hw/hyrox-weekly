#!/usr/bin/env python3
"""
Non-destructive backfill of missing platforms for a single week.

Unlike batch_yolo.py, this never clears content. For each platform that has
nothing selected yet it runs discovery (items already in the database are
skipped), selects the top N for that platform only, then writes blurbs for
any selected item that lacks one. Platforms that already have selections are
left untouched.

Generalises backfill_youtube_week.py, which only handled YouTube.

Usage:
    python backfill_week.py --week 2026-09-07                       # every platform with nothing selected
    python backfill_week.py --week 2026-08-24 --platforms youtube,podcast
    python backfill_week.py --week 2026-09-07 --dry-run             # show what would run
"""
import argparse
from datetime import datetime, timedelta, timezone

import batch_yolo as by

PLATFORMS = ('youtube', 'podcast', 'article', 'reddit')
SCRIPTS = {
    'youtube': 'youtube_discovery.py',
    'podcast': 'podcast_discovery.py',
    'article': 'article_discovery.py',
    'reddit': 'reddit_discovery.py',
}


def selected_counts(ws: str, end_date: str) -> dict[str, int]:
    """Count items currently selected for the week, per platform."""
    rows = by.supabase_get('content_items',
        f'status=eq.selected&published_date=gte.{ws}&published_date=lt.{end_date}&select=platform') or []
    counts = {p: 0 for p in PLATFORMS}
    for row in rows:
        if row['platform'] in counts:
            counts[row['platform']] += 1
    return counts


def select_top(platform: str, ws: str, end_date: str) -> int:
    """Select the top N discovered items for one platform, priority sources first (same rules as auto_curate_yolo)."""
    priority_sources = by.supabase_get('priority_sources', 'is_active=eq.true') or []
    priority_names = {p['source_name'].lower() for p in priority_sources}

    content = by.supabase_get('content_items',
        f'platform=eq.{platform}&status=eq.discovered'
        f'&published_date=gte.{ws}&published_date=lt.{end_date}'
        f'&select=id,view_count,comment_count,creators(name)'
        f'&order=view_count.desc.nullslast') or []

    if platform == 'reddit':
        # Same bar as auto_curate_yolo: only well-discussed or well-upvoted threads
        content = [c for c in content
                   if (c.get('comment_count') or 0) >= by.YOLO_CONFIG['yolo_reddit_min_comments']
                   or (c.get('view_count') or 0) >= by.YOLO_CONFIG['yolo_reddit_min_upvotes']]

    def sort_key(item: dict) -> tuple[int, int]:
        creator = ((item.get('creators') or {}).get('name') or '').lower()
        return (0 if creator in priority_names else 1, -(item.get('view_count') or 0))

    content.sort(key=sort_key)
    selected = content[:by.YOLO_CONFIG[f'yolo_max_{platform}']]
    for i, item in enumerate(selected):
        by.supabase_patch('content_items', f'id=eq.{item["id"]}', {
            'status': 'selected',
            'display_order': (i + 1) * 10,
            'selection_method': 'yolo',
            'updated_at': datetime.now(timezone.utc).isoformat(),
        })
    return len(selected)


def main() -> int:
    parser = argparse.ArgumentParser(description='Non-destructive backfill of missing platforms for one week')
    parser.add_argument('--week', required=True, help='Monday date YYYY-MM-DD')
    parser.add_argument('--platforms', help='Comma list of youtube,podcast,article (default: every platform with nothing selected)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would run without changing anything')
    args = parser.parse_args()

    week_start, week_end = by.resolve_week(args.week)
    ws = week_start.strftime('%Y-%m-%d')
    we = week_end.strftime('%Y-%m-%d')
    end_date = (week_end + timedelta(days=1)).strftime('%Y-%m-%d')

    by.load_yolo_config()
    counts = selected_counts(ws, end_date)
    requested = [p.strip() for p in args.platforms.split(',')] if args.platforms else list(PLATFORMS)
    unknown = [p for p in requested if p not in PLATFORMS]
    if unknown:
        print(f"Unknown platform(s): {', '.join(unknown)}. Choose from {', '.join(PLATFORMS)}.")
        return 1

    todo = [p for p in requested if counts[p] == 0]
    print(f"=== Backfill {ws} .. {we} @ {datetime.now(timezone.utc).isoformat()} ===")
    print(f"Currently selected: {counts}")
    for p in requested:
        if p not in todo:
            print(f"  {p}: already has {counts[p]} selected, leaving untouched")
    print(f"Will backfill: {', '.join(todo) or 'nothing'}")
    if args.dry_run or not todo:
        return 0

    for platform in todo:
        ok, output, found, saved = by.run_discovery_script(SCRIPTS[platform], ws, we)
        by.record_discovery_run(platform, week_start, week_end, found, saved, 'completed' if ok else 'failed')
        print(f"[{platform}] discovery ok={ok} found={found} saved={saved}")
        if platform == 'youtube' and ('429' in output or 'Quota exceeded' in output):
            print("[youtube] WARNING: hit the YouTube quota during the run, so coverage may be partial")
        print(f"[{platform}] selected {select_top(platform, ws, end_date)}")

    blurbs = by.generate_blurbs(week_start, week_end)
    print(f"[blurbs] {blurbs}")

    final = selected_counts(ws, end_date)
    print(f"=== DONE: selected now {final} ===")
    return 0 if all(final[p] > 0 for p in todo) else 2


if __name__ == '__main__':
    raise SystemExit(main())
