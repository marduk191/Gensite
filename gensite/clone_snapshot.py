"""Generic rendered-DOM/CSSOM static clone snapshot (prototype).

Pipeline (no model calls, no network, no site-specific adapters):

1. ``CAPTURE_STATIC_JS`` runs inside an already-rendered page (e.g. a QtWebEngine page at
   1440px and again at 390px).  It works on a *cloned* DOM, never mutates the original,
   and returns a JSON-serializable snapshot: cleaned ``body_html``, accessible CSSOM rules,
   html/body attributes, warnings for inaccessible stylesheets and metadata for every
   picture slot (``<img>``, large CSS photo backgrounds, large pictorial SVG, video posters).
2. ``build_static_html(snapshots, image_count)`` / ``build_static_report(...)`` turn one or
   two such snapshots (``{'desktop': snap, 'mobile': snap}``) into one complete static HTML
   document with inline CSS, real ``<img src="assets/image-N.png">`` slot nodes, no scripts,
   safe external links and namespaced ids when two different DOM states must be combined.

The Python side re-sanitizes everything, so a snapshot from an untrusted/older capture can
not smuggle scripts, forms, secrets or remote resources into the output.
"""
from __future__ import annotations

import ipaddress
import json
import re
from collections import Counter
from html import escape as _html_escape
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

__all__ = ['CAPTURE_STATIC_JS', 'CloneError', 'CloneIncomplete', 'build_static_html',
           'build_static_report', 'SNAPSHOT_VERSION']

SNAPSHOT_VERSION = 1
MIN_MAJOR_EDGE = 24          # visible slots at least this wide and tall count as picture slots
MAX_DATA_URL = 20000
SYSTEM_FONT_FALLBACK = 'system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif'


class CloneError(ValueError):
    """The snapshot can not honestly be turned into a static clone."""


class CloneIncomplete(CloneError):
    """Needed stylesheets were inaccessible; pass allow_partial=True to accept a partial clone."""


