"""
Batch update podcast thumbnails - Replace generic show artwork with
episode-specific images from Spotify for the 6 missed editions.
"""
import os
import sys
import time
import requests
import base64
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL', 'https://ksqrakczmecdbzxwsvea.supabase.co')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY', '')
SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtzcXJha2N6bWVjZGJ6eHdzdmVhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjgwMjYxMTMsImV4cCI6MjA4MzYwMjExM30.sotuDt98HLIaDvkINuT-2mC8DPgpDTB6luu_xKCxe64'

SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

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


class SpotifyClient:
    """Minimal Spotify client for episode search."""

    def __init__(self):
        self.access_token = None
        self.token_expires = None
        if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
            print("ERROR: SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set")
            sys.exit(1)

    def get_token(self):
        if self.access_token and self.token_expires and datetime.now() < self.token_expires:
            return self.access_token

        credentials = f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}"
        encoded = base64.b64encode(credentials.encode()).decode()

        response = requests.post(
            'https://accounts.spotify.com/api/token',
            headers={
                'Authorization': f'Basic {encoded}',
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            data={'grant_type': 'client_credentials'},
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            self.access_token = data['access_token']
            self.token_expires = datetime.now() + timedelta(seconds=data['expires_in'] - 60)
            return self.access_token

        print(f"  Spotify auth failed: {response.status_code}")
        return None

    def search_episode(self, episode_title, show_name=None):
        token = self.get_token()
        if not token:
            return None

        if show_name:
            clean_episode = episode_title.replace('#', '').replace('|', ' ').replace(':', ' ')[:60]
            clean_show = show_name.replace('#', '').replace('|', ' ').replace(':', ' ')[:40]
            search_query = f"{clean_episode} {clean_show}"
        else:
            search_query = episode_title[:80]

        spotify_market = os.getenv('PODCAST_COUNTRY', '')
        params = {
            'q': search_query,
            'type': 'episode',
            'limit': 5,
        }
        if spotify_market:
            params['market'] = spotify_market

        try:
            response = requests.get(
                'https://api.spotify.com/v1/search',
                headers={'Authorization': f'Bearer {token}'},
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                episodes = response.json().get('episodes', {}).get('items', [])
                if not episodes:
                    return None

                episode_title_lower = episode_title.lower()

                # Try to find a close title match first
                for ep in episodes:
                    ep_name = ep.get('name', '').lower()
                    if episode_title_lower[:30] in ep_name or ep_name[:30] in episode_title_lower:
                        images = ep.get('images', [])
                        return {
                            'episode_image': images[0]['url'] if images else None,
                            'name': ep.get('name'),
                        }

                # Fall back to first result
                ep = episodes[0]
                images = ep.get('images', [])
                return {
                    'episode_image': images[0]['url'] if images else None,
                    'name': ep.get('name'),
                }

            elif response.status_code == 401:
                self.access_token = None
                self.token_expires = None
                return self.search_episode(episode_title, show_name)

            return None
        except Exception as e:
            print(f"    Spotify search error: {e}")
            return None


if __name__ == '__main__':
    spotify = SpotifyClient()

    # Verify Spotify auth works
    token = spotify.get_token()
    if not token:
        print("Failed to authenticate with Spotify. Check credentials.")
        sys.exit(1)
    print("Spotify authenticated successfully.\n")

    total_updated = 0
    total_skipped = 0
    total_no_match = 0

    for week_start, week_end in WEEKS:
        ws = week_start.strftime('%Y-%m-%d')
        end_date = (week_end + timedelta(days=1)).strftime('%Y-%m-%d')

        print(f"{'='*55}")
        print(f"  {week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}")
        print(f"{'='*55}")

        # Get selected podcast episodes for this week
        episodes = supabase_get('content_items',
            f'status=eq.selected'
            f'&platform=eq.podcast'
            f'&published_date=gte.{ws}&published_date=lt.{end_date}'
            f'&select=id,title,thumbnail_url,creator_id'
            f'&order=published_date') or []

        if not episodes:
            print("  No podcast episodes found\n")
            continue

        # Fetch creator names for this batch
        creator_ids = list(set(e.get('creator_id') for e in episodes if e.get('creator_id')))
        creators_map = {}
        if creator_ids:
            creators = supabase_get('creators', f'id=in.({",".join(map(str, creator_ids))})') or []
            creators_map = {c['id']: c.get('name') for c in creators}

        print(f"  {len(episodes)} podcast episodes\n")

        for i, ep in enumerate(episodes, 1):
            title = ep.get('title', '')
            creator_name = creators_map.get(ep.get('creator_id'))
            current_thumb = ep.get('thumbnail_url', '')

            result = spotify.search_episode(title, creator_name)
            time.sleep(0.1)  # Rate limit

            if not result or not result.get('episode_image'):
                total_no_match += 1
                print(f"  [{i}/{len(episodes)}] NO MATCH: {title[:55]}")
                continue

            new_image = result['episode_image']

            if new_image == current_thumb:
                total_skipped += 1
                print(f"  [{i}/{len(episodes)}] SAME: {title[:55]}")
                continue

            # Update the thumbnail
            success = supabase_patch('content_items', f'id=eq.{ep["id"]}', {
                'thumbnail_url': new_image,
                'updated_at': datetime.now(timezone.utc).isoformat()
            })

            if success:
                total_updated += 1
                print(f"  [{i}/{len(episodes)}] UPDATED: {title[:55]}")
            else:
                print(f"  [{i}/{len(episodes)}] FAIL: {title[:55]}")

        print()

    print(f"{'='*55}")
    print(f"  DONE: {total_updated} updated, {total_skipped} already correct, {total_no_match} no Spotify match")
    print(f"{'='*55}")
