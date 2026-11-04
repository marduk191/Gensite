"""Loopback, read-only static Pages preview. No application API or rewriting.

Only URL semantics are modeled, not GitHub's infrastructure or build pipeline.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import mimetypes
import re
import threading
from urllib.parse import unquote, urlsplit, quote


class SiteServer:
    def __init__(self, root, repository='preview-repo'):
        self.root = Path(root).resolve()
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', repository):
            raise ValueError('Use a repository name, not a URL.')
        self.repository = repository
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_HEAD(self):
                self.serve(False)

            def do_GET(self):
                self.serve(True)

            def serve(self, body):
                raw = urlsplit(self.path).path
                decoded = unquote(raw)
                prefix = '/'+owner.repository
                if decoded == prefix:
                    self.send_response(301)
                    self.send_header('Location', prefix+'/')
                    self.end_headers()
                    return
                if not decoded.startswith(prefix+'/'):
                    self.send_error(404)
                    return
                relative = decoded[len(prefix)+1:]
                if '\\' in relative or '\x00' in relative or any(p in ('.', '..') or p.startswith('.') for p in relative.split('/') if p):
                    self.send_error(404)
                    return
                target = owner.root
                try:
                    for part in relative.split('/'):
                        if not part:
                            continue
                        # Explicit comparison: Windows resolve/is_file are case insensitive.
                        if part not in {p.name for p in target.iterdir()}:
                            raise FileNotFoundError
                        target = target/part
                        if target.is_symlink() or target.is_junction():
                            raise FileNotFoundError
                    if not target.resolve().is_relative_to(owner.root):
                        raise FileNotFoundError
                    if target.is_dir():
                        if not raw.endswith('/'):
                            self.send_response(301)
                            self.send_header('Location', raw+'/')
                            self.end_headers()
                            return
                        if 'index.html' not in {p.name for p in target.iterdir()}:
                            raise FileNotFoundError
                        target = target/'index.html'
                    if not target.is_file():
                        raise FileNotFoundError
                    content = target.read_bytes()
                except (OSError, ValueError):
                    self.send_error(404)
                    return
                self.send_response(200)
                mime = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
                if target.suffix.lower() in {'.js', '.mjs'}:
                    mime = 'text/javascript'
                self.send_header('Content-Type', mime + ('; charset=utf-8' if mime.startswith('text/') else ''))
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                if body:
                    try:
                        self.wfile.write(content)
                    except (ConnectionError, OSError):
                        pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.url = self.origin+'/'+quote(repository)+'/'
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval':.2}, daemon=True, name='Gensite static preview')
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