# --------------------------------------------------------------------------------------
# Browser-side capture
# --------------------------------------------------------------------------------------
CAPTURE_STATIC_JS = r"""(function () {
'use strict';
var D = document, W = window, warnings = [];
function warn(code, message, extra) { var w = {code: code, message: message}; if (extra) for (var k in extra) w[k] = extra[k]; warnings.push(w); }
var DROP = {script:1,noscript:1,iframe:1,frame:1,frameset:1,object:1,embed:1,applet:1,style:1,link:1,meta:1,base:1,title:1,template:1,audio:1,source:1,track:1,param:1,head:1};
var VOID = {area:1,base:1,br:1,col:1,embed:1,hr:1,img:1,input:1,link:1,meta:1,param:1,source:1,track:1,wbr:1,input:1,textarea:1,select:1,table:1,tr:1,td:1,th:1,tbody:1,thead:1,tfoot:1,colgroup:1,video:1,canvas:1,svg:1,button:1};
var SECRET_NAME = /(^|[-_:])(token|secret|password|passwd|pwd|csrf|xsrf|session|sess|auth|authorization|apikey|key|jwt|bearer|credential|cookie|nonce|signature|otp)([-_:]|$)/i;
var SECRET_VALUE = /^(eyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]*|Bearer\s+\S+|sk-[A-Za-z0-9]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|[A-Fa-f0-9]{40,})$/;
var LOGIN_FORM = /(log-?in|sign-?in|sign-?up|register|password|credential|auth)/i;
var stats = {elements: 0, removed: {}};
function removed(what) { stats.removed[what] = (stats.removed[what] || 0) + 1; }
function r2(n) { return Math.round(n * 100) / 100; }

function splitTop(s) { var out = [], d = 0, cur = ''; for (var i = 0; i < s.length; i++) { var ch = s[i]; if (ch === '(') d++; else if (ch === ')') d--; if (ch === ',' && d === 0) { out.push(cur); cur = ''; } else cur += ch; } if (cur.trim()) out.push(cur); return out; }

var root = D.documentElement, lb = D.body;
if (!lb) throw new Error('document has no body');
if (D.getElementsByTagName('*').length > 30000) throw new Error('reference exceeds the 30000 element capture limit');
var clone = root.cloneNode(true);
var cb = clone.querySelector('body');
var live = [], cl = [];
(function collect() {
  var stack = [[lb, cb]];
  while (stack.length) {
    var p = stack.pop(); live.push(p[0]); cl.push(p[1]);
    var lc = p[0].children, cc = p[1].children;
    if (lc.length !== cc.length) continue;
    for (var i = lc.length - 1; i >= 0; i--) stack.push([lc[i], cc[i]]);
  }
})();

var slots = [];
function geom(l) { var r = l.getBoundingClientRect(); return {x: Math.round(r.left + W.scrollX), y: Math.round(r.top + W.scrollY), width: r2(r.width), height: r2(r.height)}; }
function classify(l, cs, g) {
  var hint = (l.getAttribute('role') || '') + ' ' + (l.className && l.className.baseVal === undefined ? l.className : '') + ' ' + (l.getAttribute('alt') || '');
  var rad = parseFloat(cs.borderTopLeftRadius) || 0, pct = /%/.test(cs.borderTopLeftRadius) && rad >= 40;
  if (/avatar|profile-?pic/i.test(hint) || (g.width <= 220 && Math.abs(g.width - g.height) <= 2 && (pct || rad >= g.width * 0.45))) return 'avatar';
  if (g.width >= W.innerWidth * 0.6 && g.height > 0 && g.width / g.height >= 2.5) return 'banner';
  if (g.width >= W.innerWidth * 0.6) return 'hero';
  if (g.width < 48 && g.height < 48) return 'icon';
  return 'thumbnail';
}
function addSlot(l, cs, kind, extra) {
  var g = geom(l), info = {index: slots.length, kind: kind, tag: l.localName};
  for (var k in g) info[k] = g[k];
  info.visible = cs.display !== 'none' && cs.visibility !== 'hidden' && g.width > 0 && g.height > 0 && parseFloat(cs.opacity || '1') > 0;
  info.naturalWidth = l.naturalWidth || l.videoWidth || 0; info.naturalHeight = l.naturalHeight || l.videoHeight || 0;
  info.role = classify(l, cs, g);
  info.alt = (l.getAttribute('alt') || l.getAttribute('aria-label') || '').slice(0, 300);
  info.objectFit = cs.objectFit; info.objectPosition = cs.objectPosition; info.aspectRatio = cs.aspectRatio;
  info.borderRadius = cs.borderTopLeftRadius; info.inLink = !!l.closest('a');
  if (extra) for (var e in extra) info[e] = extra[e];
  slots.push(info); return info;
}
function scrubAttrs(c) {
  var names = Array.prototype.map.call(c.attributes, function (a) { return a.name; });
  names.forEach(function (n) {
    var v = c.getAttribute(n) || '';
    if (/^on/i.test(n) || n === 'srcdoc' || n === 'nonce' || n === 'integrity' || n === 'contenteditable' || SECRET_NAME.test(n) || (n !== 'class' && n !== 'style' && n !== 'href' && SECRET_VALUE.test(v))) c.removeAttribute(n);
  });
}
function applySlot(c, info) {
  Array.prototype.map.call(c.attributes, function (a) { return a.name; }).forEach(function (n) {
    if (/(^|-)src(set)?$/i.test(n) || n === 'sizes' || n === 'loading' || n === 'decoding' || n === 'fetchpriority' || n === 'crossorigin' || n === 'referrerpolicy' || n === 'poster') c.removeAttribute(n);
  });
  c.setAttribute('data-gs-slot', String(info.index)); c.setAttribute('data-gs-kind', info.kind);
}
function newSlotImg(l, c, info) {
  var im = D.createElement('img');
  ['id', 'class', 'style', 'title', 'role', 'aria-label', 'aria-hidden'].forEach(function (n) { if (c.hasAttribute(n)) im.setAttribute(n, c.getAttribute(n)); });
  im.setAttribute('alt', info.alt || ''); applySlot(im, info); c.replaceWith(im); return im;
}
var loginRemoved = 0;
for (var n = 0; n < live.length; n++) {
  var l = live[n], c = cl[n], tag = l.localName;
  if (c.getRootNode() !== clone) continue;               // inside an already removed subtree
  stats.elements++;
  if (DROP[tag] && c !== cb) { c.remove(); removed(tag); continue; }
  var cs = W.getComputedStyle(l);
  if (tag === 'form') {
    var sig = [l.id, l.className && l.className.baseVal === undefined ? l.className : '', l.getAttribute('action'), l.getAttribute('aria-label'), l.getAttribute('name')].join(' ');
    if (l.querySelector('input[type=password]') || LOGIN_FORM.test(sig)) { c.remove(); removed('credential_form'); continue; }
  }
  if (tag === 'input') {
    var t = (l.getAttribute('type') || 'text').toLowerCase();
    if (t === 'hidden' || t === 'password' || t === 'file') { c.remove(); removed('input_' + t); continue; }
    ['value', 'name', 'autocomplete'].forEach(function (a) { if (!(a === 'value' && /^(button|submit|reset)$/.test(t))) c.removeAttribute(a); });
    if (/^(checkbox|radio)$/.test(t) && l.checked) c.setAttribute('checked', ''); else c.removeAttribute('checked');
  }
  if (tag === 'textarea') c.textContent = '';
  if (l.ownerSVGElement) { scrubAttrs(c); continue; }   // children of an inline svg stay as they are
  scrubAttrs(c);
  if (tag === 'img') {
    var src = l.getAttribute('src') || '';
    var g0 = geom(l);
    if (/^data:image\/svg\+xml/i.test(src) && src.length <= 4000 && g0.width <= 64 && g0.height <= 64) continue;   // tiny UI icon
    if (g0.width > 0 && g0.width <= 2 && g0.height > 0 && g0.height <= 2) { c.remove(); removed('tracking_pixel'); continue; }
    var info = addSlot(l, cs, 'img'); applySlot(c, info); continue;
  }
  if (tag === 'video') {
    var gv = geom(l);
    if (gv.width >= 64 && gv.height >= 64 && cs.display !== 'none') newSlotImg(l, c, addSlot(l, cs, 'video-poster'));
    else { c.remove(); removed('video'); }
    continue;
  }
  if (tag === 'svg') {
    var gs = geom(l);
    if (gs.width >= 200 && gs.height >= 200 && cs.display !== 'none') { newSlotImg(l, c, addSlot(l, cs, 'svg')); }
    continue;
  }
  var bg = cs.backgroundImage;
  if (bg && bg !== 'none' && bg.indexOf('url(') >= 0 && l !== root && !(tag in {tr:1,td:1,th:1,table:1,tbody:1,thead:1,tfoot:1,colgroup:1,col:1,input:1,br:1,hr:1,textarea:1,select:1})) {
    var gb = geom(l);
    if (cs.display === 'none' || gb.width < 64 || gb.height < 64) continue;
    var repeating = cs.backgroundRepeat.indexOf('no-repeat') < 0 && !/cover|contain/.test(cs.backgroundSize);
    if (repeating) { warn('texture_background', 'repeating background texture left to CSS (remote url removed)', {tag: tag}); continue; }
    var layers = splitTop(bg), others = layers.map(function (x) { return /^\s*(url|image-set|-webkit-image-set)\(/i.test(x) ? 'none' : x.trim(); });
    var hasFx = others.some(function (x) { return x !== 'none'; });
    var info2 = addSlot(l, cs, 'background', {backgroundSize: cs.backgroundSize, backgroundPosition: cs.backgroundPosition});
    c.style.setProperty('background-image', 'none', 'important');
    if (cs.position === 'static') c.style.position = 'relative';
    c.style.isolation = 'isolate';
    var fit = /contain/.test(cs.backgroundSize) ? 'contain' : 'cover';
    var im = D.createElement('img');
    im.setAttribute('alt', ''); im.className = 'gs-bg-slot';
    im.setAttribute('style', 'position:absolute;left:0;top:0;width:100%;height:100%;max-width:none;z-index:-1;pointer-events:none;border-radius:inherit;object-fit:' + fit + ';object-position:' + cs.backgroundPosition);
    applySlot(im, info2); c.appendChild(im);
    if (hasFx) {
      var fx = D.createElement('span'); fx.className = 'gs-bg-fx';
      fx.setAttribute('style', 'position:absolute;left:0;top:0;width:100%;height:100%;z-index:-1;pointer-events:none;border-radius:inherit;background-image:' + others.join(',') + ';background-size:' + cs.backgroundSize + ';background-position:' + cs.backgroundPosition + ';background-repeat:' + cs.backgroundRepeat + ';background-origin:' + cs.backgroundOrigin + ';background-clip:' + cs.backgroundClip);
      c.appendChild(fx);
    }
  }
}

// ---- accessible CSSOM ------------------------------------------------------------
var styles = [], inaccessible = [], fontFamilies = {};
function addSheet(sheet, depth) {
  if (!sheet || sheet.disabled || depth > 8) return;
  var rules;
  try { rules = sheet.cssRules; } catch (e) { inaccessible.push({href: sheet.href || null, reason: String((e && e.name) || e), owner: sheet.ownerNode ? sheet.ownerNode.localName : null}); return; }
  var parts = [];
  for (var i = 0; i < rules.length; i++) {
    var r = rules[i];
    if (r.type === 3) {                                   // @import: follow what the browser already loaded
      if (r.styleSheet) addSheet(r.styleSheet, depth + 1); else inaccessible.push({href: r.href || null, reason: 'unloaded @import'});
      continue;
    }
    if (r.type === 5) { var fam = r.style.getPropertyValue('font-family'); if (fam) fontFamilies[fam.replace(/^["']|["']$/g, '')] = 1; }
    parts.push(r.cssText);
  }
  var media = sheet.media && sheet.media.mediaText ? sheet.media.mediaText : '';
  styles.push({href: sheet.href || null, media: media === 'all' ? '' : media, inline: !sheet.href, rule_count: rules.length, css: parts.join('\n')});
}
for (var s = 0; s < D.styleSheets.length; s++) addSheet(D.styleSheets[s], 0);
(D.adoptedStyleSheets || []).forEach(function (sh) { addSheet(sh, 0); });
if (!styles.length && !inaccessible.length) warn('no_stylesheets', 'page exposes no stylesheets');
inaccessible.forEach(function (x) { warn('inaccessible_stylesheet', 'stylesheet rules are not readable: ' + (x.href || '(inline)'), {href: x.href, reason: x.reason}); });
var shadow = 0; live.forEach(function (e) { if (e.shadowRoot) shadow++; });
if (shadow) warn('shadow_dom', shadow + ' open shadow roots are not captured');

function attrMap(el) { var o = {}; Array.prototype.forEach.call(el.attributes, function (a) { o[a.name] = a.value; }); return o; }
scrubAttrs(clone); scrubAttrs(cb);
var bcs = W.getComputedStyle(lb);
var out = {
  version: 1, kind: 'gensite-static-snapshot', url: W.location.href, base_url: D.baseURI, title: D.title || '', lang: root.getAttribute('lang') || '',
  viewport: {width: W.innerWidth, height: W.innerHeight, devicePixelRatio: W.devicePixelRatio},
  document: {scrollWidth: root.scrollWidth, scrollHeight: root.scrollHeight},
  html_attrs: attrMap(clone), body_attrs: attrMap(cb), body_html: cb.innerHTML,
  body_computed: {fontFamily: bcs.fontFamily, fontSize: bcs.fontSize, color: bcs.color, backgroundColor: bcs.backgroundColor},
  styles: styles, inaccessible_stylesheets: inaccessible, font_families: Object.keys(fontFamilies),
  slots: slots, warnings: warnings, stats: stats
};
if (out.body_html.length > 8000000) throw new Error('snapshot too large');
return out;
})()"""


