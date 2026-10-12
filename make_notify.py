"""スマホの通知風の画像を作る（Threads の「引っかかり」投稿用）。

  python make_notify.py images/notify/kita.jpg "久しぶり。ずっと連絡できなくてごめん。" --theme pastel

LINE の通知に見えるよう、アイコンは LINE 風にしている（商標のリスクは本人に説明済み）。
送り主の名前はモザイクにして、誰からでも「あの人」に見えるようにする。
"""

import argparse
import glob
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1200, 400
SCALE = 2  # 2倍で描いてから縮めて、文字をなめらかにする

THEMES = {
    # 背景の色（ぼかした色の塊）, 文字の色, 「今」の色, 通知の板の色
    "night": ([(18, 40, 78), (40, 90, 140), (12, 24, 52), (70, 120, 170)], (238, 242, 250), (190, 200, 220), (255, 255, 255, 34)),
    "pastel": ([(214, 168, 170), (150, 200, 170), (226, 196, 170), (170, 210, 200)], (34, 34, 40), (90, 90, 100), (255, 255, 255, 70)),
    "lavender": ([(196, 182, 226), (232, 190, 214), (170, 160, 210), (220, 210, 240)], (40, 30, 60), (100, 90, 120), (255, 255, 255, 70)),
    "dusk": ([(60, 30, 70), (150, 70, 120), (30, 20, 50), (200, 110, 140)], (250, 238, 246), (220, 190, 210), (255, 255, 255, 30)),
}


def find_font(names):
    for name in names:
        hits = glob.glob(f"/System/Library/AssetsV2/**/{name}", recursive=True) + glob.glob(f"/System/Library/Fonts/**/{name}", recursive=True)
        if hits:
            return hits[0]
    raise SystemExit(f"フォントが見つかりません: {names}")


FONT_BOLD = find_font(["YuGothic-Bold.otf"])
FONT_MED = find_font(["YuGothic-Medium.otf"])


