"""
Suggest athlete tags across the full content_items pool.

Scans every content_items title + description and matches them against the
athlete roster (full name, Instagram handle, and any configured search_terms).
Matches are written to athlete_content as status='suggested', tag_source='suggested'
for the curator to confirm/reject in the dashboard. Nothing is auto-selected.

Precision-first by default: only an exact full-name phrase, an Instagram handle,
or an explicit search_term will match. Pass --loose to additionally match when the
first AND last name tokens both appear as separate words (noisier, still confirmed).

Usage:
    python suggest_athlete_tags.py                 # dry-run: print what would be suggested
    python suggest_athlete_tags.py --apply         # write suggestions to athlete_content
    python suggest_athlete_tags.py --loose         # dry-run incl. both-tokens matches
    python suggest_athlete_tags.py --athlete 6     # limit to one athlete id
    python suggest_athlete_tags.py --limit 500     # only scan N most recent content items
"""
import os
import re
import sys
import argparse
import unicodedata
from collections import defaultdict

import psycopg2
from psycopg2.extras import RealDictCursor, execute_values


def load_env(path='/Users/mark/hyrox-weekly/.env') -> dict:
    env = {}
    for line in open(path):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k] = v.strip().strip('"').strip("'")
    return env


def connect(env: dict):
    dsn = env.get('DATABASE_URL')
    if dsn:
        return psycopg2.connect(dsn)
    return psycopg2.connect(
        host=env['DB_HOST'], dbname=env['DB_NAME'], user=env['DB_USER'],
        password=env['DB_PASSWORD'], port=env.get('DB_PORT', '5432'),
    )