# --------------------------------------------------------------------------------------
# HTML tree (tiny, lossless enough for browser-serialized markup)
# --------------------------------------------------------------------------------------
VOID_TAGS = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param',
             'source', 'track', 'wbr'}
DROP_TAGS = {'script', 'noscript', 'iframe', 'frame', 'frameset', 'object', 'embed', 'applet', 'style', 'link',
             'meta', 'base', 'title', 'template', 'audio', 'video', 'source', 'track', 'param', 'head',
             'foreignobject', 'image', 'area', 'map', 'portal'}
FORM_CONTROLS = {'input', 'select', 'textarea', 'button', 'form', 'output', 'fieldset'}
BUTTON_INPUT_TYPES = {'button', 'submit', 'reset'}
DROP_ATTRS = {'srcdoc', 'srcset', 'sizes', 'poster', 'action', 'formaction', 'formmethod', 'formtarget', 'enctype',
              'method', 'ping', 'nonce', 'integrity', 'crossorigin', 'referrerpolicy', 'autocomplete', 'contenteditable',
              'data', 'manifest', 'background', 'longdesc', 'cite', 'download', 'list', 'form', 'is', 'loading',
              'decoding', 'fetchpriority', 'accept', 'capture', 'dirname', 'imagesrcset', 'imagesizes'}
ARIA_REFS = {'aria-labelledby', 'aria-describedby', 'aria-controls', 'aria-owns', 'aria-activedescendant',
             'aria-details', 'aria-errormessage', 'aria-flowto'}
