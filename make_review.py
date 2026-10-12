"""Threads の下書きを、スマホで読みやすい確認用ページにする。

  python make_review.py schedule/threads-2026-10-14.yaml review/threads-1014.html
"""

import base64
import datetime as dt
import html
import io
import sys
from pathlib import Path

import yaml
from PIL import Image

FMT = {"R1": "参加型ランキング", "R2": "星座別あるある", "R3": "意外性TOP3", "R4": "4グループ", "R5": "二択", "R6": "季節ネタ",
       "L1": "共感トーク", "L2": "彼の本音3つ", "L3": "〇〇な人へ", "L4": "本命チェック", "L5": "直感で選ぶ", "L6": "私だけ？あるある", "L7": "W逆行×復縁",
       "N1": "通知画像＋ひと言", "N2": "2行の問いかけ", "N3": "見たあなたへ"}
SLOT = {"threads_morning": "朝 7:00", "threads_noon": "昼 12:00", "threads_night": "夜 21:00"}
WD = "月火水木金土日"


def thumb(rel):
    im = Image.open(rel).convert("RGB")
    im.thumbnail((600, 600))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=75)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def formats(src):
    """予定ファイルのコメント（# R1 など）から、投稿の型を拾う。"""
    out, date, acc = {}, None, None
    for line in src.splitlines():
        if line.startswith("- date:"):
            date = line.split(":", 1)[1].strip()
        elif line.startswith("  ") and not line.startswith("    ") and line.strip().endswith(":"):
            acc = line.strip()[:-1]
        elif line.startswith("    threads_") and "#" in line:
            slot, fmt = line.strip().split(":", 1)
            out[(date, acc, slot)] = fmt.replace("#", "").strip()
    return out


def main(src_path, out_path):
    src = Path(src_path).read_text()
    data = yaml.safe_load(src)
    fmt_of = formats(src)
    days, nav = [], []
    for day in data:
        d = day["date"] if isinstance(day["date"], dt.date) else dt.date.fromisoformat(day["date"])
        cols = []
        for acc, name in (("seiza", "レイ（星座）"), ("renai", "ルナ（恋愛）")):
            cards = []
            for slot in ("threads_morning", "threads_noon", "threads_night"):
                p = (day.get(acc) or {}).get(slot)
                if not p:
                    continue
                fmt = fmt_of.get((d.isoformat(), acc, slot), "")
                img = f'<img src="{thumb(p["image"])}" alt="通知風の画像">' if p.get("image") else ""
                state = "承認済み" if p.get("approved") else "未承認"
                cards.append(f'<article class="card"><div class="meta"><span class="slot">{SLOT[slot]}</span><span class="fmt">{html.escape(FMT.get(fmt, fmt))}</span><span class="state">{state}</span></div><p class="text">{html.escape(p["text"].strip())}</p>{img}</article>')
            cols.append(f'<section class="col {acc}"><h3>{name}</h3>{"".join(cards)}</section>')
        days.append(f'<section class="day" id="d{d.day}"><h2>{d.month}月{d.day}日（{WD[d.weekday()]}）</h2><div class="cols">{"".join(cols)}</div></section>')
        nav.append(f'<a href="#d{d.day}">{d.day}日</a>')
    first, last = data[0]["date"], data[-1]["date"]
    title = f"Threads下書き {first.month}/{first.day}〜"
    page = TEMPLATE.replace("__TITLE__", title).replace("__RANGE__", f"{first.month}/{first.day}〜{last.month}/{last.day}").replace("__NAV__", "".join(nav)).replace("__DAYS__", "".join(days))
    Path(out_path).parent.mkdir(exist_ok=True)
    Path(out_path).write_text(page)
    print(out_path)


TEMPLATE = '''<title>__TITLE__</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Shippori+Mincho+B1:wght@700&family=Zen+Kaku+Gothic+New:wght@400;500;700&display=swap">
<style>
/* Layout: 日付ごとに、左にレイ・右にルナ（スマホでは縦に並ぶ） */
:root { --bg:#F3F1F6; --card:#FFFFFF; --ink:#211D33; --muted:#6B6580; --line:#DDD8E8; --rei:#9A6C1E; --luna:#B0436F;
  --display:"Shippori Mincho B1","Hiragino Mincho ProN",serif; --body:"Zen Kaku Gothic New","Hiragino Sans",system-ui,sans-serif; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#14131D; --card:#1D1C2A; --ink:#ECE9F6; --muted:#A39DBA; --line:#322F47; --rei:#DDB264; --luna:#E77FAE; color-scheme:dark; } }
:root[data-theme="dark"] { --bg:#14131D; --card:#1D1C2A; --ink:#ECE9F6; --muted:#A39DBA; --line:#322F47; --rei:#DDB264; --luna:#E77FAE; color-scheme:dark; }
* { box-sizing:border-box; }
body { background:var(--bg); color:var(--ink); font-family:var(--body); font-size:15px; line-height:1.65; }
.wrap { max-width:1100px; margin:0 auto; padding-inline:16px; padding-block:24px 64px; display:grid; gap:28px; }
h1,h2 { font-family:var(--display); margin:0; text-wrap:balance; }
h1 { font-size:1.7rem; } h2 { font-size:1.2rem; border-bottom:1px solid var(--line); padding-bottom:6px; }
header p { margin:6px 0 0; color:var(--muted); font-size:.9rem; }
nav { display:flex; flex-wrap:wrap; gap:8px; position:sticky; top:env(safe-area-inset-top,0px); background:var(--bg); padding-block:8px; z-index:2; }
nav a { color:var(--ink); text-decoration:none; border:1px solid var(--line); background:var(--card); border-radius:999px; padding:2px 12px; font-size:.85rem; }
.day { display:grid; gap:12px; scroll-margin-top:56px; }
.cols { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; }
.col { display:grid; gap:10px; align-content:start; min-width:0; }
.col h3 { margin:0; font-size:.95rem; }
.col.seiza h3 { color:var(--rei); } .col.renai h3 { color:var(--luna); }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px 14px; display:grid; gap:8px; min-width:0; }
.col.seiza .card { box-shadow:inset 3px 0 0 var(--rei); } .col.renai .card { box-shadow:inset 3px 0 0 var(--luna); }
.meta { display:flex; gap:8px; flex-wrap:wrap; font-size:.78rem; color:var(--muted); }
.slot { font-weight:700; color:var(--ink); }
.fmt, .state { border:1px solid var(--line); border-radius:999px; padding:0 8px; }
.text { margin:0; white-space:pre-wrap; overflow-wrap:anywhere; }
.card img { width:100%; border-radius:10px; display:block; }
@media (max-width:760px) { .cols { grid-template-columns:minmax(0,1fr); } }
</style>
<div class="wrap">
<header><h1>Threads下書き __RANGE__</h1><p>直したいものは「〇日の朝・ルナ」のように教えてください。</p></header>
<nav>__NAV__</nav>
__DAYS__
</div>'''

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