def normalize(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace — for robust matching."""
    if not text:
        return ''
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'\s+', ' ', text.lower()).strip()


def build_patterns(athlete: dict, loose: bool) -> list:
    """Return a list of (compiled_regex, kind) tuples for an athlete.

    kind is one of: 'name' (exact full-name phrase), 'handle', 'search_term',
    'tokens' (loose first+last both-present, only when loose=True).
    """
    patterns = []
    name = normalize(athlete['name'])
    tokens = [t for t in re.split(r'[\s\-]+', name) if t]

    if len(tokens) >= 2:
        # Exact full-name phrase: tokens contiguous, separated by space/hyphen.
        phrase = r'[\s\-]+'.join(re.escape(t) for t in tokens)
        patterns.append((re.compile(r'\b' + phrase + r'\b'), 'name'))
        if loose:
            # First AND last token both present as standalone words (any position).
            first = re.compile(r'\b' + re.escape(tokens[0]) + r'\b')
            last = re.compile(r'\b' + re.escape(tokens[-1]) + r'\b')
            patterns.append(((first, last), 'tokens'))

    handle = (athlete.get('instagram_handle') or '').lstrip('@').strip()
    if handle and len(handle) >= 5:
        h = normalize(handle)
        # Match the handle with dots either present or removed (colelearn / cole.learn).
        variants = {re.escape(h), re.escape(h.replace('.', '')), h.replace('.', r'[.\s]?')}
        for v in variants:
            patterns.append((re.compile(r'(?<![\w.])' + v + r'(?![\w.])'), 'handle'))

    for term in (athlete.get('search_terms') or []):
        term = normalize(term)
        if len(term) >= 4 and term != name:
            patterns.append((re.compile(r'\b' + re.escape(term).replace(r'\ ', r'[\s\-]+') + r'\b'), 'search_term'))

    return patterns


def match_field(text: str, patterns: list):
    """Return the strongest match kind for a single text field, or None."""
    best = None
    for pat, kind in patterns:
        if kind == 'tokens':
            first, last = pat
            if first.search(text) and last.search(text):
                best = best or 'tokens'
        else:
            if pat.search(text):
                return kind  # high-precision kinds win immediately
    return best


def match_athlete(title: str, description: str, patterns: list, include_description: bool):
    """Match against title first (high precision). Fall back to description only
    when include_description is set. Returns (kind, location) or None.
    Location is 'title' or 'desc' — a title hit means the content is *about* the
    athlete; a desc hit is just a mention (e.g. named in a race-recap list)."""
    kind = match_field(title, patterns)
    if kind:
        return kind, 'title'
    if include_description:
        kind = match_field(description, patterns)
        if kind:
            return kind, 'desc'
    return None


def main():
    ap = argparse.ArgumentParser(description='Suggest athlete tags across content_items')
    ap.add_argument('--apply', action='store_true', help='Write suggestions (default: dry-run)')
    ap.add_argument('--loose', action='store_true', help='Also match first+last tokens anywhere')
    ap.add_argument('--include-description', action='store_true',
                    help='Also match names mentioned in the description (noisier: race-recap lists)')
    ap.add_argument('--youtube-min-seconds', type=int, default=None,
                    help='Skip YouTube videos shorter than this (default: premium_settings '
                         'athlete_youtube_min_duration_seconds, or 600)')
    ap.add_argument('--athlete', type=int, help='Limit to a single athlete id')
    ap.add_argument('--limit', type=int, help='Only scan N most-recent content items')
    args = ap.parse_args()

    env = load_env()
    conn = connect(env)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    where = 'WHERE is_active' + (' AND id=%s' if args.athlete else '')
    cur.execute(f"SELECT id,name,slug,instagram_handle,search_terms FROM athletes {where} ORDER BY name",
                (args.athlete,) if args.athlete else None)
    athletes = cur.fetchall()

    cur.execute(f"SELECT id,title,description,platform,duration_seconds FROM content_items ORDER BY id DESC"
                + (f" LIMIT {int(args.limit)}" if args.limit else ""))
    content = cur.fetchall()

    # Minimum YouTube runtime (adjustable in premium_settings; CLI overrides).
    if args.youtube_min_seconds is not None:
        yt_min = args.youtube_min_seconds
    else:
        cur.execute("SELECT value FROM premium_settings WHERE key='athlete_youtube_min_duration_seconds'")
        row = cur.fetchone()
        yt_min = int(row['value']) if row and row.get('value') else 600

    # Existing (athlete_id, content_id) pairs — never re-suggest these.
    cur.execute("SELECT athlete_id, content_id FROM athlete_content")
    existing = {(r['athlete_id'], r['content_id']) for r in cur.fetchall()}

    scope = []
    scope.append('LOOSE tokens' if args.loose else 'precise')
    scope.append('title+description' if args.include_description else 'title-only')
    scope.append(f'YouTube ≥ {yt_min}s' if yt_min > 0 else 'no YouTube min')
    print(f"Scanning {len(content)} content items against {len(athletes)} athletes "
          f"({', '.join(scope)})...\n")

    athlete_pats = {a['id']: (a, build_patterns(a, args.loose)) for a in athletes}
    suggestions = []          # (athlete_id, content_id, content_type, kind, location)
    by_athlete = defaultdict(list)
    skipped_short_yt = 0

    for item in content:
        # Enforce the minimum YouTube runtime for athlete editions.
        if yt_min > 0 and item['platform'] == 'youtube' and (item.get('duration_seconds') or 0) < yt_min:
            skipped_short_yt += 1
            continue
        title = normalize(item['title'] or '')
        desc = normalize(item['description'] or '')
        if not title and not desc:
            continue
        for aid, (a, pats) in athlete_pats.items():
            if (aid, item['id']) in existing:
                continue
            hit = match_athlete(title, desc, pats, args.include_description)
            if hit:
                kind, location = hit
                suggestions.append((aid, item['id'], item['platform'], kind, location))
                by_athlete[aid].append((item, kind, location))

    # Report grouped by athlete
    kind_counts = defaultdict(int)
    for _, _, _, kind, location in suggestions:
        kind_counts[f'{kind}·{location}'] += 1
    for aid in sorted(by_athlete, key=lambda i: athlete_pats[i][0]['name']):
        a = athlete_pats[aid][0]
        items = by_athlete[aid]
        print(f"● {a['name']}  ({len(items)} new suggestion{'s' if len(items)!=1 else ''})")
        for item, kind, location in items[:12]:
            print(f"    [{kind:11}·{location:5}] ({item['platform']}) {(item['title'] or '')[:60]}")
        if len(items) > 12:
            print(f"    … +{len(items)-12} more")
        print()

    print("=" * 60)
    print(f"TOTAL: {len(suggestions)} new suggestions across {len(by_athlete)} athletes")
    print(f"  by match kind: {dict(kind_counts)}")
    if yt_min > 0:
        print(f"  skipped {skipped_short_yt} YouTube videos shorter than {yt_min}s")

    if not args.apply:
        print("\nDry-run only. Re-run with --apply to write these as status='suggested'.")
        conn.close()
        return

    rows = [(aid, cid, ctype, 'suggested', 'suggested') for (aid, cid, ctype, _, _) in suggestions]
    execute_values(cur,
        "INSERT INTO athlete_content (athlete_id, content_id, content_type, status, tag_source) VALUES %s "
        "ON CONFLICT (athlete_id, content_id) DO NOTHING",
        rows)
    conn.commit()
    print(f"\nApplied: inserted {cur.rowcount} suggestion rows (status='suggested', tag_source='suggested').")
    conn.close()


if __name__ == '__main__':
    main()