SECRET_NAME_RE = re.compile(r'(^|[-_:])(token|secret|password|passwd|pwd|csrf|xsrf|session|sess|auth|authorization|'
                            r'apikey|key|jwt|bearer|credential|cookie|nonce|signature|otp)([-_:]|$)', re.I)
SECRET_VALUE_RE = re.compile(r'^(eyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]*|Bearer\s+\S+|sk-[A-Za-z0-9]{16,}|'
                             r'gh[pousr]_[A-Za-z0-9]{20,}|xox[abprs]-[\w-]{10,}|AKIA[0-9A-Z]{16}|[A-Fa-f0-9]{40,})$')
SECRET_QUERY_RE = re.compile(r'(token|secret|password|passwd|csrf|xsrf|session|sid|auth|apikey|api_key|key|jwt|'
                             r'signature|sig|code|otp|credential|ticket)', re.I)
LOGIN_FORM_RE = re.compile(r'(log-?in|sign-?in|sign-?up|register|password|credential|auth)', re.I)
VALUE_SCAN_EXEMPT = {'class', 'style', 'href', 'id', 'for', 'd', 'points', 'viewbox', 'transform', 'alt', 'title'}
GENERIC_FONTS = {'serif', 'sans-serif', 'monospace', 'cursive', 'fantasy', 'system-ui', 'ui-serif', 'ui-sans-serif',
                 'ui-monospace', 'ui-rounded', 'math', 'emoji', 'fangsong', 'inherit', 'initial', 'unset', 'revert'}
FONT_CSS_HOST_HINTS = ('fonts.googleapis.com', 'fonts.bunny.net', 'use.typekit.net', 'fast.fonts.net', 'use.fontawesome.com',
                       'kit.fontawesome.com', 'fonts.gstatic.com')


class _Node:
    __slots__ = ('tag', 'attrs', 'children', 'text')

    def __init__(self, tag=None, attrs=None, text=None):
        self.tag = tag
        self.attrs = attrs or []
        self.children = []
        self.text = text


class _TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node('#root')
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, list(attrs))
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(_Node(tag, list(attrs)))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data):
        self.stack[-1].children.append(_Node(text=data))


def _parse_fragment(markup):
    builder = _TreeBuilder()
    builder.feed(markup)
    builder.close()
    return builder.root


def _esc_text(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('@import', '@&#8203;import')


def _esc_attr(value):
    return value.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;').replace('@import', '@&#8203;import')


def _serialize(node, out):
    if node.tag is None:
        out.append(_esc_text(node.text))
        return
    out.append('<' + node.tag)
    for name, value in node.attrs:
        out.append(' ' + name if value is None else f' {name}="{_esc_attr(value)}"')
    out.append('>')
    if node.tag in VOID_TAGS:
        return
    for child in node.children:
        _serialize(child, out)
    out.append(f'</{node.tag}>')


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


# --------------------------------------------------------------------------------------
# Scoping / URL policy
# --------------------------------------------------------------------------------------
class _Scope:
    def __init__(self, prefix, ids, page_url, base_url):
        self.prefix = prefix
        self.ids = ids
        self.page_url = _defrag(page_url or '')
        self.base_url = base_url or page_url or ''

    def pid(self, name):
        return self.prefix + name if self.prefix else name


def _defrag(url):
    return url.split('#', 1)[0]


def _private_host(host):
    host = (host or '').strip('[]').lower()
    if not host or host == 'localhost' or host.endswith('.localhost') or host.endswith('.local') or host.endswith('.internal'):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    except ValueError:
        return '.' not in host


def _clean_href(value, scope):
    """Return a safe replacement href or None (attribute removed)."""
    value = (value or '').strip()
    if not value or len(value) > 2000 or re.search(r'[\x00-\x1f]', value):
        return None
    if value.startswith('#'):
        frag = value[1:]
        return '#' + scope.pid(frag) if frag else '#'
    try:
        full = urljoin(scope.base_url, value)
        parts = urlsplit(full)
    except ValueError:
        return None
    if parts.scheme in ('mailto', 'tel'):
        return full if len(full) < 300 else None
    if parts.scheme not in ('http', 'https') or _private_host(parts.hostname):
        return None
    if scope.page_url and _defrag(full) == scope.page_url:
        return '#' + scope.pid(parts.fragment) if parts.fragment else '#'
    netloc = parts.hostname + (f':{parts.port}' if parts.port else '')
    if ':' in parts.hostname:
        netloc = f'[{parts.hostname}]' + (f':{parts.port}' if parts.port else '')
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not SECRET_QUERY_RE.search(k)])
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


URL_RE = re.compile(r'''url\(\s*(?:"([^"]*)"|'([^']*)'|([^)]*?))\s*\)''', re.I)


def _css_urls(text, scope, stats=None):
    def repl(match):
        arg = (match.group(1) or match.group(2) or match.group(3) or '').strip()
        if arg.startswith('#'):
            return 'url(#' + scope.pid(arg[1:]) + ')'
        low = arg.lower()
        if low.startswith('data:image/') and len(arg) <= MAX_DATA_URL and 'script' not in low:
            return match.group(0)
        if stats is not None:
            stats['css_urls_removed'] += 1
        return 'none'
    return URL_RE.sub(repl, text)


def _unescape_ident(ident):
    ident = re.sub(r'\\([0-9a-fA-F]{1,6})\s?', lambda m: chr(int(m.group(1), 16)), ident)
    return re.sub(r'\\(.)', r'\1', ident)


ID_SEL_RE = re.compile(r'#((?:\\[0-9a-fA-F]{1,6}\s?|\\.|[\w-]|[^\x00-\x7f])+)')
ATTR_ID_RE = re.compile(r'''\[\s*id\s*=\s*(["']?)([^\]"']*)\1\s*\]''')
QUOTED_RE = re.compile(r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')')


