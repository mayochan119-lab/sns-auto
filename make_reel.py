"""ルナのリール（文字が順番に出る縦長動画）を作る。

  python make_reel.py videos/renai/01_彼から連絡が来ないあなたへ.yaml

YAML に場面（テキストと秒数）を書くと、同じ名前の .mp4 と、
カバー画像（.cover.jpg = 最初の場面）を作る。最初のフレームは必ずカバーの場面になる。
"""

import math
import random
import subprocess
import sys
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 24
FADE = 0.45  # 場面の切り替えの秒数
MINCHO = "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"
ROOT = Path(__file__).parent

INK = (255, 240, 250)
GLOW = (255, 60, 200)
ACCENT = (255, 150, 220)
GOLD = (214, 176, 120)


def font(size):
    return ImageFont.truetype(MINCHO, size, index=2)  # ProN W6


def background(seed=7):
    """深い紫の夜空に、ピンクのもや・星・細い金の枠。"""
    rnd = random.Random(seed)
    y = np.linspace(0, 1, H)[:, None]
    top, bottom = np.array([20, 4, 22]), np.array([44, 8, 38])
    base = (top * (1 - y) + bottom * y)[:, :, None].transpose(0, 2, 1).repeat(W, axis=1)
    img = Image.fromarray(base.astype("uint8"))
    haze = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(haze)
    for _ in range(9):
        cx, cy = rnd.randint(-200, W + 200), rnd.randint(0, H)
        r = rnd.randint(220, 520)
        c = rnd.choice([(150, 30, 120), (110, 20, 140), (170, 40, 100)])
        d.ellipse((cx - r, cy - r * 0.6, cx + r, cy + r * 0.6), fill=c)
    haze = haze.filter(ImageFilter.GaussianBlur(160))
    img = Image.blend(img, haze, 0.5)
    d = ImageDraw.Draw(img)
    m = 46
    d.rectangle((m, m, W - m, H - m), outline=GOLD + (0,), width=2)
    d.rectangle((m + 14, m + 14, W - m - 14, H - m - 14), outline=(120, 90, 70), width=1)
    return img


def stars(seed=11, n=140):
    rnd = random.Random(seed)
    return [(rnd.randint(60, W - 60), rnd.randint(60, H - 60), rnd.uniform(1.0, 3.2), rnd.uniform(0, math.tau), rnd.uniform(0.6, 1.8)) for _ in range(n)]


def draw_stars(img, star_list, t):
    d = ImageDraw.Draw(img)
    for x, y, r, phase, speed in star_list:
        a = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(phase + t * speed * 2))
        c = tuple(int(v * a) for v in (255, 220, 245))
        d.ellipse((x - r, y - r, x + r, y + r), fill=c)


def text_layer(lines, size, y_center, emphasis=()):
    """文字のレイヤー（RGBA）を返す。ピンクの光を後ろにぼかして重ねる。"""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    fonts = [font(int(size * (1.18 if i in emphasis else 1))) for i in range(len(lines))]
    heights = [f.getbbox(l or "あ")[3] for f, l in zip(fonts, lines)]
    gap = int(size * 0.55)
    total = sum(heights) + gap * (len(lines) - 1)
    y = y_center - total // 2
    dl, dg = ImageDraw.Draw(layer), ImageDraw.Draw(glow)
    for i, (line, f, h) in enumerate(zip(lines, fonts, heights)):
        w = f.getlength(line)
        x = (W - w) / 2
        color = ACCENT if i in emphasis else INK
        dg.text((x, y), line, font=f, fill=GLOW + (255,))
        dl.text((x, y), line, font=f, fill=color + (255,))
        y += h + gap
    wide = glow.filter(ImageFilter.GaussianBlur(size * 0.45))
    near = glow.filter(ImageFilter.GaussianBlur(size * 0.12))
    out = Image.alpha_composite(wide, wide)
    out = Image.alpha_composite(out, near)
    out = Image.alpha_composite(out, near)
    return Image.alpha_composite(out, layer)


