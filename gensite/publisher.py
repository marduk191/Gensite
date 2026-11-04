"""Confirmed, branch-isolated GitHub Pages publishing using existing gh auth.

Only static allowlisted files leave the selected site. No app repository is used.
"""
from __future__ import annotations

import base64
from html.parser import HTMLParser
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import threading
import time
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen

BRANCH = 'gensite-pages'


def normalize_repository(text: str) -> str:
    """UI convenience: https://github.com/owner/repo(.git)(/) or github.com/owner/repo -> owner/repo.

    Publisher.publish stays strict and still rejects URLs; only the dialog normalizes what a user pastes.
    """
    value = str(text).strip()
    match = re.fullmatch(r'(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?', value, re.I)
    return match.group(1) + '/' + match.group(2) if match else value
MAX_FILE_BYTES = 100 * 1024 * 1024
STATIC_EXTENSIONS = {'.html', '.htm', '.css', '.js', '.mjs', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.avif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.otf', '.mp4', '.webm', '.mp3', '.wav', '.pdf', '.webmanifest'}
BLOCKED_NAMES = {'bridge.js', 'app.py', 'engine.py', 'publisher.py', 'settings.json', 'server.json', 'manifest.json', 'job.log', 'hermes.log'}
SENSITIVE_STEMS = {'credentials', 'credential', 'secrets', 'secret', 'settings', 'server', 'token', 'tokens', 'private-key', 'id_rsa', 'id_ed25519'}
SECRET_PATTERN = re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bAKIA[A-Z0-9]{16}\b)')


class _HTMLRefs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        for key in ('src', 'href', 'poster', 'action', 'data'):
            if attrs.get(key):
                self.refs.append(attrs[key])
        if attrs.get('srcset') and not attrs['srcset'].startswith('data:'):
            self.refs.extend(x.strip().split()[0] for x in attrs['srcset'].split(',') if x.strip())
        if tag == 'base':
            self.refs.append('/__base_not_supported__')


def _safe_path(name):
    parts = PurePosixPath(name).parts
    return bool(name and not name.startswith('/') and '\\' not in name and ':' not in name and all(p not in ('.', '..') and not p.startswith('.') for p in parts) and '%' not in name)


def validate_site(site: Path) -> dict:
    """Return {valid, errors, warnings, files}; never executes code or needs prompts.

    files is a relative POSIX allowlist; manifest generation metadata is omitted.
    External HTTP(S) links are allowed with a warning; local assets must exist.
    """
    errors, warnings, files = [], [], []
    site = Path(site)
    if site.is_symlink() or not site.is_dir():
        return dict(valid=False, errors=['Choose a static site folder (not a symlink).'], warnings=[], files=[])
    root = site.resolve()
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if path.is_symlink() or path.is_junction():
            errors.append(f'Symlink/junction is not allowed: {name}')
            continue
        if not path.is_file():
            continue
        if not _safe_path(name) or any(p.lower() in BLOCKED_NAMES or Path(p).stem.lower() in SENSITIVE_STEMS for p in path.relative_to(root).parts) or path.suffix.lower() not in STATIC_EXTENSIONS:
            if name != '.nojekyll':
                warnings.append(f'Not published: {name}')
            continue
        if path.stat().st_size > MAX_FILE_BYTES:
            errors.append(f'File exceeds 100 MiB: {name}')
            continue
        files.append(name)
    if 'index.html' not in files:
        errors.append('The site needs a root index.html.')
    allowed = set(files)
    for name in files:
        path = root/name
        if path.suffix.lower() not in {'.html', '.htm', '.css', '.js', '.mjs', '.svg', '.webmanifest'}:
            continue
        try:
            text = path.read_text(encoding='utf-8-sig')
        except (OSError, UnicodeError):
            errors.append(f'Cannot read UTF-8 static source: {name}')
            continue
        if any(marker in text for marker in ('data-gensite-bridge', '__BRIDGE_TOKEN__', 'data-gensite-selected')):
            errors.append(f'Editor bridge must be removed: {name}')
        if SECRET_PATTERN.search(text):
            errors.append(f'Possible embedded credential in static source: {name}; remove it before publishing.')
        refs = []
        if path.suffix.lower() in {'.html', '.htm', '.svg'}:
            parser = _HTMLRefs()
            parser.feed(text)
            refs.extend(parser.refs)
        refs.extend(re.findall(r'url\(\s*[\"\']?([^\s\)\"\']+)', text, re.I))
        refs.extend(re.findall(r'@import\s+[\"\']([^\"\']+)', text, re.I))
        for ref in refs:
            try:
                parsed = urlsplit(ref.strip())
            except ValueError:
                errors.append(f'Malformed URL in {name}.')
                continue
            if parsed.scheme in {'https', 'http'} or parsed.netloc:
                warnings.append(f'External dependency/link in {name}: review before publishing.')
                continue
            if parsed.scheme in {'mailto', 'tel', 'data'}:
                continue
            target = unquote(parsed.path)
            if not target and not parsed.scheme:
                continue
            if parsed.scheme or not _safe_path(target):
                errors.append(f'Unsafe/root-relative reference in {name}: {ref}')
                continue
            resolved = (path.parent/target).resolve()
            if not resolved.is_relative_to(root) or resolved.relative_to(root).as_posix() not in allowed:
                errors.append(f'Missing or excluded local reference in {name}: {ref}')
    manifest = root/'manifest.json'
    if manifest.is_file() and not manifest.is_symlink():
        try:
            metadata = json.loads(manifest.read_text(encoding='utf-8-sig'))
            for entry in metadata.get('pages', []) + metadata.get('images', []):
                name = entry['filename']
                if not isinstance(name, str) or not _safe_path(name) or name not in allowed:
                    errors.append('Manifest references a missing or unsafe static file.')
        except (ValueError, TypeError, KeyError, AttributeError):
            errors.append('Invalid site manifest metadata.')
    return dict(valid=not errors, errors=list(dict.fromkeys(errors)), warnings=list(dict.fromkeys(warnings)), files=files)


