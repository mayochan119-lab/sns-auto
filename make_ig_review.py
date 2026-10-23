"""インスタの予定を、横スワイプで見られる確認ページにする。

  python make_ig_review.py schedule/renai-instagram-1024.yaml renai review/luna-instagram-1024.html "ルナのインスタ予定"
"""

import base64
import html
import io
import sys
from pathlib import Path

import cv2
import yaml
from PIL import Image

WD = "月火水木金土日"
COLOR = {"seiza": ("#9A6C1E", "#DDB264"), "renai": ("#B0436F", "#E77FAE")}


def uri(im):
    im = im.convert("RGB")
    im.thumbnail((480, 600))
    b = io.BytesIO()
    im.save(b, "JPEG", quality=70)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def reel_frames(v, n=5):
    cap = cv2.VideoCapture(v)
    total = cap.get(cv2.CAP_PROP_FRAME_COUNT) / 24
    out = []
    for k in range(n):
        cap.set(cv2.CAP_PROP_POS_MSEC, (0 if k == 0 else total * k / n + 1) * 1000)
        ok, f = cap.read()
        if ok:
            out.append(Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)))
    return out


def main(src, acc, out, title):
    data = yaml.safe_load(open(src))
    cards = []
    for day in sorted(data, key=lambda x: str(x["date"])):
        d = day["date"]
        ig = day[acc]["instagram"]
        if "video" in ig:
            imgs, kind = reel_frames(ig["video"]), "リール"
        else:
            folder = Path(ig["images"][0])
            imgs = [Image.open(f) for f in sorted(folder.glob("*.jpg"), key=lambda f: int(f.stem))]
            kind = f"画像{len(imgs)}枚"
        strip = "".join(f'<img class="{"reel" if kind == "リール" else ""}" src="{uri(im)}" alt="">' for im in imgs)
        cap = html.escape(ig["caption"].strip())
        head = html.escape(ig["caption"].strip().splitlines()[0])
        cards.append(f'<section><h2>{d.month}/{d.day}（{WD[d.weekday()]}）<span class="k">{kind}</span></h2><p class="t">{head}</p><div class="strip">{strip}</div><details><summary>キャプションを見る</summary><pre>{cap}</pre></details></section>')
    first, last = sorted(str(x["date"]) for x in data)[0], sorted(str(x["date"]) for x in data)[-1]
    light, dark = COLOR[acc]
    page = TEMPLATE.replace("__TITLE__", title).replace("__RANGE__", f"{int(first[5:7])}/{int(first[8:])}〜{int(last[5:7])}/{int(last[8:])}").replace("__LIGHT__", light).replace("__DARK__", dark).replace("__CARDS__", "".join(cards))
    Path(out).write_text(page)
    print(out, len(page) // 1024, "KB")


TEMPLATE = '''<title>__TITLE__</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Shippori+Mincho+B1:wght@700&family=Zen+Kaku+Gothic+New:wght@400;700&display=swap">
<style>
/* Layout: 日付ごとに、画像を横スワイプ。下にキャプション */
:root { --bg:#F3F1F6; --card:#fff; --ink:#211D33; --muted:#6B6580; --line:#DDD8E8; --acc:__LIGHT__;
  --display:"Shippori Mincho B1","Hiragino Mincho ProN",serif; --body:"Zen Kaku Gothic New","Hiragino Sans",system-ui,sans-serif; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg:#14131D; --card:#1D1C2A; --ink:#ECE9F6; --muted:#A39DBA; --line:#322F47; --acc:__DARK__; color-scheme:dark; } }
:root[data-theme="dark"] { --bg:#14131D; --card:#1D1C2A; --ink:#ECE9F6; --muted:#A39DBA; --line:#322F47; --acc:__DARK__; color-scheme:dark; }
* { box-sizing:border-box; }
body { background:var(--bg); color:var(--ink); font-family:var(--body); }
.wrap { max-width:900px; margin:0 auto; padding-inline:16px; padding-block:24px 48px; display:grid; gap:24px; }
h1,h2 { font-family:var(--display); margin:0; } h1 { font-size:1.5rem; } h2 { font-size:1.1rem; color:var(--acc); display:flex; gap:8px; align-items:baseline; }
.k { font-family:var(--body); font-size:.75rem; color:var(--muted); border:1px solid var(--line); border-radius:999px; padding:0 8px; }
p { margin:0; color:var(--muted); font-size:.85rem; }
section { display:grid; gap:8px; min-width:0; background:var(--card); border:1px solid var(--line); border-radius:12px; padding:12px; }
.strip { display:flex; gap:8px; overflow-x:auto; scroll-snap-type:x mandatory; padding-bottom:6px; }
.strip img { flex:0 0 min(62vw, 240px); width:min(62vw, 240px); aspect-ratio:4/5; object-fit:cover; border-radius:8px; scroll-snap-align:start; }
.strip img.reel { flex-basis:min(44vw, 170px); width:min(44vw, 170px); aspect-ratio:9/16; }
details summary { cursor:pointer; font-size:.85rem; color:var(--muted); }
pre { white-space:pre-wrap; overflow-wrap:anywhere; font-family:var(--body); font-size:.85rem; margin:6px 0 0; }
</style>
<div class="wrap"><header><h1>__TITLE__ __RANGE__</h1><p>毎日20:00。1行が「画像｜リール｜画像」になる順番です。リールは場面の一部を並べています。</p></header>__CARDS__</div>'''

if __name__ == "__main__":
    main(*sys.argv[1:5])