def moon_layer(y_center, r=120):
    """細い三日月（ルナの画像の締めページにある月と同じ雰囲気）を光らせて描く。"""
    cx = W // 2
    shape = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(shape)
    d.ellipse((cx - r, y_center - r, cx + r, y_center + r), fill=255)
    off = int(r * 0.42)
    d.ellipse((cx - r + off, y_center - r - int(r * 0.18), cx + r + off, y_center + r - int(r * 0.18)), fill=0)
    body = Image.new("RGBA", (W, H), ACCENT + (0,))
    body.putalpha(shape)
    glow = Image.new("RGBA", (W, H), GLOW + (0,))
    glow.putalpha(shape.filter(ImageFilter.GaussianBlur(r * 0.35)))
    layer = Image.alpha_composite(Image.alpha_composite(glow, glow), body)
    # まわりに小さな星をいくつか
    d = ImageDraw.Draw(layer)
    for dx, dy, sr in [(-r * 1.7, -r * 0.6, 5), (r * 1.6, -r * 0.9, 6), (r * 1.3, r * 0.9, 4), (-r * 1.3, r * 1.0, 4)]:
        x, y = cx + dx, y_center + dy
        d.line((x - sr * 3, y, x + sr * 3, y), fill=INK + (230,), width=2)
        d.line((x, y - sr * 3, x, y + sr * 3), fill=INK + (230,), width=2)
    return layer


def scene_layer(scene):
    """場面の土台のレイヤーと、あとから順番に出てくる項目 [(出る秒, レイヤー)] を返す。"""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    size = scene.get("size", 84)
    y = scene.get("y", H // 2)
    if scene.get("moon"):
        layer = Image.alpha_composite(layer, moon_layer(y - 330))
        y += 120
    if scene.get("text"):
        layer = Image.alpha_composite(layer, text_layer(scene["text"].split("\n"), size, y, set(scene.get("emphasis", []))))
    if scene.get("note"):
        layer = Image.alpha_composite(layer, text_layer(scene["note"].split("\n"), 46, H - 330))
    items = []
    for item in scene.get("items", []):
        lay = text_layer(item["text"].split("\n"), item.get("size", 70), item["y"], set(item.get("emphasis", [])))
        if item.get("sub"):
            lay = Image.alpha_composite(lay, text_layer(item["sub"].split("\n"), item.get("sub_size", 40), item["y"] + item.get("sub_gap", 78)))
        items.append((item.get("at", 0.0), lay))
    return layer, items


def main(spec_path):
    spec_path = Path(spec_path)
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    out = spec_path.with_suffix(".mp4")
    bg, star_list = background(spec.get("seed", 7)), stars(spec.get("seed", 7) + 4)
    layers = [scene_layer(s) for s in spec["scenes"]]
    times = []
    t = 0.0
    for s in spec["scenes"]:
        times.append((t, t + s["seconds"]))
        t += s["seconds"]
    total = t
    writer = imageio_ffmpeg.write_frames(
        str(out), (W, H), fps=FPS, codec="libx264", quality=None,
        output_params=["-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
    )
    writer.send(None)
    first = None
    for n in range(int(total * FPS)):
        now = n / FPS
        frame = bg.copy()
        draw_stars(frame, star_list, now)
        frame = frame.convert("RGBA")
        for i, (a, b) in enumerate(times):
            if i == 0:
                alpha = 1.0 if now < b - FADE else max(0.0, (b - now) / FADE)
            else:
                alpha = min(1.0, max(0.0, (now - a + FADE) / FADE)) if now < b - FADE or i == len(times) - 1 else max(0.0, (b - now) / FADE)
            if alpha <= 0:
                continue
            base, items = layers[i]
            parts = [(alpha, base)]
            for at, lay in items:
                a2 = alpha * min(1.0, max(0.0, (now - a - at) / 0.35))
                if a2 > 0:
                    parts.append((a2, lay))
            for al, lay in parts:
                if al < 1:
                    lay = lay.copy()
                    lay.putalpha(lay.getchannel("A").point(lambda v, al=al: int(v * al)))
                frame = Image.alpha_composite(frame, lay)
        rgb = frame.convert("RGB")
        if n == 0:
            first = rgb
        writer.send(np.asarray(rgb).tobytes())
    writer.close()
    first.save(spec_path.with_suffix(".cover.jpg"), quality=92)
    print(f"{out}  {total:.1f}秒")


if __name__ == "__main__":
    main(sys.argv[1])
