"""Lazy Chromium canvas. No Python object is exposed to generated JavaScript."""
import json
import secrets
from pathlib import Path
from PySide6.QtCore import QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

EDITOR_JS = r'''
(()=>{
 if (globalThis.__gensiteEditor) return;
 let selected=null, overlay=null;
 const selector=e=>{
  const parts=[];
  while(e && e.nodeType===1 && e!==document.documentElement){
   parts.unshift(e.tagName.toLowerCase()+':nth-child('+(Array.from(e.parentElement.children).indexOf(e)+1)+')');
   e=e.parentElement;
  }
  return 'html > '+parts.join(' > ');
 };
 const show=(e,resized,quiet)=>{
  if(!e || e===overlay || ['HTML','SCRIPT','STYLE','HEAD'].includes(e.tagName)) return;
  selected=e;
  if(!overlay){overlay=document.createElement('div');overlay.setAttribute('data-gensite-overlay','');document.documentElement.appendChild(overlay);}
  const r=e.getBoundingClientRect();
  overlay.style.cssText=`pointer-events:none!important;position:fixed!important;z-index:2147483647!important;box-sizing:border-box!important;border:2px solid #2858d8!important;background:rgba(40,88,216,.04)!important;left:${r.left}px!important;top:${r.top}px!important;width:${r.width}px!important;height:${r.height}px!important;`;
  let handle=overlay.querySelector('[data-gensite-handle]');
  if(e.tagName==='IMG'){
   if(!handle){
    handle=document.createElement('div');
    handle.setAttribute('data-gensite-handle','');
    handle.title='Drag to resize';
    handle.style.cssText='position:absolute!important;right:2px!important;bottom:2px!important;width:16px!important;height:16px!important;box-sizing:border-box!important;background:#2858d8!important;border:2px solid #fff!important;border-radius:3px!important;cursor:nwse-resize!important;pointer-events:auto!important;touch-action:none!important;';
    handle.addEventListener('pointerdown',down=>{
     down.preventDefault();down.stopImmediatePropagation();
     const img=selected, startX=down.clientX, startW=img.getBoundingClientRect().width;
     const move=m=>{img.style.width=Math.max(24,Math.round(startW+m.clientX-startX))+'px';img.style.height='auto';show(img,false,true);};
     const up=()=>{removeEventListener('pointermove',move,true);removeEventListener('pointerup',up,true);removeEventListener('pointercancel',up,true);show(img,true);};
     addEventListener('pointermove',move,true);addEventListener('pointerup',up,true);addEventListener('pointercancel',up,true);
    },true);
    overlay.appendChild(handle);
   }
  } else if(handle){handle.remove();}
  if(quiet) return;
  const s=getComputedStyle(e);
  console.log(TOKEN+JSON.stringify({tag:e.tagName.toLowerCase(),selector:selector(e),text:e.textContent.slice(0,16000),color:s.color,backgroundColor:s.backgroundColor,fontSize:s.fontSize,fontFamily:s.fontFamily,padding:s.paddingTop,image:e.tagName==='IMG'?e.getAttribute('src'):'',width:Math.round(r.width),resized:!!resized,hasChildren:!!e.children.length}));
 };
 document.addEventListener('click',ev=>{
   ev.preventDefault();ev.stopImmediatePropagation();
   let target=ev.target;
   if(target.closest&&target.closest('[data-gensite-overlay]'))return;
   const ownText=Array.from(target.childNodes||[]).some(n=>n.nodeType===3&&n.textContent.trim());
   if(target.tagName!=='IMG'&&!ownText&&!target.closest('button,input,textarea,select,svg')){
     const picture=document.elementsFromPoint(ev.clientX,ev.clientY).find(e=>e.tagName==='IMG'&&parseFloat(getComputedStyle(e).opacity)>0);
     if(picture)target=picture;
   }
   show(target);
 },true);
 document.addEventListener('submit',ev=>ev.preventDefault(),true);
 addEventListener('scroll',()=>{if(selected)show(selected)},true);
 addEventListener('resize',()=>{if(selected)show(selected)});
 globalThis.__gensiteEditor={
  select:css=>show(document.querySelector(css)),
  apply:values=>{
   if(!selected) return false;
   if('text' in values && selected.tagName!=='IMG') selected.textContent=values.text;
   for(const key of ['color','backgroundColor','fontSize','fontFamily','padding']) if(key in values) selected.style[key]=values[key];
   if('image' in values && selected.tagName==='IMG') selected.setAttribute('src',values.image);
   if('width' in values && selected.tagName==='IMG'){
    const w=Math.round(Number(values.width));
    if(w>0){selected.style.width=Math.min(w,20000)+'px';selected.style.height='auto';}
    else{selected.style.removeProperty('width');selected.style.removeProperty('height');}
   }
   show(selected);return true;
  },
  snapshot:()=>{const clone=document.documentElement.cloneNode(true);clone.querySelectorAll('[data-gensite-overlay]').forEach(e=>e.remove());return '<!DOCTYPE html>\n'+clone.outerHTML;},
  outline:()=>{
   const clean=s=>(s||'').replace(/\s+/g,' ').trim();
   const label=e=>{
    const tag=e.tagName.toLowerCase();
    const named=clean(e.getAttribute('aria-label'))||clean(e.id);
    if(named) return tag+'  '+named.slice(0,40);
    if(/^h[1-6]$/.test(tag)) return tag+'  '+clean(e.innerText).slice(0,40);
    const h=e.querySelector('h1,h2,h3,h4');
    if(h && clean(h.innerText)) return tag+'  '+clean(h.innerText).slice(0,40);
    if(tag==='nav'){const links=Array.from(e.querySelectorAll('a')).slice(0,4).map(a=>clean(a.innerText)).filter(Boolean);if(links.length) return tag+'  '+links.join(' · ').slice(0,40);}
    const t=clean(e.innerText).slice(0,40);
    return t?tag+'  '+t:tag;
   };
   return Array.from(document.querySelectorAll('header,nav,main,section,article,footer,h1,h2')).slice(0,200).map(e=>({selector:selector(e),label:label(e)}));
  }
 };
})();
'''


