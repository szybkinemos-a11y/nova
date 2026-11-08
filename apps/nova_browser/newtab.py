"""Strona nowej karty: wyszukiwarka + szybkie wybieranie (zakładki)."""
from __future__ import annotations

import html


def render(bookmarks: list[dict], engine_url: str, dark: bool, labels: dict[str, str]) -> str:
    tiles = "".join(
        f'<a class="tile" href="{html.escape(b["url"])}"><span class="ic">{html.escape((b["title"] or "?")[0].upper())}</span>'
        f'<span class="t">{html.escape(b["title"])}</span></a>' for b in bookmarks[:12])
    bg, fg, card = ("#0F0D17", "#ECEBF5", "rgba(255,255,255,.06)") if dark else ("#F4F3FA", "#1C1A2B", "rgba(0,0,0,.05)")
    action = html.escape(engine_url.split("?")[0])
    param = engine_url.split("?")[1].split("=")[0] if "?" in engine_url else "q"
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{labels['title']}</title><style>
body{{margin:0;height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;
font-family:Inter,'Noto Sans',sans-serif;color:{fg};
background:radial-gradient(ellipse at 20% 20%,rgba(168,85,247,.35),transparent 55%),
radial-gradient(ellipse at 80% 80%,rgba(59,130,246,.30),transparent 55%),{bg};}}
h1{{font-weight:700;font-size:44px;margin:0 0 6px;letter-spacing:-1px}}
h1 span{{background:linear-gradient(90deg,#A855F7,#3B82F6);-webkit-background-clip:text;color:transparent}}
p{{opacity:.6;margin:0 0 28px}}
form{{width:min(620px,86vw)}}
input{{width:100%;box-sizing:border-box;padding:16px 24px;border-radius:999px;border:1px solid rgba(127,127,127,.3);
font-size:17px;background:{card};color:{fg};outline:none;backdrop-filter:blur(12px)}}
input:focus{{border-color:#7B61FF;box-shadow:0 0 0 4px rgba(123,97,255,.25)}}
.grid{{display:grid;grid-template-columns:repeat(6,96px);gap:14px;margin-top:38px}}
.tile{{display:flex;flex-direction:column;align-items:center;gap:8px;text-decoration:none;color:{fg};padding:12px 4px;border-radius:16px}}
.tile:hover{{background:{card}}}
.ic{{width:52px;height:52px;border-radius:16px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:22px;
color:white;background:linear-gradient(135deg,#A855F7,#3B82F6)}}
.t{{font-size:12px;max-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;opacity:.85}}
</style></head><body>
<h1>Nova<span>Browser</span></h1><p>{labels['tagline']}</p>
<form action="{action}" method="get"><input name="{param}" placeholder="{labels['search']}" autofocus autocomplete="off"></form>
<div class="grid">{tiles}</div></body></html>"""