def _rewrite_selector(prelude, scope):
    if not scope.prefix:
        return prelude
    pieces = QUOTED_RE.split(prelude)
    for i in range(0, len(pieces), 2):
        part = ID_SEL_RE.sub(lambda m: '#' + scope.prefix + m.group(1) if _unescape_ident(m.group(1)) in scope.ids else m.group(0), pieces[i])
        pieces[i] = part
    text = ''.join(pieces)
    return ATTR_ID_RE.sub(lambda m: f'[id="{scope.prefix}{m.group(2)}"]' if m.group(2) in scope.ids else m.group(0), text)


def _scan(text, want_open):
    """Yield positions of top-level '{', '}' and ';' outside strings, comments and parentheses."""
    i, n, quote, paren = 0, len(text), None, 0
    while i < n:
        ch = text[i]
        if quote:
            if ch == '\\':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch == '/' and text.startswith('/*', i):
            j = text.find('*/', i + 2)
            i = n if j < 0 else j + 2
            continue
        elif ch == '\\':
            i += 2
            continue
        elif ch in '"\'':
            quote = ch
        elif ch == '(':
            paren += 1
        elif ch == ')':
            paren = max(0, paren - 1)
        elif paren == 0 and ch in '{};':
            yield i, ch
        i += 1


def _split_rules(text):
    rules, start, depth, opened = [], 0, 0, False
    for i, ch in _scan(text, False):
        if ch == '{':
            depth += 1
            opened = True
        elif ch == '}':
            depth -= 1
            if depth <= 0:
                rules.append(text[start:i + 1])
                start, depth, opened = i + 1, 0, False
        elif ch == ';' and depth == 0 and not opened:
            rules.append(text[start:i + 1])
            start = i + 1
    rest = text[start:]
    if rest.strip():
        rules.append(rest)
    return [r.strip() for r in rules if r.strip()]


def _first_brace(rule):
    for i, ch in _scan(rule, True):
        if ch == '{':
            return i
        if ch == ';':
            return -1
    return -1


FONT_FAMILY_RE = re.compile(r'(font-family\s*:\s*)([^;}]+)', re.I)


def _font_fallback(match):
    value = match.group(2)
    important = ''
    m = re.search(r'\s*!important\s*$', value, re.I)
    if m:
        important, value = m.group(0), value[:m.start()]
    if 'var(' in value.lower():
        return match.group(0)
    names = {v.strip().strip('"\'').lower() for v in value.split(',')}
    if names & GENERIC_FONTS:
        return match.group(0)
    return f'{match.group(1)}{value.rstrip()}, {SYSTEM_FONT_FALLBACK}{important}'


def _css_decls(body, scope, stats):
    body = _css_urls(body, scope, stats)
    body = FONT_FAMILY_RE.sub(_font_fallback, body)
    return re.sub(r'@import', r'@\\69 mport', body, flags=re.I)


NESTED_AT = {'media', 'supports', 'layer', 'container', 'scope', 'document', 'starting-style'}


def _xform_rule(rule, scope, stats):
    brace = _first_brace(rule)
    if brace < 0:
        return None if re.match(r'@(import|charset|namespace)\b', rule, re.I) else rule
    prelude = rule[:brace].strip()
    end = rule.rstrip().rfind('}')
    body = rule[brace + 1:end if end > brace else len(rule)]
    if prelude.startswith('@'):
        name = (re.match(r'@([\w-]+)', prelude) or [None, ''])[1].lower()
        if name == 'font-face':
            stats['font_faces_removed'] += 1
            m = re.search(r'font-family\s*:\s*([^;}]+)', body, re.I)
            if m:
                stats['font_families'].add(m.group(1).strip().strip('"\''))
            return None
        if name in NESTED_AT:
            inner = [x for x in (_xform_rule(r, scope, stats) for r in _split_rules(body)) if x]
            return f'{prelude}{{{chr(10).join(inner)}}}' if inner else None
        if name.endswith('keyframes'):
            return f'{prelude}{{{_css_urls(body, scope, stats)}}}'
        return f'{prelude}{{{_css_decls(body, scope, stats)}}}'
    return f'{_rewrite_selector(prelude, scope)}{{{_css_decls(body, scope, stats)}}}'


def _style_attr(value, scope, stats):
    value = _css_urls(value, scope, stats)
    value = re.sub(r'expression\s*\(|-moz-binding|behavior\s*:|javascript:', 'x-removed(', value, flags=re.I)
    return re.sub(r'@import', r'@\\69 mport', value, flags=re.I)


# --------------------------------------------------------------------------------------
# DOM sanitizer
# --------------------------------------------------------------------------------------
def _is_login_form(node):
    attrs = {k.lower(): (v or '') for k, v in node.attrs}
    sig = ' '.join(attrs.get(k, '') for k in ('id', 'class', 'action', 'aria-label', 'name'))
    if LOGIN_FORM_RE.search(sig):
        return True
    return any(n.tag == 'input' and (dict((k.lower(), v) for k, v in n.attrs).get('type') or '').lower() == 'password'
               for n in _walk(node))


