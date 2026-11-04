"""Bounded, read-only collector for a person's public GitHub / Hugging Face / Civitai projects.

Pure data in, pure data out: no persistence, no credentials, no model calls.
Network access goes through reference_web's pinned public-HTTP helpers, so
private/local addresses (including via redirects and DNS rebinding) are rejected.

collect() never raises for provider failures: it returns complete=False with
issues.  It raises RuntimeError('Cancelled by user.') when `cancel` is set,
matching reference_web.read_page.
"""
from __future__ import annotations

import html
import json
import re
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit, urlencode, parse_qsl
from urllib.request import Request, ProxyHandler, build_opener

from . import reference_web as _rw

PLATFORMS = ('github', 'huggingface', 'civitai')

TOOL = {
    'type': 'function',
    'function': {
        'name': 'collect_projects',
        'description': ('Enumerate ALL public projects of one account on one platform through its official public API '
                        '(GitHub repositories incl. forks/archived; Hugging Face models, datasets and spaces; Civitai '
                        'models with every version). Read-only, paginated, no credentials. The full verified catalog is '
                        'stored locally; you receive counts, profile data and examples. Call once per platform.'),
        'parameters': {
            'type': 'object',
            'properties': {
                'platform': {'type': 'string', 'enum': list(PLATFORMS)},
                'username': {'type': 'string', 'description': 'Exact public account name, e.g. marduk191.'},
            },
            'required': ['platform', 'username'],
            'additionalProperties': False,
        },
    },
}

MAX_BODY = 8 * 1024 * 1024
MAX_PAGES = 60          # per source
MAX_ENTRIES = 5000      # per catalog
MAX_REQUESTS = 150      # per catalog
DEADLINE_S = 180.0
TIMEOUT_S = 15
UA = 'Mozilla/5.0 (Gensite public project catalog; read-only)'

_API_HOSTS = {'github': 'api.github.com', 'huggingface': 'huggingface.co', 'civitai': 'civitai.com'}
_WEB_HOSTS = ('github.com', 'huggingface.co', 'civitai.com')
_NAME_RE = {
    'github': re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$'),
    'huggingface': re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$'),
    'civitai': re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'),
}
_REPO_ID = re.compile(r'^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)?$')
_LINK_NEXT = re.compile(r'<([^>]+)>\s*;[^,]*?rel="?next"?', re.I)


class _Fail(Exception):
    """A provider-level failure that makes the affected source incomplete."""


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise RuntimeError('Cancelled by user.')


# ---------------------------------------------------------------- HTTP

