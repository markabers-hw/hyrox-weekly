"""Plain-text cleanup for content descriptions before they go into newsletter HTML.

Podcast and some article descriptions arrive as raw HTML from RSS feeds (<p>, <br>, <strong>, <li>...).
The newsletter templates paste descriptions in unescaped, so that markup used to land inside
<p class="content-preview">. Browsers close that paragraph early, and the nested <p> loses the
class, which made some descriptions render at a different font size from the rest.
"""
import re
from html import unescape

# Closing block tags and <br> are where a line break was intended, so they become a space
_BLOCK_BREAK = re.compile(r'</(?:p|div|li|ul|ol|h[1-6]|blockquote)\s*>|<br\s*/?>', re.IGNORECASE)
_TAG = re.compile(r'</?[a-zA-Z][^>]*>')
_UNFINISHED_TAG = re.compile(r'</?[a-zA-Z][^>]*$')  # a tag cut off by an earlier truncation
_WHITESPACE = re.compile(r'\s+')


def _strip_tags(text: str) -> str:
    text = _BLOCK_BREAK.sub(' ', text)
    text = _TAG.sub('', text)
    return _UNFINISHED_TAG.sub('', text)


def clean_description(text: str | None) -> str:
    """Return the description as plain text on one line: no HTML tags, entities decoded, whitespace collapsed.

    Any "<" or ">" left over after the tags are removed is escaped, so the result can be pasted into HTML as is.
    """
    if not text:
        return ''
    text = _strip_tags(text)
    text = _strip_tags(unescape(text))  # feeds that double-encode send "&lt;p&gt;" which decodes to a tag
    text = _WHITESPACE.sub(' ', text).strip()
    return text.replace('<', '&lt;').replace('>', '&gt;')