class _Sanitizer:
    def __init__(self, scope, stats):
        self.scope = scope
        self.stats = stats

    def clean_list(self, children, in_svg=False):
        out = []
        for child in children:
            node = self.clean(child, in_svg)
            if node is not None:
                out.append(node)
        return out

    def clean(self, node, in_svg):
        if node.tag is None:
            return node
        tag = node.tag.lower()
        attrs = {k.lower(): ('' if v is None else v) for k, v in node.attrs}
        if tag in DROP_TAGS:
            self.stats['removed'][tag] += 1
            return None
        if tag == 'form' and _is_login_form(node):
            self.stats['removed']['credential_form'] += 1
            return None
        typ = attrs.get('type', '').lower()
        if tag == 'input' and typ in ('hidden', 'password', 'file'):
            self.stats['removed']['input_' + typ] += 1
            return None
        is_slot = tag == 'img' and 'data-gs-slot' in attrs
        if tag == 'img' and not is_slot:
            src = attrs.get('src', '')
            if not (src.lower().startswith('data:image/') and len(src) <= 8000 and '<script' not in src.lower()):
                self.stats['removed']['img_without_slot'] += 1
                return None
        if tag == 'use':
            ref = attrs.get('href', attrs.get('xlink:href', ''))
            if not ref.startswith('#'):
                self.stats['removed']['use_external'] += 1
                return None
        new = _Node(node.tag, self._attrs(tag, attrs, node.attrs, typ, in_svg, is_slot))
        child_svg = in_svg or tag == 'svg'
        new.children = self.clean_list(node.children, child_svg)
        if tag == 'textarea':
            new.children = []
        return new

    def _attrs(self, tag, attrs, original, typ, in_svg, is_slot):
        scope, out = self.scope, []
        for name, raw in original:
            ln = name.lower()
            v = '' if raw is None else raw
            if ln.startswith('on') or ln in DROP_ATTRS or SECRET_NAME_RE.search(ln):
                if ln == 'form' and tag == 'div':   # not reachable; kept for clarity
                    pass
                self.stats['attrs_removed'] += 1
                continue
            if ln in ('name', 'value') and tag in FORM_CONTROLS:
                if ln == 'value' and (tag == 'button' or typ in BUTTON_INPUT_TYPES):
                    pass
                else:
                    self.stats['attrs_removed'] += 1
                    continue
            if ln == 'data-gs-slot' or ln == 'data-gs-kind':
                out.append((name, v))
                continue
            if ln not in VALUE_SCAN_EXEMPT and SECRET_VALUE_RE.match(v.strip()):
                self.stats['attrs_removed'] += 1
                continue
            if ln.startswith('data-') and len(v) > 200:
                self.stats['attrs_removed'] += 1
                continue
            if 'javascript:' in v.lower() and ln != 'style':
                self.stats['attrs_removed'] += 1
                continue
            if ln == 'id':
                v = scope.pid(v)
            elif ln == 'for' or ln == 'usemap':
                v = scope.pid(v.lstrip('#'))
            elif ln in ARIA_REFS:
                v = ' '.join(scope.pid(t) for t in v.split())
            elif ln in ('href', 'xlink:href'):
                if tag == 'use':
                    v = '#' + scope.pid(v[1:])
                elif tag == 'a':
                    cleaned = _clean_href(v, scope)
                    if cleaned is None:
                        self.stats['links_removed'] += 1
                        continue
                    v = cleaned
                else:
                    self.stats['attrs_removed'] += 1
                    continue
            elif ln == 'src':
                if is_slot:
                    continue
            elif ln == 'style':
                v = _style_attr(v, scope, self.stats)
            elif 'url(' in v.lower():
                v = _css_urls(v, scope, self.stats)
            elif ln == 'target':
                if v != '_blank':
                    continue
            out.append((name, v))
        if tag == 'a' and any(k == 'target' for k, _ in out):
            out = [(k, val) for k, val in out if k != 'rel'] + [('rel', 'noopener noreferrer')]
        return out


# --------------------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------------------
def _validate_snapshot(name, snap):
    if not isinstance(snap, dict) or snap.get('kind') != 'gensite-static-snapshot':
        raise CloneError(f'{name}: not a gensite static snapshot')
    if snap.get('version') != SNAPSHOT_VERSION:
        raise CloneError(f'{name}: unsupported snapshot version {snap.get("version")!r}')
    if not isinstance(snap.get('body_html'), str) or not isinstance(snap.get('styles'), list):
        raise CloneError(f'{name}: snapshot lacks body_html/styles')


CHALLENGE_RE = re.compile(r'(performing security verification|just a moment\.\.\.|verify you are (a )?human|attention required!?|'
                          r'checking your browser before|enable javascript and cookies to continue|cf-chl|access denied)', re.I)


def _check_not_challenge(name, snap):
    text = (snap.get('title') or '') + ' ' + re.sub(r'<[^>]+>', ' ', snap['body_html'][:60000])
    if CHALLENGE_RE.search(text) and len(text) < 6000:
        raise CloneError(f'{name}: source looks like a bot/verification challenge or block page, not the real site; '
                         'capture it only after the site is legitimately reachable')


def _new_stats():
    return {'removed': Counter(), 'attrs_removed': 0, 'links_removed': 0, 'css_urls_removed': 0,
            'font_faces_removed': 0, 'font_families': set()}


def _sanitize_state(snap, prefix):
    tree = _parse_fragment(snap['body_html'])
    ids = {dict((k.lower(), v) for k, v in n.attrs).get('id') for n in _walk(tree) if n.tag}
    ids = {i for i in ids if i}
    scope = _Scope(prefix, ids, snap.get('url'), snap.get('base_url'))
    stats = _new_stats()
    children = _Sanitizer(scope, stats).clean_list(tree.children)
    return children, scope, stats


