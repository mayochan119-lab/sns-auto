"""短くてテンポの速いリール（7〜8秒）を作る。いちばん届いているレイの誕生日TOP5と同じ形で、
タイトル → 項目が下から順に積み上がる → 全部そろった画面でとまる。

  python make_fast_reel.py videos/renai/15_xxx.yaml

今の make_reel.py 用の spec をそのまま読む（誕生日TOP5 も朝の連載も）。
同じ名前の .mp4 と .cover.jpg（最初の画面）を作り直す。
"""

import math
import random
import sys
from pathlib import Path

import imageio_ffmpeg
import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFilter

import make_reel as mr
from add_audio import add_audio

W, H, FPS = mr.W, mr.H, mr.FPS
LEFT = 110
IN = 0.28  # 項目がふわっと出てくる秒数


def bezier(p, n=90):
    t = np.linspace(0, 1, n)[:, None]
    p = np.array(p, dtype=float)
    return (1 - t) ** 3 * p[0] + 3 * (1 - t) ** 2 * t * p[1] + 3 * (1 - t) * t ** 2 * p[2] + t ** 3 * p[3]


def background(seed):
    """黒い夜空に、右上と左下から流れる光の帯と、細かい光の粒。"""
    rnd = random.Random(seed)
    img = Image.new("RGB", (W, H), (5, 4, 9))
    haze = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(haze)
    for _ in range(5):
        cx, cy, r = rnd.randint(0, W), rnd.randint(0, H), rnd.randint(260, 520)
        d.ellipse((cx - r, cy - r * 0.6, cx + r, cy + r * 0.6), fill=tuple(int(v * 0.35) for v in rnd.choice(mr.HAZE)))
    img = Image.blend(img, haze.filter(ImageFilter.GaussianBlur(180)), 0.6)
    band = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(band)
    for p0, p1, p2, p3 in (((W * 0.30, -60), (W * 0.62, H * 0.06), (W * 0.80, H * 0.02), (W + 60, H * 0.24)),
                           ((-60, H * 0.74), (W * 0.18, H * 0.98), (W * 0.48, H * 0.86), (W * 0.74, H + 60))):
        for i in range(46):
            off = (i - 23) * 5 + rnd.uniform(-2, 2)
            wob = rnd.uniform(-40, 40)
            pts = bezier([(p0[0], p0[1] + off), (p1[0] + wob, p1[1] + off), (p2[0] - wob, p2[1] + off * 1.4), (p3[0], p3[1] + off)])
            c = mr.ACCENT if i % 3 else mr.GLOW
            a = 0.25 + 0.75 * math.exp(-((i - 23) / 11) ** 2)
            d.line([tuple(q) for q in pts], fill=tuple(int(v * a) for v in c), width=1)
    glow = band.filter(ImageFilter.GaussianBlur(14))
    img = Image.fromarray(np.clip(np.asarray(img, float) + np.asarray(band, float) * 0.9 + np.asarray(glow, float) * 1.6, 0, 255).astype("uint8"))
    d = ImageDraw.Draw(img)
    for _ in range(260):
        x, y = rnd.randint(0, W), rnd.randint(0, H)
        r = rnd.choice([1, 1, 1, 2])
        c = tuple(int(v * rnd.uniform(0.35, 1)) for v in mr.STAR)
        d.ellipse((x - r, y - r, x + r, y + r), fill=c)
    return img


def glowing(draw, size):
    """draw(ink, glow) で描いた文字に、ぼかした光を重ねたレイヤーを返す。"""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw(ImageDraw.Draw(layer), ImageDraw.Draw(glow))
    out = Image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(size * 0.35)), glow.filter(ImageFilter.GaussianBlur(size * 0.1)))
    return Image.alpha_composite(out, layer)


def fit(text, max_w, size, min_size=40):
    while size > min_size and mr.font(size).getlength(text) > max_w:
        size -= 2
    return size


def wrap(parts, size, max_w):
    """spec の改行位置（言葉の切れ目）を生かして、幅に収まるだけ行をつなげる。"""
    f, lines = mr.font(size), []
    for part in parts:
        if lines and f.getlength(lines[-1] + part) <= max_w:
            lines[-1] += part
        else:
            lines.append(part)
    return lines


def header(lines):
    size = fit(max(lines, key=len), W - 2 * LEFT, 76)
    return mr.text_layer(lines, size, 120 + int(len(lines) * size * 0.8), {len(lines) - 1})


def footer(note):
    lines = [l for l in note.split("\n") if l]
    size = fit(max(lines, key=len), W - 2 * LEFT, 56)
    return mr.text_layer(lines, size, 1725, {len(lines) - 1})


