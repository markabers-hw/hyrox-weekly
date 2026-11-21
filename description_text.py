"""Plain-text cleanup for content descriptions before they go into newsletter HTML.

Podcast and some article descriptions arrive as raw HTML from RSS feeds (<p>, <br>, <strong>, <li>...).
The newsletter templates paste descriptions in unescaped, so that markup used to land inside
<p class="content-preview">. Browsers close that paragraph early, and the nested <p> loses the
class, which made some descriptions render at a different font size from the rest.

Long descriptions used to be chopped at a fixed character count by the templates, which left
endings like "stop chasing ever...". shorten_description trims at the end of a sentence instead.
"""
import re
from html import unescape

# Closing block tags and <br> are where a line break was intended, so they become a space
_BLOCK_BREAK = re.compile(r'</(?:p|div|li|ul|ol|h[1-6]|blockquote)\s*>|<br\s*/?>', re.IGNORECASE)
_TAG = re.compile(r'</?[a-zA-Z][^>]*>')
_UNFINISHED_TAG = re.compile(r'</?[a-zA-Z][^>]*$')  # a tag cut off by an earlier truncation
_WHITESPACE = re.compile(r'\s+')

# A period after one of these (or after a single capital letter, as in "J. Smith") is not the end of a sentence
_ABBREVIATIONS = {'dr', 'mr', 'mrs', 'ms', 'prof', 'st', 'vs', 'jr', 'sr', 'no', 'inc', 'ltd', 'co', 'approx'}
MIN_SENTENCE_CHARS = 80  # a sentence break earlier than this would throw away too much text


def _strip_tags(text: str) -> str:
    text = _BLOCK_BREAK.sub(' ', text)
    text = _TAG.sub('', text)
    return _UNFINISHED_TAG.sub('', text)


def _ends_sentence(text: str, i: int) -> bool:
    """True if text[i] is a '.', '!' or '?' that really finishes a sentence."""
    if text[i] not in '.!?' or (i + 1 < len(text) and text[i + 1] != ' '):
        return False
    last_word = re.search(r'(\S+)$', text[:i])
    if not last_word:
        return True
    word = last_word.group(1)
    return not (text[i] == '.' and (word.lower() in _ABBREVIATIONS or re.fullmatch(r'[A-Z]', word) or '.' in word))


def shorten_description(text: str, limit: int) -> str:
    """Trim plain text to at most `limit` characters without ending mid-word.

    Prefers the end of the last complete sentence that fits. If there is none (or it would keep
    less than MIN_SENTENCE_CHARS), cuts at the last whole word and adds an ellipsis.
    """
    if len(text) <= limit:
        return text
    for i in range(limit - 1, MIN_SENTENCE_CHARS - 2, -1):
        if _ends_sentence(text, i):
            return text[:i + 1]
    cut = text[:limit - 1].rsplit(' ', 1)[0] if ' ' in text[:limit - 1] else text[:limit - 1]
    return cut.rstrip(' ,;:-–—') + '…'


def clean_description(text: str | None, limit: int | None = None) -> str:
    """Return the description as plain text on one line: no HTML tags, entities decoded, whitespace collapsed.

    With `limit`, longer text is trimmed at a sentence or word boundary (see shorten_description).
    Any "<" or ">" left over after the tags are removed is escaped, so the result can be pasted into HTML as is.
    """
    if not text:
        return ''
    text = _strip_tags(text)
    text = _strip_tags(unescape(text))  # feeds that double-encode send "&lt;p&gt;" which decodes to a tag
    text = _WHITESPACE.sub(' ', text).strip()
    if limit:
        text = shorten_description(text, limit)
    return text.replace('<', '&lt;').replace('>', '&gt;')
