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
  const tag = (sel, attr) => [...document.querySelectorAll(sel)]
    .filter(vis).slice(0,40).map((el,i)=>({
      ref: sel.replace(/[^a-z]/g,'')+i,
      text: (el.innerText||el.value||'').trim().slice(0,60),
      [attr]: el.getAttribute(attr)||''
    }));
  return {
    url: location.href,
    title: document.title,
    visible_text: txt.slice(0, 1500),
    text_len: txt.length,
    forms,
    buttons: tag('button, input[type=submit]', 'name'),
    links: tag('a[href]', 'href'),
    inputs: [...document.querySelectorAll('input,select,textarea')]
      .slice(0,40).map((e,i)=>({ref:'in'+i, name:e.name||'', type:e.type||e.tagName.toLowerCase()})),
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
