"""Source-preserving clone assembly for the native direct-model workflow."""
from __future__ import annotations

import json
from urllib.parse import urlsplit

from .reference_web import ReferenceUnavailable, reference_urls


def generate_source_clone(e, project, rules, brief, image_count):
    """Preserve browser DOM/CSS; use the model for art prompts, not layout invention."""
    from .engine import _json_write, parse_response
    from .clone_snapshot import build_static_html
    from .llm_recovery import repair_local_site
    urls=reference_urls(brief)
    if len(urls)!=1:
        raise ValueError('Source-preserving clone currently requires one reference page URL. Clone additional URLs as separate pages rather than guessing their layouts.')
    url=urls[0]
    host=urlsplit(url).hostname.lower()
    e._web_reference_hosts.update({host,host[4:] if host.startswith('www.') else 'www.'+host})
    call={'id':'clone-reference','type':'function','function':{'name':'read_webpage','arguments':json.dumps({'url':url})}}
    e._emit('Capturing the source layout and styles for a close visual clone; ComfyUI images will fill the original slots.')
    e._search_tool(call,project)
    source=e._web_search_log[-1]['result']
    snapshots=source.get('static_snapshots')
    if not isinstance(snapshots,dict) or not snapshots.get('desktop') or not snapshots.get('mobile'):
        raise ReferenceUnavailable('The rendered reference did not include desktop/mobile HTML and CSS snapshots. Restart Gensite after updating; the app will not substitute a guessed layout.')
    e._cancelled()
    html=build_static_html(snapshots,image_count)
    data={'pages':[{'filename':'index.html','title':source.get('title') or 'Cloned reference','html':html}],'images':[]}
    _json_write(project/'response.json',data)
    _json_write(project/'source-clone.json',{'source_url':source.get('url',url),'mode':'source-preserving','image_policy':'comfyui-in-source-slots','requested_images':image_count,
        'warnings':{name:part.get('warnings',[]) for name,part in snapshots.items()},'scope':'Supplied reference page only; external page navigation is not a copied backend.'})
    if image_count:
        e._emit('Source layout saved. Asking the model only for missing image prompts; no layout regeneration.')
        parsed=repair_local_site(e,project,rules,brief,image_count,data)
    else:
        parsed=parse_response(data,0)
    return parsed
