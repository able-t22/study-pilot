/* Offline MathML rendering. All source text is inserted with DOM textContent. */
(() => {
 const NS='http://www.w3.org/1998/Math/MathML';
 const symbols={alpha:'α',beta:'β',gamma:'γ',delta:'δ',epsilon:'ε',theta:'θ',lambda:'λ',mu:'μ',pi:'π',sigma:'σ',phi:'φ',omega:'ω',Delta:'Δ',Sigma:'Σ',Omega:'Ω',infty:'∞',sum:'∑',prod:'∏',int:'∫',partial:'∂',nabla:'∇',times:'×',cdot:'·',div:'÷',pm:'±',le:'≤',leq:'≤',ge:'≥',geq:'≥',neq:'≠',approx:'≈',to:'→',rightarrow:'→',in:'∈',notin:'∉',cup:'∪',cap:'∩',ldots:'…',dots:'…',forall:'∀',exists:'∃'};
 function node(tag,...children){let e=document.createElementNS(NS,tag);for(let c of children)e.append(typeof c==='string'?document.createTextNode(c):c);return e;}
 function parse(s){
  let a=s.match(/\\[a-zA-Z]+|\\.|[0-9]+(?:\.[0-9]+)?|[a-zA-Z]|\s+|[^\s]/g)||[],i=0;
  function group(){while(/^\s+$/.test(a[i]||''))i++;if(a[i]==='{'){i++;return row('}');} return atom();}
  function atom(){while(/^\s+$/.test(a[i]||''))i++;let t=a[i++]||'';if(t==='{')return row('}');
   if(t==='\\begin'){
    const env=group().textContent, rows=[],cells=[],buf=[];
    function cell(){cells.push(node('mtd',parse(buf.join(''))));buf.length=0;}
    function finish(){cell();rows.push(node('mtr',...cells));cells.length=0;}
    while(i<a.length&&a[i]!=='\\end'){let v=a[i++];if(v==='&')cell();else if(v==='\\\\')finish();else buf.push(v);}
    if(buf.length||cells.length)finish();
    if(a[i]==='\\end'){i++;group();}
    const table=node('mtable',...rows),delims=env==='pmatrix'?['(',')']:env==='bmatrix'?['[',']']:env==='vmatrix'?['|','|']:env==='cases'?['{','']:['',''];
    return node('mrow',node('mo',delims[0]),table,node('mo',delims[1]));
   }
   if(t==='\\mathbb'){const g=group().textContent;return node('mi',({R:'ℝ',N:'ℕ',Z:'ℤ',Q:'ℚ',C:'ℂ'})[g]||g);}
   if(t==='\\frac'||t==='\\dfrac'||t==='\\tfrac')return node('mfrac',group(),group());
   if(t==='\\sqrt'){let degree;if(a[i]==='['){i++;degree=row(']');}let rad=group();return degree?node('mroot',rad,degree):node('msqrt',rad);}
   if(t==='\\text' && a[i]==='{'){i++;let text='',depth=1;while(i<a.length&&depth){let v=a[i++];if(v==='{')depth++;if(v==='}')depth--;if(depth)text+=v;}return node('mtext',text);}
   if(['\\text','\\mathrm','\\operatorname','\\mathbf','\\mathit'].includes(t)){let g=group();if(t==='\\text')return node('mtext',g.textContent.replace(/([a-z])([A-Z])/g,'$1 $2'));return g;}
   if(t==='\\left'||t==='\\right')return atom();
   if(t==='\\overline'||t==='\\bar'||t==='\\vec'||t==='\\hat')return node('mover',group(),node('mo',t==='\\vec'?'→':t==='\\hat'?'^':'¯'));
   if(t==='\\, '||['\\,','\\;','\\!','\\quad','\\qquad'].includes(t))return node('mspace');
   if(t.startsWith('\\')){let key=t.slice(1);return node(symbols[key]?'mo':'mi',symbols[key]||key);}
   return node(/^\d/.test(t)?'mn':/^[a-zA-Z]$/.test(t)?'mi':'mo',t);
  }
  function row(end){let out=node('mrow');while(i<a.length&&a[i]!==end){if(/^\s+$/.test(a[i]||'')){i++;continue;}let b=atom(),sub,sup;while(/^\s+$/.test(a[i]||''))i++;while(a[i]==='_'||a[i]==='^'){let op=a[i++],g=group();if(op==='_')sub=g;else sup=g;while(/^\s+$/.test(a[i]||''))i++;}if(sub&&sup)b=node('msubsup',b,sub,sup);else if(sub)b=node('msub',b,sub);else if(sup)b=node('msup',b,sup);out.append(b);}if(end&&a[i]===end)i++;return out;}
  return row();
 }
 function math(tex,display){let m=node('math',parse(tex.replace(/\/(sqrt|frac|sum|int|alpha|beta|theta|pi)\b/g,'\\$1')));m.setAttribute('display',display?'block':'inline');m.setAttribute('aria-label',tex);m.title=tex;return m;}
 const pattern=/\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\(([\s\S]+?)\\\)|(?<!\\)\$([^$\n]+?)\$|(?:\\|\/)(?:sqrt|frac|dfrac|sum|int)\b(?:\{[^{}\n]*(?:\{[^{}\n]*\}[^{}\n]*)*\}|[_^][a-zA-Z0-9{}]+|\s*[a-zA-Z0-9=+().-]+)+/g;
 function render(root=document.body){let walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement?.closest('math,script,style,textarea,input,code,pre,svg,option')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT}),texts=[];while(walker.nextNode())texts.push(walker.currentNode);
  for(let n of texts){let s=n.nodeValue,m,last=0,frag=document.createDocumentFragment();pattern.lastIndex=0;while((m=pattern.exec(s))){frag.append(document.createTextNode(s.slice(last,m.index)));frag.append(math(m[1]||m[2]||m[3]||m[4]||m[0],!!(m[1]||m[2])));last=pattern.lastIndex;}if(last){frag.append(document.createTextNode(s.slice(last)));n.replaceWith(frag);}}
 }
 window.renderMath=render;
 addEventListener('DOMContentLoaded',()=>{render();let queued=false;new MutationObserver(changes=>{if(queued||!changes.some(c=>[...c.addedNodes].some(n=>n.nodeType===3||n.nodeType===1&&n.namespaceURI!==NS)))return;queued=true;requestAnimationFrame(()=>{queued=false;render();});}).observe(document.body,{childList:true,subtree:true});});
})();