class _ApiRedirects(_rw.Redirects):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urlsplit(newurl)
        if parts.scheme != 'https' or (parts.hostname or '').lower() not in _API_HOSTS.values():
            raise ValueError('API redirected outside the expected public provider hosts.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def default_fetch(url, cancel=None):
    """GET url -> (status, lowercase-header dict, body bytes). Public addresses only."""
    _check_cancel(cancel)
    parts = urlsplit(url)
    if parts.scheme != 'https' or (parts.hostname or '').lower() not in _API_HOSTS.values():
        raise _Fail('Refusing non-provider URL.')
    request = Request(url, headers={'User-Agent': UA, 'Accept': 'application/json',
                                    'X-GitHub-Api-Version': '2022-11-28'})
    opener = build_opener(ProxyHandler({}), _ApiRedirects(()), _rw.PublicHTTP(()), _rw.PublicHTTPS(()))
    try:
        with opener.open(request, timeout=TIMEOUT_S) as response:
            status, headers = response.status, response.headers
            body = response.read(MAX_BODY + 1)
    except HTTPError as exc:
        status, headers = exc.code, exc.headers
        body = exc.read(65536)
    except (ValueError, OSError) as exc:  # URLError, socket errors, private-address rejections
        raise _Fail('Network request failed: %s' % _clip(exc, 160)) from exc
    if len(body) > MAX_BODY:
        raise _Fail('Response exceeded the %d byte limit.' % MAX_BODY)
    return status, {k.lower(): v for k, v in headers.items()}, body


class _Session:
    def __init__(self, fetch, cancel):
        self.fetch = fetch
        self.cancel = cancel
        self.requests = 0
        self.started = time.monotonic()

    def get_json(self, url):
        _check_cancel(self.cancel)
        if self.requests >= MAX_REQUESTS:
            raise _Fail('Request cap (%d) reached.' % MAX_REQUESTS)
        if time.monotonic() - self.started > DEADLINE_S:
            raise _Fail('Time limit (%ds) reached.' % DEADLINE_S)
        self.requests += 1
        try:
            status, headers, body = self.fetch(url, self.cancel)
        except _Fail:
            raise
        except RuntimeError:
            raise
        except Exception as exc:
            raise _Fail('Network request failed: %s' % _clip(exc, 160)) from exc
        _check_cancel(self.cancel)
        host = urlsplit(url).hostname
        if status in (429,) or (status == 403 and (headers.get('x-ratelimit-remaining') == '0' or 'retry-after' in headers)):
            raise _Fail('%s rate limited the request (HTTP %s).' % (host, status))
        if status in (401, 403):
            raise _Fail('%s refused the public request (HTTP %s; authentication or bot protection).' % (host, status))
        if status == 404:
            raise _Fail('%s returned not found (HTTP 404) for %s.' % (host, urlsplit(url).path))
        if status != 200:
            raise _Fail('%s returned HTTP %s.' % (host, status))
        try:
            return json.loads(body.decode('utf-8')), headers
        except (UnicodeDecodeError, ValueError) as exc:
            raise _Fail('%s returned invalid JSON.' % host) from exc


def _clip(value, limit=500):
    text = ' '.join(str(value).split()) if value is not None else ''
    return text if len(text) <= limit else text[:limit - 1] + '…'


def _s(value, limit=500):
    return _clip(value, limit) if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ''


def _int(value):
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _next_link(headers, expected_host, expected_path):
    """Return the validated rel=next URL or None.  Raises _Fail for off-provider links."""
    match = _LINK_NEXT.search(headers.get('link', ''))
    if not match:
        return None
    return _validate_next(match.group(1), expected_host, expected_path)


def _validate_next(url, host, path):
    parts = urlsplit(url)
    ok_path = bool(path.match(parts.path)) if hasattr(path, 'match') else parts.path == path
    if parts.scheme != 'https' or (parts.hostname or '').lower() != host or not ok_path:
        raise _Fail('Pagination link pointed outside the expected API endpoint.')
    return url


def _paginate(session, first_url, host, path, extract, label, state):
    """Generic cursor/link walker.  extract(json, headers)->(items, next_url|None, total|None)."""
    url, seen, pages = first_url, set(), 0
    while url:
        if url in seen:
            raise _Fail('%s pagination looped on a repeated cursor.' % label)
        if pages >= MAX_PAGES:
            raise _Fail('%s page cap (%d) reached before the final page.' % (label, MAX_PAGES))
        seen.add(url)
        data, headers = session.get_json(url)
        pages += 1
        items, nxt, total = extract(data, headers)
        if nxt:
            nxt = _validate_next(nxt, host, path)
        state['pages'][label] = pages
        if total is not None:
            state['totals'][label] = total
        yield items
        url = nxt


# ---------------------------------------------------------------- collectors

def _new_catalog(platform, username):
    web = {'github': 'https://github.com/%s', 'huggingface': 'https://huggingface.co/%s',
           'civitai': 'https://civitai.com/user/%s'}[platform]
    return {'platform': platform, 'username': username, 'complete': False, 'entries': [], 'profile': {},
            'profile_url': web % quote(username, safe=''), 'sources': [], 'issues': [], 'counts': {}}


class _Collector:
    def __init__(self, platform, username, session):
        self.catalog = _new_catalog(platform, username)
        self.session = session
        self.state = {'pages': {}, 'totals': {}}
        self.seen = {}
        self.raw = 0
        self.ok = True
        self.truncated = False

    def issue(self, text):
        self.ok = False
        self.catalog['issues'].append(text)

    def add(self, key, entry):
        self.raw += 1
        if key in self.seen:
            return
        if len(self.catalog['entries']) >= MAX_ENTRIES:
            if not self.truncated:
                self.truncated = True
                self.issue('Entry cap (%d) reached; remaining records were not collected.' % MAX_ENTRIES)
            return
        self.seen[key] = True
        self.catalog['entries'].append(entry)

    def run_source(self, label, url, host, path, extract, ingest, total_check=True):
        """Walk one paginated source; any failure marks the whole collection incomplete."""
        self.catalog['sources'].append(url)
        before_raw, before_unique = self.raw, len(self.seen)
        try:
            for items in _paginate(self.session, url, host, path, extract, label, self.state):
                for item in items:
                    _check_cancel(self.session.cancel)
                    ingest(item)
        except _Fail as exc:
            self.issue('%s: %s' % (label, exc))
            return False
        total = self.state['totals'].get(label)
        if total_check and total is not None:
            unique = len(self.seen) - before_unique
            if unique != total:
                self.issue('%s: provider reported %d items but %d unique records were collected.' % (label, total, unique))
                return False
        return True

    def finish(self):
        cat = self.catalog
        counts = {'entries': len(cat['entries']), 'raw_records': self.raw,
                  'duplicates_removed': self.raw - len(self.seen) if not self.truncated else None,
                  'requests': self.session.requests, 'pages': dict(self.state['pages']), 'by_kind': {}}
        for entry in cat['entries']:
            counts['by_kind'][entry['kind']] = counts['by_kind'].get(entry['kind'], 0) + 1
        if cat['platform'] == 'civitai':
            counts['versions'] = sum(len(e.get('versions', [])) for e in cat['entries'])
        if self.state['totals']:
            counts['reported_totals'] = dict(self.state['totals'])
        if counts['duplicates_removed'] is None:
            counts['duplicates_removed'] = 0
        cat['counts'] = counts
        cat['complete'] = bool(self.ok)
        return cat


def _github(c):
    user = quote(c.catalog['username'], safe='')
    profile_url = 'https://api.github.com/users/%s' % user
    # GitHub rewrites rel=next to /user/{numeric id}/repos for large accounts.
    repos_path = re.compile(r'^/users?/(?:%s|\d+)/repos$' % re.escape(user), re.I)
    c.catalog['sources'].append(profile_url)
    expected = None
    try:
        data, _ = c.session.get_json(profile_url)
        if not isinstance(data, dict) or not isinstance(data.get('login'), str):
            raise _Fail('GitHub profile response had an unexpected shape.')
        if data['login'].lower() != c.catalog['username'].lower():
            raise _Fail('GitHub profile login did not match the requested account.')
        c.catalog['profile'] = {k: _s(data.get(k), 400) for k in
                                ('login', 'name', 'company', 'blog', 'location', 'bio', 'created_at', 'html_url', 'type')}
        c.catalog['profile']['id'] = _int(data.get('id'))
        for k in ('public_repos', 'followers', 'following'):
            c.catalog['profile'][k] = _int(data.get(k))
        expected = _int(data.get('public_repos'))
        if expected is None:
            raise _Fail('GitHub profile did not report public_repos, so the repository total cannot be verified.')
    except _Fail as exc:
        c.issue('github profile: %s' % exc)

    def extract(data, headers):
        if not isinstance(data, list):
            raise _Fail('GitHub repository page was not a JSON list.')
        nxt = _next_link(headers, 'api.github.com', repos_path)
        return data, nxt, None

    def ingest(item):
        rid = item.get('id') if isinstance(item, dict) else None
        full = item.get('full_name') if isinstance(item, dict) else None
        if _int(rid) is None or not isinstance(full, str) or not _REPO_ID.match(full) or '/' not in full:
            c.issue('github repos: skipped a record with missing/invalid id or full_name.')
            return
        c.add(('repo', rid), {
            'platform': 'github', 'kind': 'repository', 'id': rid, 'name': _s(item.get('name'), 200),
            'full_name': full, 'url': 'https://github.com/' + full, 'description': _s(item.get('description')),
            'fork': bool(item.get('fork')), 'archived': bool(item.get('archived')),
            'language': _s(item.get('language'), 80), 'stars': _int(item.get('stargazers_count')),
            'forks': _int(item.get('forks_count')), 'topics': [_s(t, 60) for t in (item.get('topics') or [])[:20]
                                                              if isinstance(t, str)],
            'homepage': _s(item.get('homepage'), 300), 'created_at': _s(item.get('created_at'), 40),
            'updated_at': _s(item.get('updated_at'), 40), 'pushed_at': _s(item.get('pushed_at'), 40)})

    query = urlencode({'per_page': 100, 'type': 'owner', 'sort': 'created', 'direction': 'asc'})
    path = '/users/%s/repos' % user
    c.run_source('github repos', 'https://api.github.com%s?%s' % (path, query), 'api.github.com', repos_path, extract, ingest)
    if expected is not None and len(c.seen) != expected and c.ok:
        c.issue('github repos: profile reports %d public repositories but %d unique records were collected.'
                % (expected, len(c.seen)))


def _huggingface(c):
    user = c.catalog['username']
    c.catalog['profile'] = {'username': user}
    for kind, seg in (('model', 'models'), ('dataset', 'datasets'), ('space', 'spaces')):
        path = '/api/' + seg
        label = 'huggingface ' + seg

        def extract(data, headers, _p=path):
            if not isinstance(data, list):
                raise _Fail('Hugging Face page was not a JSON list.')
            nxt = _next_link(headers, 'huggingface.co', _p)
            total = headers.get('x-total-count')
            return data, nxt, int(total) if total and total.isdigit() else None

        def ingest(item, _k=kind, _s_=seg):
            rid = item.get('id') if isinstance(item, dict) else None
            if not isinstance(rid, str) or not _REPO_ID.match(rid):
                c.issue('%s: skipped a record with missing/invalid id.' % label)
                return
            prefix = {'model': '', 'dataset': 'datasets/', 'space': 'spaces/'}[_k]
            entry = {'platform': 'huggingface', 'kind': _k, 'id': rid, 'source_id': _s(item.get('_id'), 80),
                     'name': rid.split('/')[-1], 'url': 'https://huggingface.co/%s%s' % (prefix, quote(rid, safe='/')),
                     'description': _s(item.get('description')), 'likes': _int(item.get('likes')),
                     'downloads': _int(item.get('downloads')),
                     'tags': [_s(t, 60) for t in (item.get('tags') or [])[:20] if isinstance(t, str)],
                     'created_at': _s(item.get('createdAt'), 40), 'last_modified': _s(item.get('lastModified'), 40)}
            if _k == 'space':
                entry['sdk'] = _s(item.get('sdk'), 40)
            c.add((_k, entry['source_id'] or rid), entry)

        query = urlencode({'author': user, 'limit': 100})
        c.run_source(label, 'https://huggingface.co%s?%s' % (path, query), 'huggingface.co', path, extract, ingest)


def _civitai(c):
    user = c.catalog['username']
    path = '/api/v1/models'

    def extract(data, headers):
        if not isinstance(data, dict) or not isinstance(data.get('items'), list):
            raise _Fail('Civitai page had an unexpected shape.')
        meta = data.get('metadata') if isinstance(data.get('metadata'), dict) else {}
        nxt = meta.get('nextPage') if isinstance(meta.get('nextPage'), str) else None
        return data['items'], nxt, _int(meta.get('totalItems'))

    def ingest(item):
        mid = item.get('id') if isinstance(item, dict) else None
        if _int(mid) is None:
            c.issue('civitai models: skipped a record with missing/invalid id.')
            return
        creator = item.get('creator') if isinstance(item.get('creator'), dict) else {}
        if isinstance(creator.get('username'), str) and creator['username'].lower() != user.lower():
            c.issue('civitai models: model %s belongs to a different creator and was excluded.' % mid)
            return
        if creator.get('username') and 'username' not in c.catalog['profile']:
            c.catalog['profile'] = {'username': _s(creator['username'], 100)}
        base = 'https://civitai.com/models/%d' % mid
        versions, vseen = [], set()
        for v in item.get('modelVersions') or []:
            vid = v.get('id') if isinstance(v, dict) else None
            if _int(vid) is None or vid in vseen:
                continue
            vseen.add(vid)
            versions.append({'id': vid, 'name': _s(v.get('name'), 200), 'url': '%s?modelVersionId=%d' % (base, vid),
                             'base_model': _s(v.get('baseModel'), 80), 'published_at': _s(v.get('publishedAt'), 40),
                             'availability': _s(v.get('availability'), 40)})
        stats = item.get('stats') if isinstance(item.get('stats'), dict) else {}
        c.add(('model', mid), {
            'platform': 'civitai', 'kind': 'model', 'id': mid, 'name': _s(item.get('name'), 200), 'url': base,
            'model_type': _s(item.get('type'), 60), 'description': _s(re.sub(r'<[^>]*>', ' ', str(item.get('description') or ''))),
            'nsfw': bool(item.get('nsfw')), 'tags': [_s(t, 60) for t in (item.get('tags') or [])[:20] if isinstance(t, str)],
            'downloads': _int(stats.get('downloadCount')), 'likes': _int(stats.get('thumbsUpCount')),
            'versions': versions})

    query = urlencode({'username': user, 'nsfw': 'true', 'limit': 50})
    c.run_source('civitai models', 'https://civitai.com%s?%s' % (path, query), 'civitai.com', path, extract, ingest)


_COLLECTORS = {'github': _github, 'huggingface': _huggingface, 'civitai': _civitai}


def collect(platform, username, cancel=None, fetch=None):
    """Collect one platform's public catalog. `fetch(url, cancel)->(status, headers, body)` is injectable for tests."""
    if platform not in _COLLECTORS:
        raise ValueError('platform must be one of: %s' % ', '.join(PLATFORMS))
    if not isinstance(username, str) or not _NAME_RE[platform].match(username):
        raise ValueError('username is not a valid %s account name.' % platform)
    _check_cancel(cancel)
    collector = _Collector(platform, username, _Session(fetch or default_fetch, cancel))
    _COLLECTORS[platform](collector)
    return collector.finish()


def collect_projects(arguments, cancel=None, fetch=None):
    """Tool entry point: validates exactly {platform, username}."""
    if not isinstance(arguments, dict) or set(arguments) != {'platform', 'username'}:
        raise ValueError('collect_projects takes exactly platform and username.')
    return collect(arguments['platform'], arguments['username'], cancel, fetch)


# ---------------------------------------------------------------- rendering

_CSS = (
    '.gs-catalog{margin:2rem 0;font:inherit;color:inherit}'
    '.gs-catalog-head{display:flex;flex-wrap:wrap;gap:.5rem 1rem;align-items:baseline}'
    '.gs-catalog-status{padding:.15rem .6rem;border:1px solid currentColor;border-radius:999px;font-size:.8em}'
    '.gs-catalog-counts,.gs-catalog-issues{margin:.5rem 0;padding-left:1.2rem}'
    '.gs-catalog-list{list-style:none;margin:1rem 0;padding:0;display:grid;gap:1rem;'
    'grid-template-columns:repeat(auto-fill,minmax(min(100%,17rem),1fr))}'
    '.gs-catalog-item{border:1px solid rgba(128,128,128,.4);border-radius:.6rem;padding:1rem;overflow-wrap:anywhere}'
    '.gs-catalog-item h3{margin:.1rem 0 .4rem;font-size:1.05em}.gs-catalog-kind{font-size:.75em;opacity:.7;text-transform:uppercase}'
    '.gs-catalog-meta,.gs-catalog-versions{margin:.4rem 0 0;padding-left:1.1rem;font-size:.9em}'
    '.gs-catalog a{color:inherit}'
)


def _e(value):
    return html.escape('' if value is None else str(value), quote=True)


def _safe_url(url):
    try:
        parts = urlsplit(url)
    except (ValueError, TypeError):
        return None
    if parts.scheme != 'https' or parts.username or parts.password or (parts.hostname or '').lower() not in _WEB_HOSTS:
        return None
    return url


def _link(url, text):
    safe = _safe_url(url)
    if not safe:
        return _e(text)
    return '<a href="%s" rel="noopener noreferrer">%s</a>' % (_e(safe), _e(text))


def render_catalog(catalog):
    """Static, script-free, resource-free HTML section listing every entry and Civitai version."""
    entries = [e for e in catalog.get('entries', []) if isinstance(e, dict)]
    platform = _e(catalog.get('platform'))
    name = {'github': 'GitHub', 'huggingface': 'Hugging Face', 'civitai': 'Civitai'}.get(catalog.get('platform'), platform)
    if catalog.get('complete') is True:
        status, label = 'complete', 'Complete'
    elif entries:
        status, label = 'partial', 'Partial'
    else:
        status, label = 'unavailable', 'Unavailable'
    kinds = {}
    versions = 0
    for entry in entries:
        kinds[entry.get('kind', 'item')] = kinds.get(entry.get('kind', 'item'), 0) + 1
        versions += len(entry.get('versions') or [])
    out = ['<section class="gs-catalog gs-catalog-%s gs-catalog-%s" data-status="%s" data-count="%d">'
           % (status, platform, status, len(entries)), '<style>%s</style>' % _CSS,
           '<div class="gs-catalog-head"><h2>%s projects for %s</h2><span class="gs-catalog-status">%s</span> %s</div>'
           % (_e(name), _e(catalog.get('username')), label, _link(catalog.get('profile_url'), 'Profile'))]
    out.append('<ul class="gs-catalog-counts"><li>Total records: %d</li>' % len(entries))
    for kind in sorted(kinds):
        out.append('<li>%s: %d</li>' % (_e(kind), kinds[kind]))
    if catalog.get('platform') == 'civitai':
        out.append('<li>Versions/releases: %d</li>' % versions)
    out.append('</ul>')
    if status != 'complete':
        out.append('<p class="gs-catalog-note">This list is %s; it may not include every public project.</p>' % status)
    issues = [i for i in catalog.get('issues', []) if isinstance(i, str)]
    if issues:
        out.append('<ul class="gs-catalog-issues">%s</ul>' % ''.join('<li>%s</li>' % _e(i) for i in issues))
    out.append('<ul class="gs-catalog-list">')
    for entry in entries:
        out.append('<li class="gs-catalog-item gs-catalog-%s"><span class="gs-catalog-kind">%s</span><h3>%s</h3>'
                   % (re.sub(r'[^a-z0-9-]', '', str(entry.get('kind', 'item')).lower()) or 'item',
                      _e(entry.get('kind')), _link(entry.get('url'), entry.get('full_name') or entry.get('id') or entry.get('name'))))
        if entry.get('description'):
            out.append('<p>%s</p>' % _e(entry['description']))
        meta = []
        for key, text in (('language', 'Language'), ('stars', 'Stars'), ('forks', 'Forks'), ('likes', 'Likes'),
                          ('downloads', 'Downloads'), ('model_type', 'Type'), ('sdk', 'SDK')):
            if entry.get(key) not in (None, ''):
                meta.append('<li>%s: %s</li>' % (text, _e(entry[key])))
        for key, text in (('fork', 'Fork'), ('archived', 'Archived')):
            if entry.get(key):
                meta.append('<li>%s</li>' % text)
        if meta:
            out.append('<ul class="gs-catalog-meta">%s</ul>' % ''.join(meta))
        if entry.get('versions'):
            out.append('<ul class="gs-catalog-versions">%s</ul>' % ''.join(
                '<li>%s</li>' % _link(v.get('url'), v.get('name') or v.get('id')) for v in entry['versions'] if isinstance(v, dict)))
        out.append('</li>')
    out.append('</ul></section>')
    return '\n'.join(out)
