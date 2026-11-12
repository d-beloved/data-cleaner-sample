"""Text normalisation helpers for user-generated content.

Standard library only, so the cleaner runs anywhere pandas runs.
"""
from __future__ import annotations

import html
import re
import unicodedata

_BLOCK_TAG = re.compile(r"</?(?:p|br|div|li|ul|ol|tr|td|th|h[1-6]|blockquote)\b[^>]*>", re.IGNORECASE)
_TAG = re.compile(r"</?[a-zA-Z][^<>]*>|<!--.*?-->", re.DOTALL)
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]*\w")
_PHONE = re.compile(r"(?<![\w.])\+?\d[\d\s().-]{7,}\d(?!\w)")
_HANDLE = re.compile(r"(?<!\w)@\w+")
_HASHTAG = re.compile(r"(?<!\w)#(\w+)")
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]+")
_REPEAT = re.compile(r"(.)\1{2,}")
_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")
_TOKEN = re.compile(r"[^\W_]+(?:'[^\W_]+)?")

# Curly quotes, dashes and the ellipsis survive NFKC, so map them by hand.
_QUOTES = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", "…": "...",
})

STOPWORDS = frozenset("""
a about above after again against all am an and any are as at be because been
before being below between both but by can did do does doing down during each
few for from further had has have having he her here hers him his how i if in
into is it its just me more most my no nor not of off on once only or other our
out over own same she so some such than that the their them then there these
they this those through to too under until up very was we were what when where
which while who whom why will with you your
""".split())


def clean_text(
    value: str,
    *,
    lowercase: bool = True,
    strip_html: bool = True,
    strip_urls: bool = True,
    strip_emoji: bool = True,
    strip_handles: bool = True,
    mask_pii: bool = False,
    squash_repeats: bool = True,
) -> str:
    """Return a normalised, still human-readable version of `value`."""
    text = value
    if strip_html:
        # Block tags become spaces so words do not fuse; inline tags just vanish.
        text = _TAG.sub("", _BLOCK_TAG.sub(" ", html.unescape(text)))
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES)
    if strip_urls:
        text = _URL.sub(" ", text)
    if mask_pii:
        text = _EMAIL.sub("[email]", text)
        text = _PHONE.sub("[phone]", text)
    if strip_handles:
        text = _HANDLE.sub(" ", text)
    text = _HASHTAG.sub(r"\1", text)
    if strip_emoji:
        text = _EMOJI.sub(" ", text)
    if squash_repeats:
        # "soooo goooood!!!!" -> "soo good!!"
        text = _REPEAT.sub(r"\1\1", text)
    if lowercase:
        text = text.lower()
    return _WS.sub(" ", text).strip()


def dedupe_key(value: str) -> str:
    """Case, punctuation and whitespace insensitive key for duplicate checks."""
    text = unicodedata.normalize("NFKC", value).casefold()
    return _WS.sub(" ", _PUNCT.sub(" ", text)).strip()


def tokenize(value: str, *, remove_stopwords: bool = False) -> list[str]:
    """Split text into lowercase word tokens."""
    tokens = _TOKEN.findall(value.lower())
    if remove_stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS]
    return tokens
