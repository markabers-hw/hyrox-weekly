"""
Batch blurb generator - Re-generate AI blurbs for all selected content
across the 6 missed weeks, processing per-edition to avoid repetition.
"""
import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://ksqrakczmecdbzxwsvea.supabase.co')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY', '')
SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtzcXJha2N6bWVjZGJ6eHdzdmVhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjgwMjYxMTMsImV4cCI6MjA4MzYwMjExM30.sotuDt98HLIaDvkINuT-2mC8DPgpDTB6luu_xKCxe64'
ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY')

WEEKS = [
    (datetime(2026, 2, 9), datetime(2026, 2, 15)),
    (datetime(2026, 2, 16), datetime(2026, 2, 22)),
    (datetime(2026, 2, 23), datetime(2026, 3, 1)),
    (datetime(2026, 3, 2), datetime(2026, 3, 8)),
    (datetime(2026, 3, 9), datetime(2026, 3, 15)),
    (datetime(2026, 3, 16), datetime(2026, 3, 22)),
]

def get_headers():
    key = SUPABASE_SERVICE_KEY if SUPABASE_SERVICE_KEY else SUPABASE_ANON_KEY
    return {
        'apikey': key, 'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json', 'Prefer': 'return=representation'
    }

def supabase_get(table, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url += f"?{params}"
    r = requests.get(url, headers=get_headers())
    return r.json() if r.status_code == 200 else []

def supabase_patch(table, params, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}"
    r = requests.patch(url, headers=get_headers(), json=data)
    return r.status_code in [200, 204]


def generate_blurb(client, item, creator_name, existing_blurbs):
    platform_context = {
        'youtube': 'YouTube video', 'podcast': 'podcast episode',
        'article': 'article', 'reddit': 'Reddit discussion'
    }.get(item.get('platform'), 'content')
    creator_info = f" by {creator_name}" if creator_name else ""

    existing_context = ""
    if existing_blurbs:
        existing_context = "\n\nOther blurbs already written for this edition (DO NOT reuse their opening words, sentence structures, or key phrases — vary your vocabulary and sentence patterns):\n"
        for b in existing_blurbs[-10:]:
            existing_context += f"- {b}\n"

    prompt = f"""Write a brief blurb for this {platform_context}{creator_info} for a Hyrox fitness newsletter.

Title: {item.get('title', '')}

Original Description: {(item.get('description') or 'No description available')[:1000]}{existing_context}

Requirements:
- STRICT LIMIT: Keep under 230 characters (about 1-2 short sentences)
- Write in a crisp, professional sports journalism style (think Sports Illustrated)
- Be informative and direct - no hype or exaggeration
- Avoid words like: epic, amazing, incredible, ultimate, game-changer, crushing it, insane
- Assume readers already know what Hyrox is - no need to explain the sport
- Focus on the specific value: what will readers learn or gain?
- Do not use quotation marks around the blurb
- Do not start with "This video..." or "In this episode..."
- Use varied sentence structures and opening words — no two blurbs in this edition should read alike

Just return the blurb text, nothing else."""

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}]
    )
    blurb = message.content[0].text.strip()

    if len(blurb) > 250:
        truncated = blurb[:247]
        last_period = truncated.rfind('.')
        last_space = truncated.rfind(' ')
        if last_period > 180:
            blurb = truncated[:last_period + 1]
        elif last_space > 200:
            blurb = truncated[:last_space] + '...'
        else:
            blurb = truncated + '...'

    return blurb


if __name__ == '__main__':
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    total_generated = 0
    total_failed = 0

    for week_start, week_end in WEEKS:
        ws = week_start.strftime('%Y-%m-%d')
        end_date = (week_end + timedelta(days=1)).strftime('%Y-%m-%d')

        print(f"\n{'='*50}")
        print(f"  {week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}")
        print(f"{'='*50}")

        content = supabase_get('content_items',
            f'status=eq.selected'
            f'&published_date=gte.{ws}&published_date=lt.{end_date}'
            f'&select=id,title,description,platform,ai_description,creator_id'
            f'&order=display_order.asc.nullslast,published_date') or []

        print(f"  {len(content)} selected items")

        # Fetch creator names
        creator_ids = list(set(c.get('creator_id') for c in content if c.get('creator_id')))
        creators_map = {}
        if creator_ids:
            creators = supabase_get('creators', f'id=in.({",".join(map(str, creator_ids))})') or []
            creators_map = {c['id']: c.get('name') for c in creators}

        edition_blurbs = []
        generated = 0
        failed = 0

        for i, item in enumerate(content, 1):
            creator_name = creators_map.get(item.get('creator_id'))
            try:
                blurb = generate_blurb(client, item, creator_name, edition_blurbs)
                edition_blurbs.append(blurb)

                supabase_patch('content_items', f'id=eq.{item["id"]}', {
                    'ai_description': blurb,
                    'use_ai_description': True,
                    'updated_at': datetime.now(timezone.utc).isoformat()
                })
                generated += 1
                print(f"  [{i}/{len(content)}] OK: {item.get('title','')[:55]}")
            except Exception as e:
                failed += 1
                print(f"  [{i}/{len(content)}] FAIL: {item.get('title','')[:55]} - {e}")

        print(f"  >> {generated}/{len(content)} generated, {failed} failed")
        total_generated += generated
        total_failed += failed

    print(f"\n{'='*50}")
    print(f"  DONE: {total_generated} blurbs generated, {total_failed} failed")
    print(f"{'='*50}")
