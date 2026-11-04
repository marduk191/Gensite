"""Generic clone-intent detection and fidelity-priority instructions.

Pure stdlib, no site-specific knowledge. ``is_clone_brief`` decides whether the
human part of a brief explicitly asks to clone/recreate a public web page;
``clone_instructions`` returns the priority contract to add to the generation
prompt (empty string for ordinary briefs).
"""
from __future__ import annotations

import re

__all__ = ['is_clone_brief', 'clone_instructions']

_SCHEME_URL = r'https?://[^\s<>"\')\]]+'
_FILE_EXT = ('html', 'htm', 'css', 'js', 'json', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'txt', 'md', 'py',
             'zip', 'pdf', 'ico', 'xml', 'mp4', 'bat', 'exe', 'ts', 'yml', 'yaml')
_BARE_DOMAIN = (r'(?:www\.)?(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+(?!(?:' + '|'.join(_FILE_EXT) +
                r')\b)[a-z]{2,}(?:/[^\s<>"\')\]]*)?')
_URL_TOKEN = '\x00URL\x00'

# Blocks that are not the human's words: fenced code, markers, whole HTML documents.
_BLOCK_RES = [
    re.compile(r'```.*?(?:```|\Z)', re.S),
    re.compile(r'<<<[^>\n]*>>>.*?(?=<<<|\Z)', re.S),
    re.compile(r'<!doctype\b.*?(?:</html\s*>|\Z)', re.S | re.I),
    re.compile(r'<html\b.*?(?:</html\s*>|\Z)', re.S | re.I),
    re.compile(r'<(style|script|head|body)\b.*?(?:</\1\s*>|\Z)', re.S | re.I),
    re.compile(r'<[a-zA-Z/][^>]*>'),
]
# Lines the app generates itself; they carry no clone intent.
_AUTO_LINE = re.compile(r'^\s*(?:visual style|image art direction|use semantic accessible html)\b', re.I)
_SECTION_BLOCK = re.compile(
    r'^[ \t]*(?:BEGIN|START)?[ \t]*(?:PREVIOUS|CURRENT|EXISTING|TEMPLATE)[ \t_-]*(?:SITE|SOURCE|HTML|PAGE|TEMPLATE)[^\n]*\n'
    r'.*?(?=^[ \t]*(?:END|STOP)\b[^\n]*$|\Z)', re.S | re.I | re.M)

_NEG = re.compile(r"\b(?:don'?t|do not|never|not|without|no need to|instead of|rather than)\b[^.\n]{0,30}$", re.I)
_STRONG = re.compile(r'\b(?:clone|cloning|recreate|re-create|recreating|replicate|replicating|reproduce|'
                     r'duplicate|rebuild|remake|mirror)\b', re.I)
_SOFT = re.compile(
    r'\b(?:copy|copying|match|matching|imitate|emulate)\b[^.\n]{0,40}?\b(?:the\s+|this\s+|that\s+|its\s+|their\s+|an?\s+|exact\s+)*'
    r'(?:web\s*)?(?:page|site|website|webpage|layout|design|look|appearance|style|theme|ui|interface|homepage|landing)\b',
    re.I)
_COPY_AS_TEXT = re.compile(r'\b(?:write|draft|compose|create|generate)\s+(?:the\s+|some\s+|a\s+)?(?:copy|text)\b', re.I)
_LOCAL = re.compile(r'^(?:https?://)?(?:localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|\[::1\])', re.I)


def _human_text(brief: object) -> str:
    text = brief if isinstance(brief, str) else ''
    for rx in (_SECTION_BLOCK, *_BLOCK_RES):
        text = rx.sub(' ', text)
    return '\n'.join(l for l in text.splitlines() if not _AUTO_LINE.match(l))


def _mask_urls(text: str) -> tuple[str, int]:
    count = 0

    def sub(m: re.Match) -> str:
        nonlocal count
        if _LOCAL.match(m.group(0)):
            return m.group(0)
        count += 1
        return _URL_TOKEN
    text = re.sub(_SCHEME_URL, sub, text, flags=re.I)
    text = re.sub(r'(?<![\w@./-])' + _BARE_DOMAIN + r'(?![\w@-])', sub, text, flags=re.I)
    return text, count


def _clauses(masked: str):
    for line in masked.splitlines():
        for sent in re.split(r'(?<=[.!?;])\s+', line):
            if sent.strip():
                yield sent


def _has_intent(clause: str) -> bool:
    if _URL_TOKEN not in clause:
        return False
    for rx in (_STRONG, _SOFT):
        for m in rx.finditer(clause):
            if rx is _SOFT and _COPY_AS_TEXT.search(clause[max(0, m.start() - 20):m.end()]):
                continue
            if _NEG.search(clause[:m.start()]):
                continue
            return True
    return False


def is_clone_brief(brief: object) -> bool:
    """True when the human text explicitly asks to clone/recreate a public URL."""
    masked, n = _mask_urls(_human_text(brief))
    return bool(n) and any(_has_intent(c) for c in _clauses(masked))


_INSTRUCTIONS = '''CLONE FIDELITY CONTRACT (the human asked to clone/recreate an existing public web page):
1. This is a faithful recreation, not a redesign or a "inspired by" interpretation. Do not substitute your own taste, a generic gallery/hero/portfolio layout, or a template.
2. The measured reference data (color palette and light/dark scheme, page and container backgrounds, layout structure, container positions and sizes, sidebar/header/footer placement, typography, spacing, component styling, and mobile/responsive behavior) is authoritative. Reproduce it from the measurements, not from memory or assumption. Region text identifies what belongs in each box: preserve that content assignment, not just the box dimensions. Do not swap a profile/information sidebar for a navigation menu, move its contents into a new main-column profile card, or reorder tabs and banners.
3. Priority order: (a) the human's original purpose and any explicitly requested changes; (b) the measured source design; (c) everything else. App-generated lines such as "Visual style", preset or template hints, and "Image art direction" are lower priority and MUST NOT override the source theme, colors, or layout. If they conflict with the source, follow the source.
4. Image settings stay as the user configured them. Requested generated art may replace the source's imagery, but it must never change the source's theme, color scheme, or layout; place it in the same slots, sizes, and crops the source uses.
5. Preserve the source's visible information architecture: the same regions, navigation, section order, headings, and labels as read. Do not invent related pages, sections, or content from search results or guesses; only add pages the human asked for or that navigation to the source's own visible links requires.
6. Matching content, section names, or item counts alone is not a match. The recreation must also match the measured visual structure (scheme, layout regions, typography, proportions) at desktop and mobile widths. Do not claim the clone matches unless that was checked.
7. If part of the source could not be read or measured, say so rather than filling the gap with an invented design.'''


def clone_instructions(brief: object) -> str:
    """Priority contract text for clone briefs; '' for ordinary generation."""
    return _INSTRUCTIONS if is_clone_brief(brief) else ''