class CommandError(RuntimeError):
    """Safe command failure; intentionally never retains credential-bearing output."""
    def __init__(self, command, code=None):
        self.code = code
        super().__init__(f'{command} failed' + (f' (HTTP {code})' if code else '') + '. Check gh auth login, repository permissions, and network connectivity; no force/retry was attempted.')


class Publisher:
    poll_timeout = 90.0
    poll_interval = 3.0
    command_timeout = 120.0

    def __init__(self, log, cancel: threading.Event):
        self.log = log
        self.cancel = cancel
        self._lock = threading.Lock()

    def _cancelled(self):
        if self.cancel.is_set():
            raise RuntimeError('Cancelled. Any remote push already completed may continue deploying.')

    def _run(self, argv, cwd=None, **kwargs):
        self._cancelled()
        env = {k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
        env.update(GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never', GH_PROMPT_DISABLED='1', GH_HOST='github.com', GH_DEBUG='', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        try:
            proc = subprocess.Popen([str(a) for a in argv], cwd=cwd, env=env, shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except OSError:
            raise RuntimeError(f'{Path(argv[0]).stem} could not start. Install Git and GitHub CLI and restart Gensite.') from None
        deadline = time.monotonic() + self.command_timeout
        try:
            while True:
                try:
                    out, err = proc.communicate(timeout=.1)
                    break
                except subprocess.TimeoutExpired:
                    self._cancelled()
                    if time.monotonic() >= deadline:
                        raise RuntimeError('Publishing command timed out; check connectivity before retrying.')
        except BaseException:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
            elif proc.poll() is None:
                proc.kill()
            if proc.poll() is None:
                proc.kill()
            proc.communicate()
            raise
        if proc.returncode:
            match = re.search(r'HTTP (\d{3})', err)
            raise CommandError(Path(argv[0]).stem, int(match[1]) if match else None)
        return out

    def _api(self, endpoint, method='GET', fields=()):
        argv = ['gh', 'api', endpoint, '--hostname', 'github.com', '--method', method]
        for field in fields:
            argv.extend(['--raw-field', field])
        return json.loads(self._run(argv) or '{}')

    def status(self):
        result = dict(git=bool(shutil.which('git')), gh=bool(shutil.which('gh')), authenticated=False, account=None, diagnostics=[])
        if not result['git']:
            result['diagnostics'].append('Install Git and restart Gensite.')
        if not result['gh']:
            result['diagnostics'].append('Install GitHub CLI (gh) and restart Gensite.')
            return result
        try:
            self._run(['gh', 'auth', 'status', '--hostname', 'github.com'])
            user = self._api('user')
            result.update(authenticated=True, account=user['login'])
        except (RuntimeError, ValueError, KeyError):
            self._cancelled()
            result['diagnostics'].append('Run gh auth login --hostname github.com, then retry.')
        return result

    def _http_matches(self, url, expected, commit):
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            return False
        request = Request(url + ('&' if '?' in url else '?') + 'gensite_commit=' + commit, headers={'Cache-Control':'no-cache', 'User-Agent':'Gensite-Publisher'})
        try:
            with urlopen(request, timeout=10) as response:
                return response.status == 200 and response.read(len(expected)+1) == expected
        except (OSError, ValueError):
            return False

    def publish(self, site: Path, repository: str, create: bool = False, confirm: bool = False, initialize_empty: bool = False) -> dict:
        if confirm is not True:
            raise ValueError('Confirm that the selected site and repository may become public.')
        if not isinstance(repository, str) or not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', repository) or repository.endswith('.git') or repository.split('/')[1] in {'.', '..'}:
            raise ValueError('Repository must be an exact GitHub owner/name, not a URL.')
        validation = validate_site(site)
        if not validation['valid']:
            raise ValueError('Static site preflight failed: ' + '; '.join(validation['errors']))
        if not self._lock.acquire(blocking=False):
            raise RuntimeError('Publishing is already running on this publisher.')
        try:
            return self._publish(Path(site).resolve(), repository, create, validation, initialize_empty)
        finally:
            self._lock.release()

    def _publish(self, site, repository, create, validation, initialize_empty=False):
        self._cancelled()
        readiness = self.status()
        if not readiness['git'] or not readiness['gh'] or not readiness['authenticated']:
            raise RuntimeError(' '.join(readiness['diagnostics']))
        endpoint = 'repos/' + repository
        try:
            repo = self._api(endpoint)
        except CommandError as exc:
            if exc.code != 404:
                raise
            if create is not True:
                raise RuntimeError('Repository not found or inaccessible. Select create explicitly only for a new public repository.') from None
            self.log('Creating the confirmed public repository.')
            self._run(['gh', 'repo', 'create', repository, '--public', '--add-readme'])
            repo = self._api(endpoint)
        if repo.get('full_name', '').lower() != repository.lower():
            raise RuntimeError('Repository readback does not match the confirmed target.')
        if repo.get('default_branch') == BRANCH:
            raise RuntimeError('gensite-pages is the default branch. Choose a repository with a separate default branch to preserve it.')
        if not repo.get('permissions', {}).get('push', False):
            raise RuntimeError('The signed-in account needs repository push and Pages administration permissions.')
        for warning in validation['warnings']:
            self.log(warning)
        # A fresh isolated directory per operation avoids stale state and shared worktrees.
        publishing = Path(__file__).resolve().parents[1]/'.publishing'
        publishing.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='publish-', dir=publishing) as directory:
            work = Path(directory)
            # All git config is operation-local, with global/system config disabled in _run.
            gh_path = shutil.which('gh') or 'gh'
            helper = '!"' + gh_path.replace('\\', '/') + '" auth git-credential'
            prefix = ['git', '-c', 'core.hooksPath=' + str(work/'disabled-hooks'), '-c', 'core.autocrlf=false', '-c', 'commit.gpgsign=false', '-c', 'credential.helper=', '-c', 'credential.helper='+helper]
            def git(*args):
                return self._run(prefix+list(args), cwd=work)
            git('init', '--initial-branch='+BRANCH)
            git('remote', 'add', 'origin', 'https://github.com/'+repository+'.git')
            default = repo.get('default_branch')
            if default and not git('ls-remote', '--heads', 'origin', 'refs/heads/'+default).strip() and not git('ls-remote', '--heads', 'origin').strip() and initialize_empty is True:
                # Explicitly approved: give a brand-new empty repository a default branch with a README
                # through the contents API (the same safe initialization --add-readme performs).
                self.log(f'The repository is empty. Adding a README to create its {default} branch (explicitly approved).')
                note = '# ' + repository.split('/')[1] + '\n\nPublished with Gensite.\n'
                self._api(endpoint + '/contents/README.md', 'PUT', ['message=Initialize repository', 'content=' + base64.b64encode(note.encode('utf-8')).decode('ascii'), 'branch=' + default])
            if not default or not git('ls-remote', '--heads', 'origin', 'refs/heads/'+default).strip():
                raise RuntimeError('This repository is empty (it has no branch yet). Tick "If the repository is empty, add a README first" and publish again, or choose a repository that already has a branch.')
            remote_ref = 'refs/heads/'+BRANCH
            refs = git('ls-remote', '--heads', 'origin', remote_ref).strip()
            old_files = set()
            if refs:
                self.log('Fetching existing gensite-pages tip; default branch is untouched.')
                git('fetch', '--no-tags', 'origin', remote_ref)
                # Reject symlink/submodule entries before checkout, including existing unrelated files.
                tree = git('ls-tree', '-r', 'FETCH_HEAD')
                if any(line.startswith(('120000 ', '160000 ')) for line in tree.splitlines()):
                    raise RuntimeError('Publishing branch contains symlinks/submodules; refusing unsafe checkout.')
                git('checkout', '-B', BRANCH, 'FETCH_HEAD')
                marker = work/'.gensite-managed.json'
                if marker.is_file():
                    try:
                        data = json.loads(marker.read_text(encoding='utf-8'))
                        previous = data['files']
                        if data.get('generator') != 'Gensite' or not isinstance(previous,list) or not all(isinstance(n,str) and (n == '.nojekyll' or _safe_path(n)) and n not in {'.gensite-managed.json'} for n in previous):
                            raise ValueError
                        old_files = set(previous)
                    except (ValueError, KeyError, TypeError):
                        raise RuntimeError('Invalid publishing branch ownership metadata; refusing destructive changes.') from None
            new_files = set(validation['files']) | {'.nojekyll'}
            for name in new_files:
                dest = work/name
                if dest.exists() and name not in old_files and name != '.nojekyll':
                    raise RuntimeError('Publishing would overwrite an unmanaged branch file; select a different repository.')
            for name in old_files-new_files:
                path = work/name
                if path.is_file():
                    path.unlink()
            # Revalidate immediately before copying; refuse races to symlinks/changed structure.
            current = validate_site(site)
            if not current['valid'] or current['files'] != validation['files']:
                raise RuntimeError('Site changed during publishing. Retry after editing is complete.')
            for name in validation['files']:
                self._cancelled()
                src, dest = site/name, work/name
                if src.is_symlink() or not src.resolve().is_relative_to(site) or src.stat().st_size > MAX_FILE_BYTES:
                    raise RuntimeError('Unsafe source changed during publishing.')
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
            (work/'.nojekyll').write_bytes(b'')
            (work/'.gensite-managed.json').write_text(json.dumps({'generator':'Gensite','files':sorted(new_files)}, indent=2), encoding='utf-8')
            staged = sorted(new_files | old_files | {'.gensite-managed.json'})
            for offset in range(0,len(staged),100):
                git('add', '--all', '--', *staged[offset:offset+100])
            user = self._api('user')
            login = user['login']
            if not re.fullmatch(r'[A-Za-z0-9-]+', login) or not isinstance(user.get('id'),int):
                raise RuntimeError('Invalid authenticated account identity.')
            # An unchanged deployment does not need a new commit, but is still verified.
            changes = git('diff', '--cached', '--name-only').strip()
            if changes:
                git('-c', 'user.name='+login, '-c', 'user.email='+str(user['id'])+'+'+login+'@users.noreply.github.com', 'commit', '-m', 'Publish generated site with Gensite')
            commit = git('rev-parse', 'HEAD').strip()
            if not re.fullmatch(r'[0-9a-f]{40,64}',commit):
                raise RuntimeError('Could not verify local commit.')
            expected = (work/'index.html').read_bytes()
            self._cancelled()
            self.log('Pushing only gensite-pages (no force).')
            git('push', 'origin', 'HEAD:'+remote_ref)
            remote = git('ls-remote', '--heads', 'origin', remote_ref).split()
            if not remote or remote[0] != commit:
                raise RuntimeError('Remote branch readback did not match the generated commit.')
        try:
            self._api(endpoint+'/pages')
            method = 'PUT'
        except CommandError as exc:
            if exc.code != 404:
                raise
            method = 'POST'
        self._api(endpoint+'/pages', method, ['build_type=legacy','source[branch]='+BRANCH,'source[path]=/'])
        settings = self._api(endpoint+'/pages')
        if settings.get('source') != {'branch':BRANCH,'path':'/'} or settings.get('build_type','legacy') != 'legacy':
            raise RuntimeError('Pages settings readback mismatch; commit pushed but deployment is not verified.')
        url = settings.get('html_url')
        if not isinstance(url,str) or urlsplit(url).scheme != 'https':
            raise RuntimeError('Pages settings did not return an HTTPS deployment URL.')
        result = dict(repository=repository, url=url, commit=commit, status='deploying', diagnostics=[])
        self.log('Pages source settings verified; waiting for build and exact index HTTP verification.')
        deadline = time.monotonic()+self.poll_timeout
        while True:
            self._cancelled()
            build = {}
            try:
                build = self._api(endpoint+'/pages/builds/latest')
            except CommandError:
                result['diagnostics'] = ['Pages build status is not yet available.']
            if build.get('status') == 'built' and build.get('commit') == commit and self._http_matches(url,expected,commit):
                self._cancelled()
                result.update(status='published',diagnostics=['Pages build commit and exact generated index bytes verified over HTTP.'])
                self.log('Published: exact generated index verified over HTTP.')
                return result
            result['diagnostics'] = ['Commit pushed and Pages settings verified; build status: '+str(build.get('status','pending'))+'. Exact generated index is not yet verified.']
            if time.monotonic() >= deadline:
                self.log('Deploying: remote work may continue; live content is not yet verified.')
                return result
            self.cancel.wait(min(self.poll_interval,max(0,deadline-time.monotonic())))