def rank_row(rank, day, sub, y, top=False, row_h=220):
    def draw(dl, dg):
        f_rank, f_day, f_sub = mr.font(62), mr.font(124 if top else 104), mr.font(42)
        col = mr.ACCENT if top else mr.INK
        for d, c in ((dg, mr.GLOW), (dl, mr.GOLD if not top else mr.ACCENT)):
            d.text((LEFT, y + 30), rank, font=f_rank, fill=c + (255,))
        for d, c in ((dg, mr.GLOW), (dl, col)):
            d.text((LEFT + 190, y), day, font=f_day, fill=c + (255,))
        dl.text((LEFT + 196, y + (150 if top else 128)), sub, font=f_sub, fill=mr.INK + (235,))
        dl.line((LEFT - 10, y + row_h - 14, W - LEFT + 10, y + row_h - 14), fill=mr.GOLD + (110,), width=2)
    return glowing(draw, 104)


def trait_block(num, text, note, y):
    def draw(dl, dg):
        f_num, f_txt, f_note = mr.font(84), mr.font(62), mr.font(40)
        for d, c in ((dg, mr.GLOW), (dl, mr.ACCENT)):
            d.text((LEFT, y - 6), num, font=f_num, fill=c + (255,))
        yy = y
        for line in wrap(text.split("\n"), 62, W - LEFT - 120 - 70):
            for d, c in ((dg, mr.GLOW), (dl, mr.INK)):
                d.text((LEFT + 120, yy), line, font=f_txt, fill=c + (255,))
            yy += 82
        if note:
            dl.text((LEFT + 124, yy + 6), note, font=f_note, fill=mr.INK + (220,))
    return glowing(draw, 70)


def build(spec):
    """(長さ, タイトルのレイヤー, 見出しのレイヤー, [(出る秒, レイヤー)]) を返す。"""
    sc = spec["scenes"]
    title = mr.text_layer(sc[0]["text"].split("\n"), min(sc[0].get("size", 110), 124), 860, set(sc[0].get("emphasis", [0])))
    if sc[0].get("note"):
        title = Image.alpha_composite(title, mr.text_layer(sc[0]["note"].split("\n"), 66, 1180, {0}))
    end_note = sc[-1].get("note", "")
    parts = []
    if len(sc) >= 2 and sc[1].get("items"):  # 誕生日TOP5
        head = header(sc[1]["text"].split("\n"))
        top = max(470, head.getbbox()[3] + 40)  # 見出しが3行のときは、順位を少し下げる
        items = sc[1]["items"]  # 5位 → 1位 の順
        row_h = min(220, (1640 - top) / len(items))  # 下の予告（明日20時は…）に重ならないように
        for k, it in enumerate(items):
            rank, day = it["text"].split("　", 1)
            y = int(top + (len(items) - 1 - k) * row_h)
            parts.append((1.1 + 0.6 * k, rank_row(rank, day.strip(), it.get("sub", ""), y, top=(k == len(items) - 1), row_h=row_h)))
        parts.append((4.3, footer(end_note)))
        return 7.0, title, head, parts
    # 朝の連載（特徴3つ）
    head = header([sc[0]["text"].replace("\n", "")])
    for k, s in enumerate(sc[1:4]):
        parts.append((1.1 + 1.0 * k, trait_block("①②③"[k], s["text"], s.get("note", ""), 480 + k * 360)))
    parts.append((4.1, footer(end_note)))
    return 8.0, title, head, parts


def fade(layer, a):
    if a >= 1:
        return layer
    out = layer.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * a)))
    return out


def main(spec_path):
    spec_path = Path(spec_path)
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    theme = spec.get("theme", "luna")
    mr.use_theme(theme)
    seed = spec.get("seed", 7)
    bg = background(seed).convert("RGBA")
    total, title, head, parts = build(spec)
    out = spec_path.with_suffix(".mp4")
    writer = imageio_ffmpeg.write_frames(str(out), (W, H), fps=FPS, codec="libx264", quality=None, macro_block_size=8,
                                         output_params=["-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"])
    writer.send(None)
    first = None
    for n in range(int(total * FPS)):
        t = n / FPS
        frame = bg.copy()
        a = 1.0 if t < 0.85 else max(0.0, 1 - (t - 0.85) / 0.25)  # タイトル → 見出しに切り替え
        if a > 0:
            frame = Image.alpha_composite(frame, fade(title, a))
        if t > 0.85:
            frame = Image.alpha_composite(frame, fade(head, min(1.0, (t - 0.85) / 0.25)))
        for at, lay in parts:
            if t >= at:
                p = min(1.0, (t - at) / IN)
                shift = int((1 - p) * 30)
                lay2 = fade(lay, p)
                if shift:
                    lay2 = lay2.transform(lay2.size, Image.AFFINE, (1, 0, 0, 0, 1, -shift))
                frame = Image.alpha_composite(frame, lay2)
        rgb = frame.convert("RGB")
        if n == 0:
            first = rgb
        writer.send(np.asarray(rgb).tobytes())
    writer.close()
    add_audio(out, theme)
    first.save(spec_path.with_suffix(".cover.jpg"), quality=92)
    print(f"{out}  {total:.1f}秒")


if __name__ == "__main__":
    for p in sys.argv[1:]:
        main(p)
