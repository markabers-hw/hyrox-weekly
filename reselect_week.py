#!/usr/bin/env python3
"""
Re-run auto-selection for editions that are not published yet, using the current rules in selection.py.

For each edition and platform (YouTube, podcasts, articles; Reddit's rules did not change):
  - items you picked by hand (selection_method other than 'yolo') are left alone and count toward the quota
  - items you rejected by hand are never brought back
  - auto-picks that no longer make the cut go back to 'discovered'
  - new picks are selected and everything is renumbered 10, 20, 30...
  - blurbs are written for new picks that lack one
Editions that already have a published record are skipped, so nothing live can change.

Every run first saves the affected rows to reselect_snapshots/; --restore puts them back.

Usage:
    python reselect_week.py --from-edition 32 --to-edition 48 --dry-run    # show what would change
    python reselect_week.py --from-edition 32 --to-edition 48              # apply
    python reselect_week.py --restore reselect_snapshots/<file>.json       # undo a run
"""
import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone

import batch_yolo as by
from selection import SELECT_FIELDS, choose_items

FIRST_EDITION_MONDAY = date(2025, 12, 15)
PLATFORMS = ('youtube', 'podcast', 'article')
SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'reselect_snapshots')
SAVED_FIELDS = ('status', 'display_order', 'selection_method')


def edition_week(number: int) -> tuple[date, date]:
    """Monday and Sunday of an edition."""
    start = FIRST_EDITION_MONDAY + timedelta(days=7 * (number - 1))
    return start, start + timedelta(days=6)


def is_published(number: int) -> bool:
    return bool(by.supabase_get('weekly_editions', f'edition_number=eq.{number}&select=id'))


def fetch_pool(platform: str, start: date, end: date) -> list[dict]:
    """Everything that could be selected: discovered items plus the current selections."""
    return by.supabase_get('content_items',
        f'platform=eq.{platform}&status=in.(discovered,selected)'
        f'&published_date=gte.{start}&published_date=lt.{end + timedelta(days=1)}'
        f'&select={SELECT_FIELDS},status,display_order,selection_method&limit=1000') or []


def plan_platform(platform: str, pool: list[dict], priority_names: set[str]) -> dict:
    """Work out what changes for one platform. Pure: no writes."""
    locked = [i for i in pool if i['status'] == 'selected' and i.get('selection_method') != 'yolo']
    candidates = [i for i in pool if i not in locked]
    config = dict(by.YOLO_CONFIG)
    config[f'yolo_max_{platform}'] = max(int(config[f'yolo_max_{platform}']) - len(locked), 0)

    chosen = choose_items(candidates, platform, config, priority_names)
    base = max((i.get('display_order') or 0 for i in locked), default=0)  # number new picks after hand-picked ones
    wanted = {i['id']: base + (rank + 1) * 10 for rank, i in enumerate(chosen)}

    current_auto = {i['id']: i for i in candidates if i['status'] == 'selected'}
    return {
        'remove': [i for iid, i in current_auto.items() if iid not in wanted],
        'add': [i for i in chosen if i['id'] not in current_auto],
        'renumber': [(i, wanted[i['id']]) for i in chosen
                     if i['id'] in current_auto and current_auto[i['id']].get('display_order') != wanted[i['id']]],
        'wanted': wanted,
        'locked': len(locked),
        'kept': sum(1 for i in chosen if i['id'] in current_auto),
    }


def patch_item(item_id: int, fields: dict) -> None:
    fields = {**fields, 'updated_at': datetime.now(timezone.utc).isoformat()}
    if not by.supabase_patch('content_items', f'id=eq.{item_id}', fields):
        raise RuntimeError(f"Saving content item {item_id} failed; stopped so nothing is left half-changed unnoticed "
                           f"(re-run, or undo with --restore)")


def apply_plan(plan: dict) -> None:
    for item in plan['remove']:
        patch_item(item['id'], {'status': 'discovered', 'selection_method': None, 'display_order': None})
    for item in plan['add']:
        patch_item(item['id'], {'status': 'selected', 'selection_method': 'yolo',
                                'display_order': plan['wanted'][item['id']]})
    for item, order in plan['renumber']:
        patch_item(item['id'], {'display_order': order})


def restore(snapshot_path: str) -> int:
    """Put every row in a snapshot back the way it was."""
    with open(snapshot_path, encoding='utf-8') as f:
        rows = json.load(f)
    changed = 0
    for row in rows:
        now = by.supabase_get('content_items', f"id=eq.{row['id']}&select={','.join(SAVED_FIELDS)}") or [{}]
        if any(now[0].get(k) != row[k] for k in SAVED_FIELDS):
            patch_item(row['id'], {k: row[k] for k in SAVED_FIELDS})
            changed += 1
    print(f"Restored {changed} of {len(rows)} rows from {snapshot_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description='Re-select unpublished editions with the current rules')
    parser.add_argument('--from-edition', type=int)
    parser.add_argument('--to-edition', type=int)
    parser.add_argument('--dry-run', action='store_true', help='Show what would change without writing anything')
    parser.add_argument('--no-blurbs', action='store_true', help='Skip writing blurbs for new picks')
    parser.add_argument('--restore', metavar='SNAPSHOT', help='Undo a previous run from its snapshot file')
    args = parser.parse_args()

    if args.restore:
        return restore(args.restore)
    if not (args.from_edition and args.to_edition):
        parser.error('give --from-edition and --to-edition (or --restore)')

    by.load_yolo_config()
    priority_names = {p['source_name'].lower() for p in by.supabase_get('priority_sources', 'is_active=eq.true') or []}

    plans, snapshot = [], []
    for number in range(args.from_edition, args.to_edition + 1):
        start, end = edition_week(number)
        if is_published(number):
            print(f"Edition {number}: already published, skipped")
            continue
        for platform in PLATFORMS:
            pool = fetch_pool(platform, start, end)
            plan = plan_platform(platform, pool, priority_names)
            plans.append((number, platform, start, end, plan))
            snapshot += [{'id': i['id'], **{k: i.get(k) for k in SAVED_FIELDS}} for i in pool]
            print(f"Edition {number} {platform:8}: {len(pool):>3} candidates | keep {plan['kept']:>2}, "
                  f"add {len(plan['add']):>2}, remove {len(plan['remove']):>2}, renumber {len(plan['renumber']):>2}"
                  + (f" | {plan['locked']} hand-picked left alone" if plan['locked'] else ''))

    totals = {k: sum(len(p[4][k]) for p in plans) for k in ('add', 'remove', 'renumber')}
    print(f"\nTotal: add {totals['add']}, remove {totals['remove']}, renumber {totals['renumber']}")
    if args.dry_run:
        print('Dry run: nothing was written.')
        return 0

    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    snapshot_path = os.path.join(SNAPSHOT_DIR, f"{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
    with open(snapshot_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f)
    print(f"Saved {len(snapshot)} rows to {snapshot_path} (undo with --restore)")

    for number, platform, start, end, plan in plans:
        apply_plan(plan)
    print('Selections updated.')

    if not args.no_blurbs:
        for number in sorted({p[0] for p in plans}):
            start, end = edition_week(number)
            result = by.generate_blurbs(datetime.combine(start, datetime.min.time()), datetime.combine(end, datetime.min.time()))
            print(f"Edition {number} blurbs: {result}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
