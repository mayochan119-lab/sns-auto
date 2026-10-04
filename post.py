"""予約投稿スクリプト。

schedule/*.yaml を読み、時刻が来ていて approved: true の投稿を
Instagram / Threads に投稿する。投稿済みのものは posted.json に記録する。

使い方:
  python post.py           # 期限が来た投稿を実行
  python post.py --dry-run # 投稿せずに、何が投稿されるかだけ表示
  python post.py --check   # 予定ファイルの書き方をチェック
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
import yaml

ROOT = Path(__file__).parent
SCHEDULE_DIR = ROOT / "schedule"
POSTED_FILE = ROOT / "posted.json"
JST = ZoneInfo("Asia/Tokyo")

# 投稿の種類ごとの時刻（日本時間）
SLOTS = {
    "threads_morning": dt.time(7, 0),
    "instagram": dt.time(20, 0),
    "threads_night": dt.time(21, 0),
}
# 予定時刻からこれ以上遅れたら投稿しない（古い投稿が突然出ないように）
MAX_DELAY = dt.timedelta(hours=6)

IG_API = "https://graph.instagram.com/" + os.environ.get("IG_API_VERSION", "v23.0")
TH_API = "https://graph.threads.net/v1.0"

THREADS_MAX_CHARS = 500
IG_MAX_CHARS = 2200
IG_MAX_HASHTAGS = 30


# ---------- 予定ファイルの読み込み ----------

def load_posts():
    """schedule/*.yaml から投稿の一覧を返す。"""
    posts = []
    for path in sorted(SCHEDULE_DIR.glob("*.yaml")):
        if path.name.startswith("見本"):
            continue
        days = yaml.safe_load(path.read_text(encoding="utf-8")) or []
        for day in days:
            date = day["date"]
            if isinstance(date, str):
                date = dt.date.fromisoformat(date)
            for slot, slot_time in SLOTS.items():
                item = day.get(slot)
                if not item:
                    continue
                posts.append({
                    "id": f"{date.isoformat()}_{slot}",
                    "slot": slot,
                    "due": dt.datetime.combine(date, slot_time, tzinfo=JST),
                    "file": path.name,
                    **item,
                })
    return posts


def check_post(post):
    """問題点のリストを返す（空なら OK）。"""
    errors = []
    if post["slot"] == "instagram":
        caption = post.get("caption") or ""
        if not post.get("image"):
            errors.append("画像 (image) がありません。インスタは画像が必須です")
        elif not (ROOT / post["image"]).exists():
            errors.append(f"画像ファイルが見つかりません: {post['image']}")
        if not caption.strip():
            errors.append("キャプション (caption) が空です")
        if len(caption) > IG_MAX_CHARS:
            errors.append(f"キャプションが長すぎます ({len(caption)}/{IG_MAX_CHARS}文字)")
        if caption.count("#") > IG_MAX_HASHTAGS:
            errors.append(f"ハッシュタグが多すぎます (最大{IG_MAX_HASHTAGS}個)")
    else:
        text = post.get("text") or ""
        if not text.strip():
            errors.append("本文 (text) が空です")
        if len(text) > THREADS_MAX_CHARS:
            errors.append(f"本文が長すぎます ({len(text)}/{THREADS_MAX_CHARS}文字)")
        if post.get("image") and not (ROOT / post["image"]).exists():
            errors.append(f"画像ファイルが見つかりません: {post['image']}")
    return errors


def load_posted():
    if POSTED_FILE.exists():
        return json.loads(POSTED_FILE.read_text(encoding="utf-8"))
    return {}


def save_posted(posted):
    POSTED_FILE.write_text(
        json.dumps(posted, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


# ---------- 画像のアップロード（Cloudinary） ----------

def upload_image(rel_path):
    """画像を Cloudinary に上げ、インスタ用の JPEG の公開 URL を返す。"""
    cloud = os.environ["CLOUDINARY_CLOUD_NAME"]
    key = os.environ["CLOUDINARY_API_KEY"]
    secret = os.environ["CLOUDINARY_API_SECRET"]
    data = (ROOT / rel_path).read_bytes()
    # 同じ画像は同じ名前で上書きする
    public_id = "sns/" + hashlib.sha1(data).hexdigest()[:16]
    timestamp = str(int(time.time()))
    to_sign = f"overwrite=true&public_id={public_id}&timestamp={timestamp}{secret}"
    res = requests.post(
        f"https://api.cloudinary.com/v1_1/{cloud}/image/upload",
        data={
            "api_key": key,
            "timestamp": timestamp,
            "public_id": public_id,
            "overwrite": "true",
            "signature": hashlib.sha1(to_sign.encode()).hexdigest(),
        },
        files={"file": (Path(rel_path).name, data)},
        timeout=60,
    )
    res.raise_for_status()
    # インスタは JPEG のみ対応なので、拡張子を .jpg にして変換させる
    return f"https://res.cloudinary.com/{cloud}/image/upload/{public_id}.jpg"


# ---------- Instagram ----------

def api_call(method, url, **params):
    res = requests.request(method, url, params=params, timeout=60)
    if not res.ok:
        raise RuntimeError(f"{res.status_code} {res.text}")
    return res.json()


def wait_until_ready(url, token, field):
    for _ in range(30):
        status = api_call("GET", url, fields=field, access_token=token).get(field)
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"メディアの準備に失敗しました: {status}")
        time.sleep(5)
    raise RuntimeError("メディアの準備がタイムアウトしました")


def post_instagram(post):
    token = os.environ["IG_ACCESS_TOKEN"]
    image_url = upload_image(post["image"])
    container = api_call(
        "POST", f"{IG_API}/me/media",
        image_url=image_url, caption=post["caption"], access_token=token,
    )["id"]
    wait_until_ready(f"{IG_API}/{container}", token, "status_code")
    return api_call(
        "POST", f"{IG_API}/me/media_publish",
        creation_id=container, access_token=token,
    )["id"]


# ---------- Threads ----------

def post_threads(post):
    token = os.environ["THREADS_ACCESS_TOKEN"]
    params = {"text": post["text"], "access_token": token}
    if post.get("image"):
        params.update(media_type="IMAGE", image_url=upload_image(post["image"]))
    else:
        params["media_type"] = "TEXT"
    container = api_call("POST", f"{TH_API}/me/threads", **params)["id"]
    wait_until_ready(f"{TH_API}/{container}", token, "status")
    return api_call(
        "POST", f"{TH_API}/me/threads_publish",
        creation_id=container, access_token=token,
    )["id"]


# ---------- メイン ----------

def summary(post):
    body = post.get("caption") or post.get("text") or ""
    return body.strip().splitlines()[0][:40] if body.strip() else "(本文なし)"


def run_check(posts):
    problems = 0
    for post in posts:
        for err in check_post(post):
            print(f"❌ {post['file']} {post['id']}: {err}")
            problems += 1
    waiting = [p for p in posts if not p.get("approved")]
    print(f"\n投稿 {len(posts)}件 / 未承認 {len(waiting)}件 / 問題 {problems}件")
    return problems == 0


def run_post(posts, dry_run):
    now = dt.datetime.now(JST)
    posted = load_posted()
    failed = False
    for post in sorted(posts, key=lambda p: p["due"]):
        if post["id"] in posted or not post.get("approved"):
            continue
        if post["due"] > now:
            continue
        if now - post["due"] > MAX_DELAY:
            print(f"⏭  {post['id']}: 予定時刻を{MAX_DELAY}以上過ぎたのでスキップ")
            continue
        errors = check_post(post)
        if errors:
            print(f"❌ {post['id']}: {' / '.join(errors)}")
            failed = True
            continue
        if dry_run:
            print(f"[dry-run] {post['id']}: {summary(post)}")
            continue
        try:
            if post["slot"] == "instagram":
                media_id = post_instagram(post)
            else:
                media_id = post_threads(post)
        except Exception as e:  # 1件失敗しても他の投稿は続ける
            print(f"❌ {post['id']}: 投稿に失敗しました: {e}")
            failed = True
            continue
        posted[post["id"]] = {"media_id": media_id, "at": now.isoformat(timespec="seconds")}
        save_posted(posted)
        print(f"✅ {post['id']}: {summary(post)}")
    return not failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    posts = load_posts()
    ok = run_check(posts) if args.check else run_post(posts, args.dry_run)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
