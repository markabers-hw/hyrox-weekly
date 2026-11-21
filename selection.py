"""Shared rules for auto-selecting a week's content (the Monday job, backfills and the dashboard's YOLO mode).

For YouTube, podcasts and articles:
  1. Relevance: an item must mention Hyrox (title, description or the creator's own name) and have a
     title in the Latin alphabet. Priority channels used to skip this, which let CrossFit Games and
     training-diary videos into the newsletter.
  2. Ranking: Hyrox in the title first, then priority sources, then an engagement signal for the platform.
  3. Variety: at most `yolo_max_per_creator` items per creator, unless that would leave slots empty.
Reddit is all from r/hyrox, so it only needs the comment/upvote bar and is ranked by comments then upvotes.

Pure functions only (no database or network), so every caller selects the same way.
"""
from collections import Counter

# Terms that mark an item as being about Hyrox. Deliberately short: "ski erg" or "wall balls" alone
# also appear in plain CrossFit and gym content.
HYROX_TERMS = ('hyrox', 'roxzone', 'fitness racing', 'hybrid racing')

# Fields every caller must fetch for choose_items to work
SELECT_FIELDS = ('id,title,description,platform,url,view_count,like_count,comment_count,'
                 'published_date,creators(name,credibility_score)')

DEFAULT_PER_CREATOR = 2


def _creator(item: dict) -> dict:
    return item.get('creators') or {}


def _mentions_hyrox(text: str) -> bool:
    text = text.lower()
    return any(term in text for term in HYROX_TERMS)


def relevance_tier(item: dict) -> int:
    """2 = Hyrox is in the title or the creator's own name, 1 = only in the description, 0 = never mentioned.

    A creator with "Hyrox" in its name is a dedicated source, so everything it posts counts as on topic.
    A title stuffed with hashtags ("Hyrox #hyroxworkout #gym #fitness") is demoted a tier: it mentions
    the word without being a considered piece about Hyrox.
    """
    title = item.get('title') or ''
    name = _creator(item).get('name') or ''
    if _mentions_hyrox(title) or _mentions_hyrox(name):
        return 1 if title.count('#') >= 2 else 2
    if _mentions_hyrox(item.get('description') or ''):
        return 1
    return 0


def is_latin_title(item: dict, min_share: float = 0.8) -> bool:
    """False for titles written mostly in a non-Latin script (Thai, Hindi, Chinese...).

    Discovery only drops videos whose language is declared as non-English, and many creators leave it blank.
    """
    letters = [c for c in (item.get('title') or '') if c.isalpha()]
    if not letters:
        return True
    return sum(1 for c in letters if ord(c) < 0x250) / len(letters) >= min_share


def engagement(item: dict, platform: str) -> float:
    """Platform signal used after relevance and priority.

    YouTube uses the same weights as the database's engagement_score (views + 5*likes + 10*comments),
    without its time decay. Podcasts and articles have no view counts, so the creator's credibility
    score stands in (all 0.5 unless you tune it on the creators table); newest wins any remaining tie.
    """
    if platform == 'youtube':
        return ((item.get('view_count') or 0) + 5 * (item.get('like_count') or 0)
                + 10 * (item.get('comment_count') or 0))
    return float(_creator(item).get('credibility_score') or 0)


def rank_candidates(items: list[dict], platform: str, priority_names: set[str]) -> list[dict]:
    """Best first. Reddit: comments, then upvotes. Others: relevance tier, priority source, engagement, newest."""
    def is_priority(item: dict) -> bool:
        return (_creator(item).get('name') or '').lower() in priority_names

    # Lowest id first, so items that tie on everything always end up in the same order, whatever order
    # the database returned them in. Without this, re-running selection could shuffle tied items.
    items = sorted(items, key=lambda i: i['id'])
    if platform == 'reddit':
        return sorted(items, key=lambda i: (0 if is_priority(i) else 1,
                                            -(i.get('comment_count') or 0), -(i.get('view_count') or 0)))
    # Stable sorts: newest first, then the main key, so newest wins any remaining tie
    items = sorted(items, key=lambda i: i.get('published_date') or '', reverse=True)
    return sorted(items, key=lambda i: (-relevance_tier(i), 0 if is_priority(i) else 1,
                                        -engagement(i, platform)))


def choose_items(items: list[dict], platform: str, config: dict, priority_names: set[str]) -> list[dict]:
    """The items to auto-select for one platform, best first.

    `config` holds the yolo_* settings (limits, Reddit bar, per-creator cap) as ints or numeric strings.
    """
    limit = int(config.get(f'yolo_max_{platform}', 8))

    if platform == 'reddit':
        min_comments = int(config.get('yolo_reddit_min_comments', 20))
        min_upvotes = int(config.get('yolo_reddit_min_upvotes', 20))
        eligible = [i for i in items if (i.get('comment_count') or 0) >= min_comments
                    or (i.get('view_count') or 0) >= min_upvotes]
        return rank_candidates(eligible, platform, priority_names)[:limit]

    eligible = [i for i in items if relevance_tier(i) > 0 and is_latin_title(i)]
    ranked = rank_candidates(eligible, platform, priority_names)

    # Soft per-creator cap: skipped items only fill slots the rest of the week couldn't
    cap = int(config.get('yolo_max_per_creator', DEFAULT_PER_CREATOR))
    chosen, held_back, per_creator = [], [], Counter()
    for item in ranked:
        if len(chosen) == limit:
            break
        creator_key = (_creator(item).get('name') or f"item-{item['id']}").lower()
        if cap and per_creator[creator_key] >= cap:
            held_back.append(item)
            continue
        per_creator[creator_key] += 1
        chosen.append(item)
    return chosen + held_back[:limit - len(chosen)]