def _assign_slots(children, snap, image_count, state):
    """Point slot <img> nodes at assets/image-N.png.  Returns report rows."""
    meta = {str(s.get('index')): s for s in snap.get('slots', []) if isinstance(s, dict)}
    rows, major_n, minor_n = [], 0, 0
    holder = _Node('#root')
    holder.children = children
    for node in _walk(holder):
        if node.tag != 'img':
            continue
        attrs = dict(node.attrs)
        if 'data-gs-slot' not in attrs:
            continue
        if image_count == 0:
            raise CloneError('The reference has picture slots; choose at least one generated image to fill them without changing the layout.')
        info = meta.get(attrs['data-gs-slot'], {})
        w, h = float(info.get('width') or 0), float(info.get('height') or 0)
        visible = bool(info.get('visible', True))
        major = visible and w >= MIN_MAJOR_EDGE and h >= MIN_MAJOR_EDGE
        if major:
            number, major_n = major_n % image_count + 1, major_n + 1
        else:
            number, minor_n = minor_n % image_count + 1, minor_n + 1
        rows.append({'state': state, 'slot': int(attrs['data-gs-slot']), 'image': number, 'major': major,
                     'kind': attrs.get('data-gs-kind') or info.get('kind'), 'role': info.get('role'),
                     'width': w, 'height': h, 'visible': visible})
        new = [(k, v) for k, v in node.attrs if k.lower() not in ('src', 'width', 'height')]
        names = {k.lower() for k, _ in new}
        if 'alt' not in names:
            new.append(('alt', str(info.get('alt') or '')))
        new.append(('src', f'assets/image-{number}.png'))
        if attrs.get('data-gs-kind') != 'background':
            nat_w, nat_h = float(info.get('naturalWidth') or 0), float(info.get('naturalHeight') or 0)
            if w > 0 and h > 0:
                new.append(('width', str(int(round(w)))))
            elif nat_w > 0:
                new.append(('width', str(int(round(nat_w)))))
            extra = []
            if w > 0 and h > 0 and info.get('aspectRatio', 'auto') in (None, '', 'auto'):
                extra.append(f'aspect-ratio:{int(round(w))} / {int(round(h))}')
            if info.get('objectFit', 'fill') in (None, '', 'fill'):
                extra.append('object-fit:cover')
            if extra:
                style = next((v for k, v in new if k.lower() == 'style'), '')
                new = [(k, v) for k, v in new if k.lower() != 'style']
                new.append(('style', (style.rstrip('; ') + ';' if style else '') + ';'.join(extra)))
        style = next((v for k,v in new if k.lower() == 'style'), '')
        new = [(k,v) for k,v in new if k.lower() != 'style']
        new.append(('style',(style.rstrip('; ')+';' if style else '')+'pointer-events:auto!important'))
        node.attrs = new
    return rows


def _css_for_state(snap, scope, stats, seen):
    chunks = []
    for sheet in snap['styles']:
        css = sheet.get('css') or ''
        rules = []
        for rule in _split_rules(css):
            out = _xform_rule(rule, scope, stats)
            if out and out not in seen:
                seen.add(out)
                rules.append(out)
        if not rules:
            continue
        text = '\n'.join(rules)
        media = (sheet.get('media') or '').strip()
        chunks.append(f'@media {media}{{\n{text}\n}}' if media else text)
    return chunks


def _font_only_sheet(href):
    return bool(href) and (any(h in href for h in FONT_CSS_HOST_HINTS) or 'font' in href.lower())


def _attr_string(attrs, scope, stats, allow=('class', 'style', 'lang', 'dir', 'id')):
    out = []
    for name, value in (attrs or {}).items():
        ln = name.lower()
        if ln.startswith('on') or SECRET_NAME_RE.search(ln) or SECRET_VALUE_RE.match(str(value).strip()):
            continue
        if ln in allow or ln.startswith('data-') or ln.startswith('aria-'):
            if len(str(value)) > 200 and ln.startswith('data-'):
                continue
            if ln == 'id':
                value = scope.pid(value)
            elif ln == 'style':
                value = _style_attr(value, scope, stats)
            out.append(f' {name}="{_esc_attr(str(value))}"')
    return ''.join(out)