def background(colors, seed):
    rnd = random.Random(seed)
    img = Image.new("RGB", (W * SCALE, H * SCALE), colors[0])
    d = ImageDraw.Draw(img)
    for i in range(10):
        c = colors[i % len(colors)]
        cx, cy = rnd.randint(0, W * SCALE), rnd.randint(0, H * SCALE)
        r = rnd.randint(int(H * 0.6 * SCALE), int(H * 1.3 * SCALE))
        d.ellipse((cx - r, cy - r * 0.7, cx + r, cy + r * 0.7), fill=c)
    return img.filter(ImageFilter.GaussianBlur(120 * SCALE // 2))


def avatar(size):
    """水色の丸に、白く塗った人のシルエット（LINEの初期アイコン風）。"""
    av = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(av)
    d.ellipse((0, 0, size, size), fill=(190, 222, 238, 255))
    w = (255, 255, 255, 255)
    d.ellipse((size * 0.36, size * 0.22, size * 0.64, size * 0.50), fill=w)
    d.pieslice((size * 0.20, size * 0.56, size * 0.80, size * 1.16), 180, 360, fill=w)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(av, (0, 0), mask)
    return out


def badge(size):
    """緑の角丸の四角に、白い吹き出しと「LINE」の文字（LINEのアプリアイコン風）。"""
    b = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(b)
    d.rounded_rectangle((0, 0, size, size), radius=int(size * 0.24), fill=(6, 199, 85, 255), outline=(255, 255, 255, 255), width=max(2, size // 16))
    bw, bh = size * 0.74, size * 0.56
    x0, y0 = (size - bw) / 2, size * 0.17
    d.ellipse((x0, y0, x0 + bw, y0 + bh), fill=(255, 255, 255, 255))
    d.polygon([(x0 + bw * 0.62, y0 + bh * 0.86), (x0 + bw * 0.50, y0 + bh * 1.22), (x0 + bw * 0.80, y0 + bh * 0.80)], fill=(255, 255, 255, 255))
    f = ImageFont.truetype(FONT_BOLD, int(size * 0.20))
    tw = f.getlength("LINE")
    d.text(((size - tw) / 2, y0 + bh * 0.27), "LINE", font=f, fill=(6, 199, 85, 255))
    return b


def mosaic_name(draw_img, x, y, color, seed):
    """名前の部分をモザイクにする。"""
    rnd = random.Random(seed)
    block = 9 * SCALE
    n = rnd.randint(4, 6)
    d = ImageDraw.Draw(draw_img)
    for i in range(n):
        for j in range(3):
            shade = rnd.randint(-40, 40)
            c = tuple(max(0, min(255, v + shade)) for v in color[:3]) + (rnd.randint(110, 200),)
            d.rectangle((x + i * block, y + j * block, x + (i + 1) * block - 1, y + (j + 1) * block - 1), fill=c)
    d.rectangle((x + n * block + 6 * SCALE, y + block, x + n * block + 12 * SCALE, y + block + 4 * SCALE), fill=color[:3] + (150,))


def make(out, text, theme="pastel", seed=1, time_label="今"):
    colors, ink, sub, panel = THEMES[theme]
    img = background(colors, seed).convert("RGBA")
    # 通知の板（うっすら白）
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    pad = 34 * SCALE
    ImageDraw.Draw(layer).rounded_rectangle((pad, pad, W * SCALE - pad, H * SCALE - pad), radius=56 * SCALE, fill=panel)
    img = Image.alpha_composite(img, layer)

    av_size = 150 * SCALE
    ax, ay = pad + 36 * SCALE, (H * SCALE - av_size) // 2
    img.alpha_composite(avatar(av_size), (ax, ay))
    bsize = 62 * SCALE
    img.alpha_composite(badge(bsize), (ax + av_size - bsize + 8 * SCALE, ay + av_size - bsize + 8 * SCALE))

    tx = ax + av_size + 42 * SCALE
    mosaic_name(img, tx, ay + 22 * SCALE, ink, seed)
    d = ImageDraw.Draw(img)
    f_time = ImageFont.truetype(FONT_MED, 34 * SCALE)
    d.text((W * SCALE - pad - 70 * SCALE, pad + 34 * SCALE), time_label, font=f_time, fill=sub)

    # 本文：長ければ2行に折り返す
    max_w = W * SCALE - pad - 60 * SCALE - tx
    size = 42 * SCALE
    f = ImageFont.truetype(FONT_BOLD, size)
    def split(t, font):
        if font.getlength(t) <= max_w:
            return [t]
        fit = max(i for i in range(1, len(t)) if font.getlength(t[:i]) <= max_w)
        # 句読点のあとで折り返せるなら、そこで折る（1行目が短くなりすぎない範囲で）
        for i in range(fit, max(0, int(len(t) * 0.3)), -1):
            if t[i - 1] in "、。！？!?" and i < len(t):
                return [t[:i], t[i:]]
        # 句読点で行が始まらないようにする
        while fit > 1 and t[fit] in "、。！？!?」』）":
            fit -= 1
        return [t[:fit], t[fit:]]

    lines = split(text, f)
    while len(lines) > 1 and f.getlength(lines[1]) > max_w and size > 30 * SCALE:
        size -= 2 * SCALE
        f = ImageFont.truetype(FONT_BOLD, size)
        lines = split(text, f)
    y = ay + 78 * SCALE if len(lines) == 1 else ay + 62 * SCALE
    for line in lines:
        d.text((tx, y), line, font=f, fill=ink)
        y += int(size * 1.35)

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").resize((W, H), Image.LANCZOS).save(out, quality=92)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("text")
    ap.add_argument("--theme", default="pastel", choices=list(THEMES))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--time", default="今")
    a = ap.parse_args()
    print(make(a.out, a.text, a.theme, a.seed, a.time))
