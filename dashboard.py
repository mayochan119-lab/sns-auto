"""予約投稿のダッシュボード（HTML）を作る。

  python dashboard.py   # dashboard/index.html を作る

予定ファイルと posted.json から、投稿予定・投稿済み・インスタのグリッドの見え方を
1枚のページにまとめる。画像は小さなサムネイルにしてページに埋め込む。
"""

import base64
import datetime as dt
import html
import io
import json
from pathlib import Path

import cv2
from PIL import Image

import post as P

OUT = P.ROOT / "dashboard" / "index.html"
HANDLES = {"seiza": "rei.seizauranai", "renai": "luna.loveuranai"}
SLOT_LABELS = {"threads_morning": "Threads 朝", "instagram": "Instagram", "threads_night": "Threads 夜"}
TOKEN_EXPIRES = dt.date(2026, 12, 5)  # 2026-10-06 に作った鍵の期限（60日）

_thumb_cache = {}


def thumb(rel, width=240):
    """画像（または動画の最初のフレーム）を小さな JPEG の data URI にする。"""
    if rel in _thumb_cache:
        return _thumb_cache[rel]
    path = P.ROOT / rel
    if path.suffix.lower() == ".mp4":
        ok, frame = cv2.VideoCapture(str(path)).read()
        im = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)) if ok else None
    else:
        im = Image.open(path)
    if im is None:
        return None
    im = im.convert("RGB")
    im.thumbnail((width, width * 2))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=72)
    uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    _thumb_cache[rel] = uri
    return uri


def describe(post, posted, now):
    images = P.post_images(post)
    if post.get("video"):
        kind, cover = "リール", post.get("cover") or post["video"]
    elif len(images) > 1:
        kind, cover = f"画像{len(images)}枚", images[0]
    elif images:
        kind, cover = "画像", images[0]
    else:
        kind, cover = "テキスト", None
    if post["id"] in posted:
        status, at = "posted", posted[post["id"]]["at"]
    elif not post.get("approved"):
        status, at = "draft", None
    elif now - post["due"] > P.MAX_DELAY:
        status, at = "missed", None
    else:
        status, at = "scheduled", None
    problems = P.check_post(post)
    body = (post.get("caption") or post.get("text") or "").strip()
    return {
        "id": post["id"],
        "account": post["account"],
        "handle": HANDLES.get(post["account"], post["account"]),
        "platform": post["platform"],
        "slot": SLOT_LABELS.get(post["id"].split("_", 2)[2], post["platform"]),
        "due": post["due"].isoformat(),
        "kind": kind,
        "thumb": thumb(cover) if cover else None,
        "title": body.splitlines()[0] if body else "(本文なし)",
        "body": body,
        "status": "problem" if problems and status != "posted" else status,
        "problems": problems,
        "postedAt": at,
    }


def main():
    now = dt.datetime.now(P.JST)
    accounts = P.load_accounts()
    posted = P.load_posted()
    posts = sorted(P.load_posts(), key=lambda p: (p["due"], p["account"]))
    items = [describe(p, posted, now) for p in posts]
    data = {
        "generatedAt": now.isoformat(timespec="minutes"),
        "tokenExpires": TOKEN_EXPIRES.isoformat(),
        "accounts": [{"id": k, "name": v["name"], "handle": HANDLES.get(k, k)} for k, v in accounts.items()],
        "posts": items,
    }
    template = (P.ROOT / "dashboard_template.html").read_text(encoding="utf-8")
    page = template.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"{OUT}  投稿 {len(items)}件  {OUT.stat().st_size // 1024}KB")


if __name__ == "__main__":
    main()