def build_static_report(snapshots, image_count, *, allow_partial=False, breakpoint=768, title=None):
    """Build the static clone and return a report dict (``['html']`` is the complete document)."""
    if type(image_count) is not int or not 0 <= image_count <= 12:
        raise CloneError('image_count must be an integer between 0 and 12')
    if not isinstance(snapshots, dict) or not snapshots:
        raise CloneError('snapshots must map "desktop"/"mobile" to capture dicts')
    unknown = set(snapshots) - {'desktop', 'mobile'}
    if unknown:
        raise CloneError(f'unknown snapshot states: {sorted(unknown)}')
    states = [(name, snapshots[name]) for name in ('desktop', 'mobile') if name in snapshots]
    for name, snap in states:
        _validate_snapshot(name, snap)
        _check_not_challenge(name, snap)

    # Decide between one shared DOM and two namespaced responsive DOM states.
    plain = [_sanitize_state(snap, '') for _, snap in states]
    serialized = []
    for children, _, _ in plain:
        out = []
        for c in children:
            _serialize(c, out)
        serialized.append(re.sub(r'data-gs-slot="\d+"', 'data-gs-slot=""', ''.join(out)))
    single = len(states) == 1 or serialized[0] == serialized[1]
    warnings, removed = [], Counter()
    seen_css, css_chunks, slot_rows, bodies = set(), [], [], []
    stat_total = _new_stats()
    inaccessible, all_rules = [], 0

    if single:
        targets = [(states[0][0], states[0][1], '')]
        union = states
    else:
        targets = [(name, snap, 'd-' if name == 'desktop' else 'm-') for name, snap in states]
        union = states
    for name, snap, prefix in targets:
        children, scope, stats = _sanitize_state(snap, prefix)
        rows = _assign_slots(children, snap, image_count, name)
        slot_rows.extend(rows)
        out = []
        for c in children:
            _serialize(c, out)
        bodies.append((name, ''.join(out), scope))
        if not single or name == states[0][0]:
            for k, v in stats['removed'].items():
                removed[k] += v
        _merge_stats(stat_total, stats)
    # CSS: in single mode the other snapshot's rules are still unioned (unprefixed).
    css_sources = [(name, snap, scope) for (name, snap, _), (_, _, scope) in zip(targets, bodies)]
    if single and len(states) == 2:
        css_sources.append((states[1][0], states[1][1], bodies[0][2]))
    for name, snap, scope in css_sources:
        css_chunks.extend(_css_for_state(snap, scope, stat_total, seen_css))
    for name, snap in union:
        all_rules += sum(int(s.get('rule_count') or 0) for s in snap['styles'])
        for item in snap.get('inaccessible_stylesheets') or []:
            href = item.get('href')
            if not any(x['href'] == href for x in inaccessible):
                inaccessible.append({'href': href, 'reason': item.get('reason'), 'font_only': _font_only_sheet(href), 'state': name})
        for w in snap.get('warnings') or []:
            if isinstance(w, dict) and w.get('code') != 'inaccessible_stylesheet' and w not in warnings:
                warnings.append(w)
    if not css_chunks:
        raise CloneError('no accessible stylesheet rules in the snapshot; refusing to guess a layout')
    blocking = [x for x in inaccessible if not x['font_only']]
    if blocking and not allow_partial:
        raise CloneIncomplete('inaccessible stylesheets: ' + ', '.join(str(x['href'] or '(inline)') for x in blocking)
                              + ' (pass allow_partial=True to build a partial clone)')
    for x in inaccessible:
        warnings.append({'code': 'inaccessible_stylesheet', 'href': x['href'], 'font_only': x['font_only'],
                         'message': 'stylesheet unreadable; its rules are missing from the clone'})

    # Slot coverage: every requested image must be placed in a real, visible, non-trivial slot.
    major = [r for r in slot_rows if r['major']]
    used = {r['image'] for r in major}
    if len(used) < image_count:
        raise CloneError(f'source exposes only {len(major)} visible picture slots; cannot place all {image_count} '
                         'requested images without hidden filler')

    primary_name, primary_snap, primary_scope = states[0][0], states[0][1], bodies[0][2]
    stats_for_attrs = _new_stats()
    if single:
        body_markup = bodies[0][1]
    else:
        body_markup = ''.join(f'<div class="gs-state gs-state-{n}" data-gs-state="{n}">{m}</div>' for n, m, _ in bodies)
        other = states[1][1]
        if (other.get('body_attrs') or {}) != (primary_snap.get('body_attrs') or {}) or (other.get('html_attrs') or {}) != (primary_snap.get('html_attrs') or {}):
            warnings.append({'code': 'state_root_attrs_differ', 'message': 'html/body attributes differ between states; desktop attributes used'})
    html_attrs = _attr_string(primary_snap.get('html_attrs'), primary_scope, stats_for_attrs, allow=('class', 'style', 'lang', 'dir'))
    body_attrs = _attr_string(primary_snap.get('body_attrs'), primary_scope, stats_for_attrs)
    if 'lang=' not in html_attrs:
        html_attrs += f' lang="{_esc_attr(primary_snap.get("lang") or "en")}"'
    bp = int(breakpoint)
    switch = ''
    if not single:
        switch = (f'\n.gs-state{{display:contents}}\n@media (max-width:{bp - 0.02}px){{.gs-state-desktop{{display:none}}}}\n'
                  f'@media (min-width:{bp}px){{.gs-state-mobile{{display:none}}}}')
    css = '\n'.join(css_chunks).replace('</style', '<\\/style') + switch
    families = sorted(stat_total['font_families'] | set(primary_snap.get('font_families') or []))
    fonts = {'fallback': SYSTEM_FONT_FALLBACK, 'removed_font_face_rules': stat_total['font_faces_removed'], 'families': families}
    exact = not blocking
    notes = [f'mode={"single" if single else "responsive-states"}', f'exact_styles={str(exact).lower()}']
    if blocking:
        notes.append('missing stylesheets: ' + ', '.join(str(x['href']) for x in blocking))
    if families:
        notes.append('remote fonts replaced by system fallback: ' + ', '.join(families[:12]))
    comment = '<!-- gensite-clone-snapshot ' + re.sub(r'--+', '-', '; '.join(notes)) + ' -->'
    page_title = title or primary_snap.get('title') or 'Clone'
    html = (f'<!DOCTYPE html>\n<html{html_attrs}>\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f'<meta name="generator" content="gensite-clone-snapshot">\n{comment}\n<title>{_html_escape(page_title)}</title>\n'
            f'<style id="gs-clone-css">\n{css}\n</style>\n</head>\n<body{body_attrs}>\n{body_markup}\n</body>\n</html>\n')
    html = re.sub(r'<(/?)(script|iframe|object|embed)\b', r'&lt;\1\2', html, flags=re.I) if re.search(r'<script', body_markup, re.I) else html
    return {'html': html, 'mode': 'single' if single else 'responsive-states', 'exact_styles': exact,
            'warnings': warnings, 'fonts': fonts, 'slots': slot_rows, 'image_usage': dict(Counter(r['image'] for r in major)),
            'removed': dict(removed), 'attrs_removed': stat_total['attrs_removed'], 'links_removed': stat_total['links_removed'],
            'css_urls_removed': stat_total['css_urls_removed'], 'inaccessible_stylesheets': inaccessible,
            'css_bytes': len(css), 'stylesheet_rule_count': all_rules}


def _merge_stats(total, stats):
    total['attrs_removed'] += stats['attrs_removed']
    total['links_removed'] += stats['links_removed']
    total['css_urls_removed'] += stats['css_urls_removed']
    total['font_faces_removed'] += stats['font_faces_removed']
    total['font_families'] |= stats['font_families']


def build_static_html(snapshots, image_count, **options):
    """Return one complete static HTML document (see :func:`build_static_report` for options)."""
    return build_static_report(snapshots, image_count, **options)['html']


def snapshot_json(snapshot):
    """Stable JSON text for storing a snapshot next to its report."""
    return json.dumps(snapshot, ensure_ascii=False, indent=1, sort_keys=True)
