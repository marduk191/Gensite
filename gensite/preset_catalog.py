"""Curated WEBSITE page templates; never styling for the builder itself.

All paths are repository-relative POSIX paths. No network or UI dependency.
Unknown IDs and malformed catalogs raise ValueError; callers may show the error
and fall back to their own Custom/no-preset state (not a catalog entry).
"""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parents[1]  # repository root; data folders live here
CATALOG_PATH = ROOT / 'presets' / 'catalog.json'


def _safe_template(value: object) -> str:
    if not isinstance(value, str) or '\\' in value:
        raise ValueError('Template path must be a repository-relative POSIX path')
    path = PurePosixPath(value)
    if (path.is_absolute() or '..' in path.parts or ':' in value
            or len(path.parts) != 4 or path.parts[:2] != ('presets', 'previews')
            or path.name != 'index.html'):
        raise ValueError(f'Unsafe template path: {value!r}')
    resolved = (ROOT / value).resolve()
    if not resolved.is_relative_to((ROOT / 'presets' / 'previews').resolve()) or not resolved.is_file():
        raise ValueError(f'Template does not exist inside previews: {value!r}')
    return value


def load_presets() -> list[dict]:
    """Read and validate every template in stable display order; return fresh data."""
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'Cannot load website presets: {exc}') from exc
    if not isinstance(data, list) or len(data) < 6:
        raise ValueError('Website catalog must contain at least six presets')
    seen = set()
    required = ('name', 'summary', 'best_for', 'palette', 'typography', 'layout',
                'motion', 'imagery_prompt', 'generation_rules', 'sources', 'preview', 'template_source')
    for item in data:
        if not isinstance(item, dict) or any(not item.get(k) for k in required):
            raise ValueError('Preset is missing required design direction')
        identifier = item.get('id')
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-z][a-z0-9-]*', identifier):
            raise ValueError('Invalid website preset ID')
        if identifier in seen or identifier == 'custom':
            raise ValueError('Duplicate or reserved website preset ID')
        seen.add(identifier)
        if not isinstance(item['palette'], dict) or any(
            not isinstance(color, str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}', color)
            for color in item['palette'].values()
        ):
            raise ValueError(f'Invalid hex palette for {identifier}')
        if not isinstance(item['typography'], dict):
            raise ValueError(f'Invalid typography for {identifier}')
        for key in ('layout', 'generation_rules', 'best_for', 'sources'):
            if not isinstance(item[key], list) or not item[key]:
                raise ValueError(f'{identifier}: {key} must be a nonempty list')
        for source in item['sources']:
            if not isinstance(source, dict) or any(not isinstance(source.get(k), str) or not source[k].strip()
                                                   for k in ('title', 'url', 'observed')):
                raise ValueError(f'Invalid source for {identifier}')
            if not source['url'].startswith('https://'):
                raise ValueError(f'Source must use HTTPS for {identifier}')
        for key in ('preview', 'template_source'):
            _safe_template(item[key])
    return data


def get_preset(identifier: str) -> dict:
    """Return a fresh preset dict, or ValueError for an unknown/invalid ID."""
    if not isinstance(identifier, str) or not identifier:
        raise ValueError('Choose a valid website preset ID')
    for preset in load_presets():
        if preset['id'] == identifier:
            return preset
    raise ValueError(f'Unknown website preset: {identifier!r}')


def preset_brief(identifier: str) -> str:
    """Detailed additive Hermes direction, including actual HTML source location.

    The caller appends this to the user's brief. The caller/agent may read the
    source file for structure; the generated site remains a separate artifact.
    """
    p = get_preset(identifier)
    lines = [f"Website page-template direction: {p['name']} ({p['id']})",
             'This styles the generated WEBSITE, never the builder application.',
             'The user’s content and explicit style requests take priority over this preset.',
             'Use this as an additive starting point; do not replace the user’s brief.',
             f"Original runnable HTML template source: {p['template_source']}",
             f"Purpose: {p['summary']}",
             'Palette: ' + '; '.join(f'{k} {v}' for k, v in p['palette'].items()),
             'Typography: ' + '; '.join(f'{k}: {v}' for k, v in p['typography'].items()),
             'Layout:']
    lines.extend('- ' + rule for rule in p['layout'])
    lines.extend([f"Motion: {p['motion']}", 'Generation rules:'])
    lines.extend('- ' + rule for rule in p['generation_rules'])
    lines.extend(['ComfyUI image art direction (generate actual local assets when requested):',
                  p['imagery_prompt'],
                  'Demo SVG artwork is original sample art, not evidence of ComfyUI generation.',
                  'Replace fictional demo copy with supplied content; never invent endorsements, usage metrics, credentials, or working backend forms.',
                  'Deliver self-contained static HTML/CSS/JS and relative local assets; no CDN, build runtime, or Jekyll required. Include .nojekyll.',
                  'Keep semantic landmarks, visible keyboard focus, mobile reflow, descriptive image alt text, and reduced-motion support.'])
    return '\n'.join(lines)
