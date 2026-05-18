"""Build a compact, token-frugal observation of the current page.

Never returns full DOM or full text. Visible text is capped; cookie /
localStorage *keys* only (values withheld unless the user opts in). Buttons and
links get stable selector ids so Claude can reference them by handle.
"""
from __future__ import annotations

from typing import Any

_JS_OBSERVE = r"""
() => {
  const vis = el => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none';
  };
  const txt = (document.body ? document.body.innerText : '').replace(/\s+/g,' ').trim();
  const forms = [...document.forms].slice(0,15).map((f,i)=>({
    id: f.id || ('form#'+i),
    action: f.getAttribute('action')||'',
    method: (f.getAttribute('method')||'get').toLowerCase(),
    fields: [...f.elements].slice(0,30).map(e=>({
      name: e.name||'', type: e.type||e.tagName.toLowerCase(),
      hidden: e.type==='hidden'
    }))
  }));
  // Assign every interactive element a REAL, resolvable handle in the DOM
  // (data-ctfc="<ref>") and return that ref so browser.click/fill can find
  // it via [data-ctfc="<ref>"]. Previously refs were opaque labels nothing
  // could resolve, so every click timed out.
  let _n = 0;
  const ref = el => { const r = 'e' + (_n++);
                      el.setAttribute('data-ctfc', r); return r; };
  const tag = (sel, attr) => [...document.querySelectorAll(sel)]
    .filter(vis).slice(0,40).map(el=>({
      ref: ref(el),
      text: (el.innerText||el.value||el.getAttribute('aria-label')
             ||el.getAttribute('placeholder')||'').trim().slice(0,60),
      [attr]: el.getAttribute(attr)||''
    }));
  return {
    url: location.href,
    title: document.title,
    visible_text: txt.slice(0, 1500),
    text_len: txt.length,
    forms,
    buttons: tag('button, input[type=submit], input[type=button], '
                 + '[role=button], a.btn', 'name'),
    links: tag('a[href]', 'href'),
    inputs: [...document.querySelectorAll('input,select,textarea')]
      .filter(vis).slice(0,40).map(e=>({ref:ref(e), name:e.name||'',
        type:e.type||e.tagName.toLowerCase(),
        placeholder:e.getAttribute('placeholder')||''})),
    cookie_keys: document.cookie.split(';').map(c=>c.split('=')[0].trim()).filter(Boolean),
    localStorage_keys: Object.keys(localStorage||{}),
  };
}
"""


def observe(page: Any, *, include_storage_values: bool = False) -> dict[str, Any]:
    """Run the in-page collector and return a plain dict."""
    data: dict[str, Any] = page.evaluate(_JS_OBSERVE)
    if not include_storage_values:
        data["note"] = "cookie/localStorage VALUES withheld (privacy). Keys only."
    return data
