"""Generic measured visual structure for reference-site recreation; no site adapters."""

CAPTURE_DESIGN_JS = r"""(() => {
  const W=innerWidth,H=innerHeight;
  const props=['display','position','width','height','min-width','max-width','background-color','background-image','color','font-family','font-size','font-weight','line-height','padding','margin','border-radius','border-color','grid-template-columns','flex-direction','gap','align-items','justify-content','overflow-y'];
  const opaque=c => c && c!=='transparent' && !/^rgba\(.*,[\s]*0\)$/.test(c);
  const box=r => [Math.round(r.x),Math.round(r.y+scrollY),Math.round(r.width),Math.round(r.height)];
  const selector=e => e.id ? '#'+e.id.slice(0,100) : e.tagName.toLowerCase()+'.'+String(typeof e.className==='string'?e.className:'').trim().split(/\s+/).filter(Boolean).slice(0,2).join('.');
  const styles=e => {const c=getComputedStyle(e),s={};for(const p of props)s[p]=c.getPropertyValue(p).slice(0,180);return s};
  const roots=[document.documentElement,document.body].filter(Boolean).map(e=>({selector:e.tagName.toLowerCase(),style:styles(e)}));
  const colors=new Map(),candidates=[];
  for(const el of [...document.querySelectorAll('header,nav,main,aside,footer,section,article,div,a,img,h1,h2')].slice(0,2500)) {
    const r=el.getBoundingClientRect();
    if(r.width<80||r.height<24||r.right<=0||r.left>=W||r.bottom<=0)continue;
    const cs=getComputedStyle(el);
    if(cs.visibility==='hidden'||cs.opacity==='0')continue;
    const area=Math.max(0,Math.min(W,r.right)-Math.max(0,r.left))*Math.max(0,Math.min(H,r.bottom)-Math.max(0,r.top));
    const bg=cs.backgroundColor;
    if(opaque(bg)&&area>0)colors.set(bg,(colors.get(bg)||0)+area);
    let kind='panel',score=20;
    const tag=el.tagName.toLowerCase();
    if(['header','nav','footer','main','aside','section','article','h1','h2'].includes(tag))score+=60;
    if(tag==='main'){kind='primary';score+=100}
    if((r.x<W*.08||r.right>W*.92)&&r.width<W*.4&&r.height>H*.45&&r.y<H*.25){kind='sidebar';score+=210}
    if(r.width>W*.65&&r.height<140&&r.y<80){kind='topbar';score+=190}
    if(r.x>W*.1&&r.width>W*.45&&r.height>H*.45){kind='primary';score+=140}
    if(cs.display==='grid'){kind='grid';score+=110}
    if(tag==='img'&&r.width>W*.4&&r.height>100){kind='wide-image';score+=210}
    if(tag==='h1'||tag==='h2'){kind='heading';score+=40}
    if(opaque(bg))score+=10;
    if(area===0)score-=80;
    candidates.push({el,r,kind,score});
  }
  candidates.sort((a,b)=>b.score-a.score);
  const chosen=[];
  for(const c of candidates){
    if(chosen.length>=28)break;
    if(chosen.some(p=>Math.abs(p.r.x-c.r.x)<3&&Math.abs(p.r.y-c.r.y)<3&&Math.abs(p.r.width-c.r.width)<3&&Math.abs(p.r.height-c.r.height)<3))continue;
    chosen.push(c);
  }
  const palette=[...colors.entries()].sort((a,b)=>b[1]-a[1]).slice(0,8).map(([color,area])=>({color,area:Math.round(area)}));
  const htmlbg=roots.find(x=>x.selector==='html')?.style['background-color'];
  const bodybg=roots.find(x=>x.selector==='body')?.style['background-color'];
  const canvas=opaque(bodybg)?bodybg:opaque(htmlbg)?htmlbg:palette[0]?.color||'unknown';
  const rgb=canvas.match(/^rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)/);
  const theme=rgb?(.2126*Number(rgb[1])+.7152*Number(rgb[2])+.0722*Number(rgb[3])<128?'dark':'light'):'unknown';
  return {theme,canvas_background:canvas,roots,palette,
    regions:chosen.map(({el,r,kind})=>({kind,tag:el.tagName.toLowerCase(),selector:selector(el),rect:box(r),text:(el.innerText||el.getAttribute('alt')||'').trim().slice(0,140),style:styles(el)})),
    instruction:'These are measured reference-page colors and container positions, not a suggestion for a new design. Preserve the theme and relative region arrangement at each viewport.'};
})()"""