class ExternalLinkPage(QWebEnginePage):
    """Throwaway page for target=_blank links: hands the URL to the system browser."""

    def acceptNavigationRequest(self, url, kind, isMainFrame):
        if url.scheme() in {'http', 'https'}:
            QDesktopServices.openUrl(url)
        QTimer.singleShot(0, self.deleteLater)
        return False


class CanvasPage(QWebEnginePage):
    selection = Signal(dict)

    def __init__(self, profile, parent):
        super().__init__(profile, parent)
        self.token = 'GENSITE-'+secrets.token_hex(24)+':'
        self.origin = ''
        self.preview = False
        self.external_links = False  # only for trusted info pages (e.g. Support); never generated sites

    def javaScriptConsoleMessage(self, level, message, line, source):
        if message.startswith(self.token) and len(message) < 40000:
            try:
                value = json.loads(message[len(self.token):])
                if isinstance(value, dict) and isinstance(value.get('selector'), str):
                    self.selection.emit(value)
            except ValueError:
                pass

    def acceptNavigationRequest(self, url, kind, isMainFrame):
        if isMainFrame:
            if self.external_links and kind == QWebEnginePage.NavigationType.NavigationTypeLinkClicked and url.scheme() in {'http', 'https'}:
                QDesktopServices.openUrl(url)
                return False
            if self.preview and url.scheme() in {'http','https'}:
                return True
            return url.toString().startswith(self.origin+'/') or url.toString() == 'about:blank'
        return True

    def createWindow(self, kind):
        if self.external_links:
            return ExternalLinkPage(self.profile(), self)
        return None


class SiteCanvas(QWebEngineView):
    selected = Signal(dict)
    loaded = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.profile = QWebEngineProfile(self)
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        self._install_page()
        self.edit = True
        self.external_links = False
        self.ready = False
        self.loadFinished.connect(self._finished)
        self.setMinimumSize(1, 1)
        self.setStyleSheet('background:white;')

    def _install_page(self):
        from shiboken6 import isValid
        previous = getattr(self, 'canvas_page', None)
        self.canvas_page = CanvasPage(self.profile, self)
        self.setPage(self.canvas_page)
        if previous is not None and isValid(previous):
            previous.deleteLater()
        self.canvas_page.selection.connect(self.selected)
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, False)
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)

    def _finished(self, ok):
        self.ready = bool(ok)
        self.loaded.emit(bool(ok))

    def open(self, url, origin, edit=True):
        self.ready = False
        if self.edit != edit and self.url().toString() not in ('', 'about:blank'):
            # Script-list clearing alone leaves the old editing context attached.
            # Isolate Preview from it before allowing normal external navigation.
            self._install_page()
        self.edit = edit
        self.canvas_page.origin = origin
        self.canvas_page.preview = not edit
        self.canvas_page.external_links = self.external_links and not edit
        self.page().scripts().clear()
        if edit:
            script = QWebEngineScript()
            script.setName('Gensite isolated editor')
            script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
            script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
            script.setRunsOnSubFrames(False)
            script.setSourceCode(EDITOR_JS.replace('TOKEN', json.dumps(self.canvas_page.token)))
            self.page().scripts().insert(script)
        self.load(QUrl(url))

    def evaluate(self, code, callback=None):
        def decoded(value):
            try:
                result = json.loads(value) if isinstance(value, str) and value else None
            except (ValueError, TypeError):
                result = None
            if callback:
                callback(result)
        # Explicit JSON avoids binding-dependent QVariant conversions for arrays/objects.
        source = 'JSON.stringify((()=>{return ('+code+');})())'
        self.page().runJavaScript(source, QWebEngineScript.ScriptWorldId.ApplicationWorld, decoded)

    def select(self, css):
        self.evaluate('globalThis.__gensiteEditor?.select('+json.dumps(css)+')')

    def apply(self, values, callback):
        self.evaluate('globalThis.__gensiteEditor?.apply('+json.dumps(values)+')', callback)

    def snapshot(self, callback):
        self.evaluate('globalThis.__gensiteEditor?.snapshot()', callback)

    def outline(self, callback):
        self.evaluate('globalThis.__gensiteEditor?.outline()', callback)

    def dispose(self):
        self.stop()
        # Page must die before its profile (Qt's required destruction order).
        self.canvas_page.deleteLater()
        self.deleteLater()
