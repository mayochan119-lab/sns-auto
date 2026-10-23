"""カルーセル（複数枚の画像投稿）を作る。

  python make_carousel.py stock/carousel-samples/rei_W逆行.yaml [--sheet]

YAML と同じ名前のフォルダに 1.jpg, 2.jpg, ...（1080x1350）を書き出す。
--sheet を付けると、全ページを横に並べた確認用画像（<名前>.contact.jpg）を YAML の隣に作る
（フォルダの中に置くと投稿に混ざるので、外に置く）。

YAML の書き方:
  theme: rei | luna          # rei = 紺と金の星空 / luna = 紫とピンクのネオン（make_reel.py と同じ雰囲気）
  seed: 3                    # 星の配置（省略可）
  backgrounds: [images/renai/backgrounds/bg1.jpg, ...]  # 用意した背景画像を順番に使う（省略可）
  slides:
    - type: cover            # 表紙: eyebrow / title / subtitle / note / art: wheel | moon
    - type: text             # icon / eyebrow / heading / body / emphasis: [行番号] / sections: [{label, text}] / note
    - type: list             # icon / eyebrow / heading / items（文字 or {text, sub}）/ style: number | check | dot | center / note
    - type: closing          # 最後のお礼ページ（文言は固定）
  icon: fire | earth | air | water | moon | wheel | star | heart | sparkle（図形で描く）

文字の中の書式:
  **ことば**  大きく明るく（強調）    ==ことば==  アクセント色
  :star: :heart: :letter: :moon: :bookmark: :sparkle:  文中に図形のアイコンを入れる
  空行 = 段落の区切り
絵文字はフォントで描けないので、⭐💌🌙❤🔖✨ などは図形に置きかえ、それ以外は取り除く。
長い行は枠の内側で自動的に縮小・折り返しする。
"""

import math
import random
import re
import sys
from collections import namedtuple
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1080, 1350
MINCHO = "/System/Library/Fonts/ヒラギノ明朝 ProN.ttc"
SAFE_L, SAFE_R, SAFE_T, SAFE_B = 118, W - 118, 124, H - 124  # 文字を置ける範囲
MAX_W = SAFE_R - SAFE_L
CX = W // 2
TAU = math.tau

THEMES = {
    "rei": {
        "head": (255, 234, 192), "ink": (240, 228, 206), "bright": (255, 248, 226),
        "accent": (226, 186, 112), "glow": (206, 148, 52), "line": (206, 170, 106),
        "frame": (200, 162, 96), "faint": (112, 90, 56), "star": (255, 240, 212),
        "passes": [(0.42, 0.55), (0.13, 0.7), (0.045, 0.45)],
        "emph": 1.16, "thanks": "star", "extra": 0.45,
        "sizes": {}, "closing": (62, 42, 58),
    },
    "luna": {
        "head": (255, 232, 248), "ink": (255, 226, 245), "bright": (255, 250, 254),
        "accent": (255, 150, 220), "glow": (255, 60, 200), "line": (255, 150, 220),
        "frame": (214, 176, 120), "faint": (120, 90, 70), "star": (255, 220, 245),
        "passes": [(0.45, 1.0), (0.45, 1.0), (0.12, 1.0), (0.12, 1.0), (0.05, 1.0)],
        "emph": 1.24, "thanks": "moon", "extra": 0.6,
        # ルナは見本の画像のように文字を大きく
        "sizes": {"title": 118, "subtitle": 50, "eyebrow": 34, "heading": 80, "body": 46, "label": 32,
                  "item": 52, "sub": 38, "note": 34, "small": 32},
        "closing": (72, 46, 66),
    },
}

# 役割ごとの 文字の大きさ / 行の間隔（文字の高さの倍率）/ 光の強さ / 色
ROLES = {
    "title": (112, 1.30, 1.0, "head"),
    "subtitle": (46, 1.50, 0.7, "head"),
    "eyebrow": (32, 1.40, 0.5, "accent"),
    "heading": (64, 1.38, 0.9, "head"),
    "body": (40, 1.78, 0.5, "ink"),
    "label": (30, 1.40, 0.45, "accent"),
    "item": (46, 1.40, 0.75, "head"),
    "sub": (34, 1.62, 0.5, "ink"),
    "note": (31, 1.50, 0.45, "ink"),
    "small": (30, 1.60, 0.45, "ink"),
}

# 長すぎる行を「縮めて1行に収める」のをどこまで許すか（これより縮むなら折り返す）。本文は大きさをそろえたいので折り返し優先
SHRINK_MIN = {"title": 0.8, "heading": 0.88, "subtitle": 0.9, "eyebrow": 0.9, "label": 0.9, "item": 0.9}

_fonts = {}


def font(size):
    size = max(8, int(round(size)))
    if size not in _fonts:
        _fonts[size] = ImageFont.truetype(MINCHO, size, index=2)  # ProN W6
    return _fonts[size]


# ---------------------------------------------------------------- 文字の掃除（絵文字）

ICONS = ("star", "sparkle", "heart", "letter", "moon", "bookmark")
EMOJI_ICON = {
    "⭐": "star", "🌟": "star", "🌠": "star", "✨": "sparkle", "💫": "sparkle",
    "💌": "letter", "✉": "letter", "📩": "letter", "📨": "letter", "📧": "letter",
    "❤": "heart", "💕": "heart", "💗": "heart", "💖": "heart", "💓": "heart", "🩷": "heart",
    "💞": "heart", "🤍": "heart", "💜": "heart", "🧡": "heart", "💛": "heart",
    "🌙": "moon", "🌛": "moon", "🌜": "moon", "☾": "moon", "☽": "moon", "🔖": "bookmark",
}
KEEP = set("★☆♡♥♪")  # 明朝体に字がある記号は残す
_glyph = {}


def is_emoji(c):
    o = ord(c)
    return (0x1F000 <= o <= 0x1FAFF or 0x2600 <= o <= 0x27BF or 0x2B00 <= o <= 0x2BFF or 0x2300 <= o <= 0x23FF
            or 0xFE00 <= o <= 0xFE0F or o in (0x200D, 0x20E3) or 0xE0000 <= o <= 0xE007F)


def has_glyph(c):
    """フォントに字があるか（無い字は豆腐 □ になるので、.notdef と同じ形かで判定する）"""
    if c.isascii() or c.isspace():
        return True
    if c not in _glyph:
        f = font(40)
        def shape(ch):
            m = f.getmask(ch)
            return m.size, bytes(m)
        _glyph[c] = shape(c) != shape("\U0010FFFD")
    return _glyph[c]


def clean(text):
    out = []
    for c in str(text):
        if c in EMOJI_ICON:
            out.append(f":{EMOJI_ICON[c]}:")
        elif c == "\n" or c in KEEP:
            out.append(c)
        elif ord(c) < 32 or is_emoji(c) or not has_glyph(c):
            if not ("︀" <= c <= "️" or c == "‍"):
                print(f"  ※ 描けない文字を消しました: {c!r}")
        else:
            out.append(c)
    return "".join(out)


# ---------------------------------------------------------------- 書式つき文字 → 行

Atom = namedtuple("Atom", "ch e a icon")  # 文字（またはアイコン名）/ 強調 / アクセント色 / アイコンか
TOKEN = re.compile(r"\*\*|==|:(?:%s):|\n|." % "|".join(ICONS), re.S)
ICON_W = 1.15  # 文中アイコンの幅（文字の何個ぶんか）


def parse(text):
    lines, cur, e, a = [], [], False, False
    for tok in TOKEN.findall(clean(text)):
        if tok == "**":
            e = not e
        elif tok == "==":
            a = not a
        elif tok == "\n":
            lines.append(cur)
            cur = []
        elif len(tok) > 2 and tok[0] == tok[-1] == ":":
            cur.append(Atom(tok[1:-1], e, a, True))
        else:
            cur.append(Atom(tok, e, a, False))
    lines.append(cur)
    lines = [strip(l) for l in lines]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def strip(line):
    i, j = 0, len(line)
    while i < j and not line[i].icon and line[i].ch.isspace():
        i += 1
    while j > i and not line[j - 1].icon and line[j - 1].ch.isspace():
        j -= 1
    return line[i:j]


def runs(line):
    """同じ書式の文字をまとめる → [(Atom の書式, 文字列 or アイコン名)]"""
    out = []
    for at in line:
        if not at.icon and out and not out[-1][0].icon and out[-1][0].e == at.e and out[-1][0].a == at.a:
            out[-1] = (out[-1][0], out[-1][1] + at.ch)
        else:
            out.append((at, at.ch))
    return out


def piece_w(at, text, size, es):
    s = size * (es if at.e else 1)
    return s * ICON_W if at.icon else font(s).getlength(text)


def line_w(line, size, es):
    return sum(piece_w(at, txt, size, es) for at, txt in runs(line))


def line_em(line, size, es):
    return max([size * (es if at.e else 1) for at in line] or [size])


# ---------------------------------------------------------------- 折り返し（禁則つき・行の長さをそろえる）

NO_START = set("、。，．,.・：；:;？！?!ー…‥）)」』】〕〉》｝}’”ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々〜～ゝゞヽヾ")
NO_END = set("（(「『【〔〈《｛{‘“")


def kind(c):
    o = ord(c)
    if 0x3040 <= o <= 0x309F:
        return "hira"
    if 0x30A0 <= o <= 0x30FF:
        return "kata"
    if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or c in "々〆":
        return "kanji"
    if (c.isascii() and (c.isalnum() or c in ":/.%-+'&#")) or 0xFF10 <= o <= 0xFF5A:
        return "alnum"
    if c.isspace():
        return "space"
    return "punct"


def break_score(prev, nxt):
    """prev と nxt の間で改行してよいか（None = だめ）。大きいほど自然な切れ目。"""
    if nxt.icon:
        return None
    if prev.icon:
        return 1.0
    p, n = prev.ch, nxt.ch
    if n in NO_START or p in NO_END:
        return None
    kp, kn = kind(p), kind(n)
    if kp == kn == "alnum":
        return None
    if kp == "space" or kn == "space":
        return 3.0
    if p in "、。！？!?」』）)…":
        return 4.0
    if p in "・｜/":
        return 3.0
    if n in "「『（(【":
        return 3.0
    score = 0.0
    if (prev.e, prev.a) != (nxt.e, nxt.a):
        score += 1.0
    elif prev.e:
        score -= 3.5  # 強調したひとまとまりの途中では切らない
    if kp == "hira" and kn in ("kanji", "kata", "alnum"):
        score += 2.5
    elif kp == "kanji" and kn == "hira":
        score -= 1.5
    elif kp == kn == "kanji":
        score -= 3.0
    elif kp == kn == "kata":
        score -= 4.0
    elif kp == kn == "hira":
        score -= 0.5
    return score


def wrap(line, size, maxw, es):
    ws = [piece_w(at, at.ch, size, es) for at in line]
    pre = [0.0]
    for w in ws:
        pre.append(pre[-1] + w)
    n, total = len(line), pre[-1]
    score = [None] + [break_score(line[i - 1], line[i]) for i in range(1, n)]
    kmin = max(2, math.ceil(total / maxw))
    best = None
    for k in range(kmin, kmin + 3):
        target = total / k
        INF = float("inf")
        dp = [[INF] * (n + 1) for _ in range(k + 1)]
        back = [[-1] * (n + 1) for _ in range(k + 1)]
        dp[0][0] = 0.0
        for j in range(1, k + 1):
            for i in range(1, n + 1):
                for p in range(i - 1, -1, -1):
                    wdt = pre[i] - pre[p]
                    if wdt > maxw * 0.985:
                        break
                    if dp[j - 1][p] == INF or (p > 0 and score[p] is None):
                        continue
                    c = dp[j - 1][p] + 12 * ((wdt - target) / target) ** 2 - (0.6 * score[p] if p else 0)
                    if c < dp[j][i]:
                        dp[j][i], back[j][i] = c, p
        if dp[k][n] < INF:
            c = dp[k][n] + (k - kmin) * 3.5
            if best is None or c < best[0]:
                best = (c, k, back)
    if best is None:
        return [line]
    _, k, back = best
    cuts, i = [], n
    for j in range(k, 0, -1):
        p = back[j][i]
        cuts.append((p, i))
        i = p
    return [strip(line[p:i]) for p, i in reversed(cuts)]


def fit(lines, size, maxw, es, shrink_min=0.84):
    """はみ出す行があれば、少しなら全体を縮め、大きくはみ出すなら折り返す。"""
    worst = max([line_w(l, size, es) for l in lines] or [0])
    if worst <= maxw:
        return size, lines
    if maxw / worst < shrink_min:
        out = []
        for l in lines:
            out += wrap(l, size, maxw, es) if line_w(l, size, es) > maxw else [l]
        lines = out
    while size > 10 and max(line_w(l, size, es) for l in lines) > maxw:
        size -= 0.5
    return size, lines


# ---------------------------------------------------------------- 図形

def star_pts(cx, cy, r, n=5, inner=0.45, rot=-90):
    pts = []
    for i in range(n * 2):
        rr = r if i % 2 == 0 else r * inner
        a = math.radians(rot) + math.pi * i / n
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def heart_pts(cx, cy, r, n=72):
    s = r / 15.5
    pts = []
    for i in range(n):
        t = TAU * i / n
        x = 16 * math.sin(t) ** 3
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        pts.append((cx + x * s, cy + (y - 2.5) * s))
    return pts


def arc_pts(c, r, a0, a1, through, n=40):
    span = (a1 - a0) % TAU
    if (through - a0) % TAU <= span:
        step = span / n
    else:
        step = -(TAU - span) / n
    return [(c[0] + r * math.cos(a0 + step * i), c[1] + r * math.sin(a0 + step * i)) for i in range(n + 1)]


def crescent_pts(cx, cy, r, off=(0.42, -0.18)):
    """make_reel の三日月と同じ形（円から、右上にずらした円を切り抜く）"""
    dx, dy = off[0] * r, off[1] * r
    d = math.hypot(dx, dy)
    ux, uy = dx / d, dy / d
    a, h = d / 2, math.sqrt(r * r - (d / 2) ** 2)
    mx, my = cx + ux * a, cy + uy * a
    p1, p2 = (mx - uy * h, my + ux * h), (mx + uy * h, my - ux * h)
    away = math.atan2(-uy, -ux)
    c0, c1 = (cx, cy), (cx + dx, cy + dy)
    ang = lambda c, p: math.atan2(p[1] - c[1], p[0] - c[0])
    return arc_pts(c0, r, ang(c0, p1), ang(c0, p2), away) + arc_pts(c1, r, ang(c1, p2), ang(c1, p1), away)


def closed(d, pts, fill, width):
    d.line(pts + pts[:2], fill=fill, width=width, joint="curve")


def draw_icon(d, kind_, cx, cy, r, col, sub=None):
    """図形のアイコン。col は RGBA。sub は手紙のハートなど差し色。"""
    w = max(2, int(round(r * 0.13)))
    if kind_ == "star":
        d.polygon(star_pts(cx, cy, r, 5, 0.45), fill=col)
    elif kind_ == "sparkle":
        d.polygon(star_pts(cx, cy, r, 4, 0.22), fill=col)
    elif kind_ == "heart":
        closed(d, heart_pts(cx, cy, r), col, w)
    elif kind_ == "heart_fill":
        d.polygon(heart_pts(cx, cy, r), fill=col)
    elif kind_ == "bookmark":
        x0, x1, y0, y1 = cx - 0.66 * r, cx + 0.66 * r, cy - r, cy + r
        closed(d, [(x0, y0), (x1, y0), (x1, y1), (cx, cy + 0.42 * r), (x0, y1)], col, w)
    elif kind_ == "letter":
        x0, x1, y0, y1 = cx - r, cx + r, cy - 0.68 * r, cy + 0.68 * r
        d.rounded_rectangle((x0, y0, x1, y1), radius=r * 0.12, outline=col, width=max(2, int(r * 0.12)))
        d.line([(x0 + w, y0 + w), (cx, cy + 0.12 * r), (x1 - w, y0 + w)], fill=col, width=max(2, int(r * 0.11)), joint="curve")
        d.polygon(heart_pts(cx, cy + 0.2 * r, r * 0.34), fill=sub or col)
    elif kind_ == "moon":
        d.polygon(crescent_pts(cx, cy, r), fill=col)
    elif kind_ in ("fire", "earth", "air", "water"):
        # 錬金術の四元素の記号（三角形）を細い円で囲む
        lw = max(2, int(r * 0.045))
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=max(1, lw - 1))
        R = r * 0.66
        up = kind_ in ("fire", "air")
        s = -1 if up else 1
        cyy = cy + s * R * 0.12
        top = (cx, cyy + s * R)
        bl = (cx - R * 0.866, cyy - s * R * 0.5)
        br = (cx + R * 0.866, cyy - s * R * 0.5)
        closed(d, [top, br, bl], col, lw)
        if kind_ in ("air", "earth"):
            yb = cyy + s * R * 0.25
            d.line((cx - R * 0.66, yb, cx + R * 0.66, yb), fill=col, width=lw)
        for a in (0, 180):
            x = cx + (r + r * 0.16) * math.cos(math.radians(a))
            d.polygon(star_pts(x, cy, r * 0.11, 4, 0.25), fill=col)


def fade_line(d, p0, p1, col, width=1, a0=255, a1=0, steps=24):
    for i in range(steps):
        t0, t1 = i / steps, (i + 1) / steps
        a = int(a0 + (a1 - a0) * (t0 + t1) / 2)
        q0 = (p0[0] + (p1[0] - p0[0]) * t0, p0[1] + (p1[1] - p0[1]) * t0)
        q1 = (p0[0] + (p1[0] - p0[0]) * t1, p0[1] + (p1[1] - p0[1]) * t1)
        d.line((q0, q1), fill=col[:3] + (a,), width=width)


def rgba(c, a=255):
    return tuple(c[:3]) + (a,)


# ---------------------------------------------------------------- 1枚の画像

class Slide:
    def __init__(self, theme, img):
        self.t = theme
        self.img = img.convert("RGBA")
        self.boxes = []      # 描いたものの範囲（星座の置き場所探し用）
        self.warnings = []

    def paint(self, fn, size, strength=1.0, extra=0.0, record=True):
        """fn(ink, glow, glow2) で描き、glow を何層かぼかして重ねてから ink を重ねる。"""
        ink = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        glow = Image.new("RGBA", (W, H), rgba(self.t["glow"], 0))
        glow2 = Image.new("RGBA", (W, H), rgba(self.t["glow"], 0))
        fn(ImageDraw.Draw(ink), ImageDraw.Draw(glow), ImageDraw.Draw(glow2))
        self._glow(glow, size, strength)
        self._glow(glow2, size, extra)
        box = ink.getbbox()
        if box:
            self.img.alpha_composite(ink.crop(box), box[:2])
            if record:
                self.boxes.append(box)
        return box

    def _glow(self, layer, size, k):
        if k <= 0:
            return
        box = layer.getbbox()
        if not box:
            return
        passes = self.t["passes"]
        pad = int(size * max(f for f, _ in passes) * 3) + 6
        box = (max(0, box[0] - pad), max(0, box[1] - pad), min(W, box[2] + pad), min(H, box[3] + pad))
        src = layer.crop(box)
        acc = Image.new("RGBA", src.size, rgba(self.t["glow"], 0))
        for f, a in passes:
            b = src.filter(ImageFilter.GaussianBlur(max(0.8, size * f)))
            al = min(1.0, a * k)
            if al < 1:
                b.putalpha(b.getchannel("A").point(lambda v, al=al: int(v * al)))
            acc = Image.alpha_composite(acc, b)
        self.img.alpha_composite(acc, box[:2])

    def check(self, box, what):
        x0, y0, x1, y1 = box
        if x0 < SAFE_L - 2 or x1 > SAFE_R + 2 or y0 < SAFE_T - 2 or y1 > SAFE_B + 2:
            self.warnings.append(f"はみ出し: {what} {tuple(int(v) for v in box)}")


# ---------------------------------------------------------------- 背景と枠

def gradient(top, bottom):
    y = np.linspace(0, 1, H)[:, None, None]
    return (np.array(top) * (1 - y) + np.array(bottom) * y) * np.ones((1, W, 1))


def haze(rnd, colors, n, blur):
    img = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for _ in range(n):
        cx, cy = rnd.randint(-200, W + 200), rnd.randint(0, H)
        r = rnd.randint(220, 480)
        d.ellipse((cx - r, cy - r * 0.6, cx + r, cy + r * 0.6), fill=rnd.choice(colors))
    return np.asarray(img.filter(ImageFilter.GaussianBlur(blur))).astype(float)


def starfield(img, rnd, color, n=170, sparkles=8):
    layer = Image.new("RGBA", (W, H), rgba(color, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(n):
        x, y = rnd.uniform(56, W - 56), rnd.uniform(56, H - 56)
        r = rnd.uniform(0.6, 1.5) if rnd.random() < 0.88 else rnd.uniform(1.6, 2.6)
        a = rnd.uniform(0.3, 1.0)
        if SAFE_L + 40 < x < SAFE_R - 40 and 240 < y < H - 240:
            a *= 0.55  # 文字の多い真ん中は控えめに
        d.ellipse((x - r, y - r, x + r, y + r), fill=rgba(color, int(255 * a)))
    sp = Image.new("RGBA", (W, H), rgba(color, 0))
    ds = ImageDraw.Draw(sp)
    for _ in range(sparkles):
        while True:
            x, y = rnd.uniform(70, W - 70), rnd.uniform(70, H - 70)
            if x < SAFE_L + 30 or x > SAFE_R - 30 or y < 200 or y > H - 200:
                break
        r = rnd.uniform(7, 15)
        ds.polygon(star_pts(x, y, r, 4, 0.18), fill=rgba(color, 235))
    glow = sp.filter(ImageFilter.GaussianBlur(6))
    for lay in (layer, glow, sp):
        img = Image.alpha_composite(img, lay)
    return img


def gold_dust(img, rnd, color, flip):
    """レイの画像にある金色の星くず（天の川）を、端に沿って薄く散らす。"""
    layer = Image.new("RGBA", (W, H), rgba(color, 0))
    d = ImageDraw.Draw(layer)
    streaks = [((0.97, 0.10), (0.70, 0.24), (0.93, 0.44)), ((0.04, 0.58), (0.30, 0.74), (0.10, 0.95))]
    for p0, p1, p2 in streaks:
        if flip:
            p0, p1, p2 = [(1 - x, y) for x, y in (p0, p1, p2)]
        for _ in range(1500):
            t = rnd.random()
            bx = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
            by = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
            spread = 14 + 34 * math.sin(math.pi * t)
            x, y = bx * W + rnd.gauss(0, spread), by * H + rnd.gauss(0, spread)
            r = rnd.uniform(0.5, 1.7)
            a = int(rnd.uniform(40, 190) * (0.35 + 0.65 * math.sin(math.pi * t)))
            d.ellipse((x - r, y - r, x + r, y + r), fill=rgba(color, a))
    img = Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(9)))
    return Image.alpha_composite(img, layer)


def background(theme_name, t, rnd, index):
    if theme_name == "rei":
        base = gradient((5, 6, 16), (0, 1, 4)) + haze(rnd, [(16, 24, 62), (22, 18, 54), (8, 28, 58)], 6, 150) * 0.28
        img = Image.fromarray(np.clip(base, 0, 255).astype("uint8")).convert("RGBA")
        img = gold_dust(img, rnd, (226, 178, 88), flip=index % 2 == 0)
        return starfield(img, rnd, t["star"], n=190, sparkles=8)
    # luna: make_reel と同じ深い紫の夜空とピンクのもや
    base = gradient((20, 4, 22), (44, 8, 38))
    hz = haze(rnd, [(150, 30, 120), (110, 20, 140), (170, 40, 100)], 7, 160)
    yy, xx = np.mgrid[0:H, 0:W]
    calm = np.exp(-(((xx - W / 2) / (W * 0.42)) ** 2 + ((yy - H * 0.48) / (H * 0.36)) ** 2))[..., None]
    arr = (base * 0.5 + hz * 0.5) * 0.72 * (1 - 0.4 * calm)  # 全体を少し沈め、文字が乗る真ん中はさらに暗くして読みやすく
    img = Image.fromarray(np.clip(arr, 0, 255).astype("uint8")).convert("RGBA")
    return starfield(img, rnd, t["star"], n=150, sparkles=7)


def hseg(d, x0, x1, y, col, w, gap=None):
    if gap:
        d.line((x0, y, gap[0], y), fill=col, width=w)
        d.line((gap[1], y, x1, y), fill=col, width=w)
    else:
        d.line((x0, y, x1, y), fill=col, width=w)


def vseg(d, y0, y1, x, col, w, gap=None):
    if gap:
        d.line((x, y0, x, gap[0]), fill=col, width=w)
        d.line((x, gap[1], x, y1), fill=col, width=w)
    else:
        d.line((x, y0, x, y1), fill=col, width=w)


def frame(slide, theme_name):
    t = slide.t
    col, faint = rgba(t["frame"]), rgba(t["faint"])

    if theme_name == "rei":
        m1, m2 = 32, 44
        gx, gy = (CX - 30, CX + 30), (H // 2 - 22, H // 2 + 22)

        def fn(dl, dg, _):
            for d, c in ((dl, col), (dg, col)):
                for m, w, cc in ((m1, 2, c), (m2, 1, faint if d is dl else c)):
                    hseg(d, m, W - m, m, cc, w, gx)
                    hseg(d, m, W - m, H - m, cc, w, gx)
                    vseg(d, m, H - m, m, cc, w, gy)
                    vseg(d, m, H - m, W - m, cc, w, gy)
                for sx, sy, cx, cy in ((1, 1, m1, m1), (-1, 1, W - m1, m1), (1, -1, m1, H - m1), (-1, -1, W - m1, H - m1)):
                    P = lambda u, v: (cx + sx * u, cy + sy * v)
                    start = {(1, 1): 0, (-1, 1): 90, (-1, -1): 180, (1, -1): 270}[(sx, sy)]
                    for rr, cc in ((30, c), (40, faint if d is dl else c)):
                        d.arc((cx - rr, cy - rr, cx + rr, cy + rr), start, start + 90, fill=cc, width=1)
                    d.polygon(star_pts(*P(12, 12), 8, 4, 0.3, rot=0), fill=c)
                    d.line((P(18, 18), P(27, 27)), fill=c, width=1)
                    d.polygon(star_pts(*P(32, 32), 4, 4, 0.4, rot=45), fill=c)
                    for u, v in ((56, 12), (12, 56)):
                        d.ellipse((P(u, v)[0] - 2.2, P(u, v)[1] - 2.2, P(u, v)[0] + 2.2, P(u, v)[1] + 2.2), fill=c)
                for y in ((m1 + m2) / 2, H - (m1 + m2) / 2):
                    d.polygon(star_pts(CX, y, 17, 4, 0.18), fill=c)
                    for dx in (-24, 24):
                        d.ellipse((CX + dx - 2, y - 2, CX + dx + 2, y + 2), fill=c)
                for x, s in (((m1 + m2) / 2, 1), (W - (m1 + m2) / 2, -1)):
                    d.polygon(crescent_pts(x, H / 2, 11, off=(0.45 * s, 0)), fill=c)

        slide.paint(fn, 30, strength=0.35, record=False)
        return

    m = 40  # luna: make_reel と同じ細い金の二重枠

    def fn(dl, dg, _):
        dl.rectangle((m, m, W - m, H - m), outline=col, width=2)
        dl.rectangle((m + 14, m + 14, W - m - 14, H - m - 14), outline=faint, width=1)
        dg.rectangle((m, m, W - m, H - m), outline=col, width=2)
        for x, y in ((m + 14, m + 14), (W - m - 14, m + 14), (m + 14, H - m - 14), (W - m - 14, H - m - 14)):
            dl.polygon(star_pts(x, y, 7, 4, 0.3, rot=0), fill=col)
        # 上から下がる飾り（ルナの画像にある吊り下げの星）
        for x, length, r in ((84, 150, 9), (102, 92, 6), (W - 84, 180, 10), (W - 102, 110, 6)):
            dl.line((x, m + 14, x, m + 14 + length), fill=rgba(t["frame"], 150), width=1)
            dl.polygon(star_pts(x, m + 14 + length + r, r, 4, 0.22), fill=rgba(t["accent"]))
            dg.polygon(star_pts(x, m + 14 + length + r, r, 4, 0.22), fill=rgba(t["glow"]))

    slide.paint(fn, 30, strength=0.4, record=False)


def constellation(slide, rnd):
    """空いている角に、細い線でつないだ星座を描く（文字と重ならない場所だけ）。"""
    t = slide.t
    cw, ch = 230, 180
    spots = [(78, 78), (W - 78 - cw, 78), (78, H - 78 - ch), (W - 78 - cw, H - 78 - ch)]
    free = [s for s in spots if all(s[0] + cw + 24 < b[0] or s[0] - 24 > b[2] or s[1] + ch + 24 < b[1] or s[1] - 24 > b[3] for b in slide.boxes)]
    if not free:
        return
    x0, y0 = rnd.choice(free)
    pts = []
    for i in range(6):
        pts.append((x0 + cw * (0.1 + 0.8 * i / 5) + rnd.uniform(-14, 14), y0 + rnd.uniform(0.12, 0.88) * ch))
    branch = (pts[3][0] + rnd.uniform(-30, 30), y0 + (0.06 if pts[3][1] > y0 + ch / 2 else 0.94) * ch)

    def fn(dl, dg, _):
        for a, b in list(zip(pts, pts[1:])) + [(pts[3], branch)]:
            dl.line((a, b), fill=rgba(t["line"], 110), width=1)
        for i, (x, y) in enumerate(pts + [branch]):
            r = 4.5 if i == 2 else rnd.uniform(2.0, 3.2)
            dl.ellipse((x - r, y - r, x + r, y + r), fill=rgba(t["star"], 240))
            dg.ellipse((x - r * 2, y - r * 2, x + r * 2, y + r * 2), fill=rgba(t["glow"]))
        dl.polygon(star_pts(*pts[2], 13, 4, 0.18), fill=rgba(t["star"], 230))

    slide.paint(fn, 20, strength=0.5, record=False)


# ---------------------------------------------------------------- 部品（縦に積む）

class Text:
    def __init__(self, text, role, t, size=None, emphasis=(), maxw=MAX_W, strength=None, color=None):
        base, self.leading, st, ckey = ROLES[role]
        self.t, self.role = t, role
        self.base = size or t["sizes"].get(role, base)
        self.strength = st if strength is None else strength
        self.color = color or t[ckey]
        self.maxw = maxw
        lines = parse(text)
        self.lines0 = [[a._replace(e=True) for a in l] if i in set(emphasis) else l for i, l in enumerate(lines)]
        self.es = t["emph"] if role != "title" else t["emph"] * 1.03

    def __bool__(self):
        return bool(self.lines0)

    def measure(self, g):
        self.size, lines = fit(self.lines0, self.base * g, self.maxw, self.es, SHRINK_MIN.get(self.role, 0.95))
        gap = self.size * (self.leading - 1)
        self.rows, y, prev = [], 0.0, False
        for line in lines:
            if not line:
                y += self.size * 0.55
                continue
            em = line_em(line, self.size, self.es)
            if prev:
                y += gap
            self.rows.append((line, em, line_w(line, self.size, self.es), y))
            y += em
            prev = True
        self.h = y
        self.w = max([r[2] for r in self.rows] or [0])
        return y

    def draw_into(self, slide, dl, dg, de, top, cx=CX, left=None):
        t = self.t
        for line, em, w, yo in self.rows:
            x = left if left is not None else cx - w / 2
            base = top + yo + em * 0.88
            slide.check((x, top + yo, x + w, top + yo + em), "".join(a.ch for a in line if not a.icon)[:12])
            for at, txt in runs(line):
                s = self.size * (self.es if at.e else 1)
                col = t["accent"] if at.a else (t["bright"] if at.e else self.color)
                if at.icon:
                    cx_, cy_, r = x + s * ICON_W * 0.55, base - s * 0.38, s * (0.46 if txt == "letter" else 0.40)
                    sub = rgba(t["accent"])
                    draw_icon(dl, txt, cx_, cy_, r, rgba(col), sub=sub)
                    draw_icon(dg, txt, cx_, cy_, r, rgba(t["glow"]), sub=rgba(t["glow"]))
                    x += s * ICON_W
                    continue
                f = font(s)
                dl.text((x, base), txt, font=f, fill=rgba(col), anchor="ls")
                dg.text((x, base), txt, font=f, fill=rgba(t["glow"]), anchor="ls")
                if at.e:
                    de.text((x, base), txt, font=f, fill=rgba(t["glow"]), anchor="ls")
                x += f.getlength(txt)

    def draw(self, slide, top, cx=CX, left=None):
        slide.paint(lambda dl, dg, de: self.draw_into(slide, dl, dg, de, top, cx, left), self.size, self.strength, self.t["extra"] * self.strength)


class Eyebrow:
    """小さな見出し。両側に細い線と星の飾り。"""

    def __init__(self, text, t):
        self.t = t
        self.text = Text(text, "eyebrow", t)

    def __bool__(self):
        return bool(self.text)

    def measure(self, g):
        self.L, self.gap = 58 * g, 18 * g
        self.text.maxw = MAX_W - 2 * (self.L + self.gap + 12 * g)
        h = self.text.measure(g)
        if len(self.text.rows) > 1:
            self.L = 0
        return h

    def draw(self, slide, top):
        tx = self.text
        t = self.t

        def fn(dl, dg, de):
            tx.draw_into(slide, dl, dg, de, top)
            if self.L:
                y = top + tx.rows[0][1] * 0.52
                for s in (-1, 1):
                    x_in = CX + s * (tx.w / 2 + self.gap)
                    x_out = x_in + s * self.L
                    fade_line(dl, (x_in, y), (x_out, y), rgba(t["line"]), 1, 230, 120, 8)
                    dl.polygon(star_pts(x_out + s * 7, y, 7 * tx.size / 32, 4, 0.22), fill=rgba(t["accent"]))
                    dg.polygon(star_pts(x_out + s * 7, y, 7 * tx.size / 32, 4, 0.22), fill=rgba(t["glow"]))

        slide.paint(fn, tx.size, tx.strength, 0)


class Divider:
    def __init__(self, t, style="sparkle", width=300):
        self.t, self.style, self.width = t, style, width

    def measure(self, g):
        self.g = g
        self.h = 22 * g
        return self.h

    def draw(self, slide, top):
        t, g = self.t, self.g
        y = top + self.h / 2
        half = self.width * g / 2

        def fn(dl, dg, _):
            col = rgba(t["line"])
            if self.style == "dots":
                n = 13
                for i in range(n):
                    if i == n // 2:
                        continue
                    x = CX - half + 2 * half * i / (n - 1)
                    a = int(255 * (1 - abs(i - n // 2) / (n // 2 + 1)))
                    r = 2.2 * g
                    dl.ellipse((x - r, y - r, x + r, y + r), fill=rgba(t["line"], a))
            else:
                for s in (-1, 1):
                    fade_line(dl, (CX + s * 16 * g, y), (CX + s * half, y), col, 1, 240, 0)
            if self.style == "moon":
                draw_icon(dl, "moon", CX, y, 8 * g, rgba(t["accent"]))
                draw_icon(dg, "moon", CX, y, 8 * g, rgba(t["glow"]))
            else:
                dl.polygon(star_pts(CX, y, 10 * g, 4, 0.2), fill=rgba(t["accent"]))
                dg.polygon(star_pts(CX, y, 10 * g, 4, 0.2), fill=rgba(t["glow"]))
                for s in (-1, 1):
                    r = 2 * g
                    x = CX + s * 22 * g
                    dl.ellipse((x - r, y - r, x + r, y + r), fill=rgba(t["accent"]))

        slide.paint(fn, 24, 0.6, 0)


class Label:
    """「起こりやすいこと」などの小さなラベル（細い楕円の囲み）"""

    def __init__(self, text, t):
        self.t = t
        self.text = Text(text, "label", t, maxw=MAX_W - 80)

    def measure(self, g):
        th = self.text.measure(g)
        s = self.text.size
        self.px, self.py = s * 1.0, s * 0.42
        self.h = th + 2 * self.py
        return self.h

    def draw(self, slide, top):
        tx, t = self.text, self.t
        w = tx.w + 2 * self.px

        def fn(dl, dg, de):
            box = (CX - w / 2, top, CX + w / 2, top + self.h)
            dl.rounded_rectangle(box, radius=self.h / 2, outline=rgba(t["line"], 220), width=2)
            dg.rounded_rectangle(box, radius=self.h / 2, outline=rgba(t["glow"]), width=2)
            tx.draw_into(slide, dl, dg, de, top + self.py)

        slide.paint(fn, tx.size, tx.strength, 0)


class Art:
    """図形の飾り（四元素の記号・三日月・ホロスコープの輪など）"""

    def __init__(self, kind_, t, size):
        self.kind, self.t, self.size = kind_, t, size

    def measure(self, g):
        self.s = self.size * g
        self.h = self.s * (1.15 if self.kind == "moon" else 1.0)
        return self.h

    def draw(self, slide, top):
        t, s, k = self.t, self.s, self.kind
        cx, cy = CX, top + self.h / 2

        def fn(dl, dg, de):
            if k == "moon":
                r = s * 0.42
                for d, c in ((dl, rgba(t["accent"])), (dg, rgba(t["glow"])), (de, rgba(t["glow"]))):
                    draw_icon(d, "moon", cx - r * 0.12, cy, r, c)
                for dx, dy, sr in ((-1.75, -0.7, 0.13), (1.6, -0.95, 0.15), (1.35, 0.85, 0.1), (-1.35, 0.95, 0.1)):
                    for d, c in ((dl, rgba(t["bright"])), (dg, rgba(t["glow"]))):
                        d.polygon(star_pts(cx + dx * r, cy + dy * r, sr * r * 1.6, 4, 0.18), fill=c)
            elif k == "wheel":
                wheel(dl, dg, cx, cy, s / 2, t)
            else:
                for d, c in ((dl, rgba(t["accent"] if k in ("star", "heart", "sparkle") else t["line"])), (dg, rgba(t["glow"]))):
                    draw_icon(d, k, cx, cy, s / 2 * (0.8 if k in ("fire", "earth", "air", "water") else 1), c)

        slide.paint(fn, s * 0.25 if k != "wheel" else 26, 0.9 if k == "moon" else 0.6, 0.6 if k == "moon" else 0)


def wheel(dl, dg, cx, cy, R, t):
    """12星座の輪。内側に四元素の4つの三角形（トライン）を重ねる。"""
    for d, base in ((dl, t["line"]), (dg, t["glow"])):
        c = rgba(base)
        soft = rgba(base, 150 if d is dl else 255)
        for rr, w in ((R * 0.97, 2), (R * 0.84, 1), (R * 0.58, 1)):
            d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=c if w == 2 else soft, width=w)
        for i in range(12):
            a = math.radians(i * 30 - 90)
            d.line((cx + R * 0.84 * math.cos(a), cy + R * 0.84 * math.sin(a), cx + R * 0.97 * math.cos(a), cy + R * 0.97 * math.sin(a)), fill=c, width=1)
            am = math.radians(i * 30 - 75)
            rm = R * 0.905
            d.polygon(star_pts(cx + rm * math.cos(am), cy + rm * math.sin(am), R * 0.03, 4, 0.35, rot=0), fill=c)
        for i in range(72):
            a = math.radians(i * 5)
            d.line((cx + R * 0.97 * math.cos(a), cy + R * 0.97 * math.sin(a), cx + R * 1.02 * math.cos(a), cy + R * 1.02 * math.sin(a)), fill=soft, width=1)
        pts = [(cx + R * 0.58 * math.cos(math.radians(i * 30 - 90)), cy + R * 0.58 * math.sin(math.radians(i * 30 - 90))) for i in range(12)]
        for k in range(4):
            tri = [pts[k], pts[k + 4], pts[k + 8]]
            d.line(tri + [tri[0]], fill=soft, width=1)
        for p in pts:
            d.ellipse((p[0] - 2.5, p[1] - 2.5, p[0] + 2.5, p[1] + 2.5), fill=c)
        d.polygon(star_pts(cx, cy, R * 0.16, 4, 0.18), fill=rgba(t["accent"] if d is dl else base))
        d.ellipse((cx - R * 0.07, cy - R * 0.07, cx + R * 0.07, cy + R * 0.07), outline=c, width=1)


class ListBlock:
    def __init__(self, items, style, t):
        self.t, self.style = t, style
        self.items = []
        for it in items:
            if isinstance(it, dict):
                txt, sub = it.get("text", ""), it.get("sub")
            else:
                txt, sub = it, None
            self.items.append((Text(txt, "item", t), Text(sub, "sub", t) if sub else None))

    def measure(self, g):
        self.g = g
        size = self.t["sizes"].get("item", ROLES["item"][0]) * g
        center = self.style == "center"
        self.mk = 0 if center else size * 1.1
        self.mg = 0 if center else size * 0.5
        colw = MAX_W - self.mk - self.mg
        self.gap = size * (1.45 if center else 0.9)
        self.subgap = size * 0.32
        self.rows, y = [], 0.0
        for i, (tx, sb) in enumerate(self.items):
            tx.maxw = colw
            h = tx.measure(g)
            if sb:
                sb.maxw = colw
                h += self.subgap + sb.measure(g)
            if i:
                y += self.gap
            self.rows.append((tx, sb, y, h))
            y += h
        self.h = y
        self.bw = max(self.mk + self.mg + max(tx.w, sb.w if sb else 0) for tx, sb, _, _ in self.rows)
        return y

    def draw(self, slide, top):
        t, g = self.t, self.g
        center = self.style == "center"
        left = CX - self.bw / 2 + self.mk + self.mg
        for i, (tx, sb, yo, h) in enumerate(self.rows):
            y = top + yo

            def fn(dl, dg, de, tx=tx, sb=sb, y=y, i=i):
                tx.draw_into(slide, dl, dg, de, y, left=None if center else left)
                if sb:
                    sb.draw_into(slide, dl, dg, de, y + tx.h + self.subgap, left=None if center else left)
                if center:
                    if i:
                        dy = y - self.gap / 2
                        for s in (-1, 1):
                            fade_line(dl, (CX + s * 14 * g, dy), (CX + s * 90 * g, dy), rgba(t["line"]), 1, 220, 0, 12)
                        dl.polygon(star_pts(CX, dy, 7 * g, 4, 0.25), fill=rgba(t["accent"]))
                    return
                em = tx.rows[0][1]
                mx, my = CX - self.bw / 2 + self.mk / 2, y + em * 0.5
                r = self.mk * 0.5
                acc, gl = rgba(t["accent"]), rgba(t["glow"])
                if self.style == "number":
                    for d, c in ((dl, acc), (dg, gl)):
                        d.ellipse((mx - r, my - r, mx + r, my + r), outline=c, width=2)
                    f = font(r * 1.15)
                    dl.text((mx, my + r * 0.04), str(i + 1), font=f, fill=rgba(t["bright"]), anchor="mm")
                    dg.text((mx, my + r * 0.04), str(i + 1), font=f, fill=gl, anchor="mm")
                elif self.style == "check":
                    rr = r * 0.78
                    for d, c in ((dl, acc), (dg, gl)):
                        d.rounded_rectangle((mx - rr, my - rr, mx + rr, my + rr), radius=rr * 0.2, outline=c, width=2)
                        d.line([(mx - rr * 0.5, my), (mx - rr * 0.1, my + rr * 0.42), (mx + rr * 0.62, my - rr * 0.5)], fill=c, width=max(2, int(r * 0.14)), joint="curve")
                else:
                    for d, c in ((dl, acc), (dg, gl)):
                        d.polygon(star_pts(mx, my, r * 0.55, 4, 0.22), fill=c)

            slide.paint(fn, tx.size, tx.strength, self.t["extra"] * tx.strength)


class Columns:
    """お礼ページの下の「いいね」「保存」の2列"""

    def __init__(self, t):
        self.t = t
        cw = MAX_W / 2 - 36
        self.cols = [("heart", Text("==いいね==\n嬉しいです！", "small", t, maxw=cw)),
                     ("bookmark", Text("あとで見返せるように\n==【保存】==してね", "small", t, maxw=cw))]

    def measure(self, g):
        self.g = g
        self.r, self.gap = 26 * g, 20 * g
        self.h = 2 * self.r + self.gap + max(tx.measure(g) for _, tx in self.cols)
        return self.h

    def draw(self, slide, top):
        t, g = self.t, self.g
        for k, (icon, tx) in enumerate(self.cols):
            cx = CX + (-1 if k == 0 else 1) * MAX_W * 0.25

            def fn(dl, dg, de, icon=icon, tx=tx, cx=cx):
                for d, c in ((dl, rgba(t["accent"])), (dg, rgba(t["glow"]))):
                    draw_icon(d, icon, cx, top + self.r, self.r * (0.92 if icon == "heart" else 1), c)
                tx.draw_into(slide, dl, dg, de, top + 2 * self.r + self.gap, cx=cx)

            slide.paint(fn, tx.size, tx.strength, 0)

        def sep(dl, dg, _):
            mid = top + self.h / 2
            for s in (-1, 1):
                fade_line(dl, (CX, mid + s * 14 * g), (CX, mid + s * (self.h / 2 + 10 * g)), rgba(t["line"]), 1, 220, 0, 16)
            dl.polygon(star_pts(CX, mid, 9 * g, 4, 0.2), fill=rgba(t["accent"]))
            dg.polygon(star_pts(CX, mid, 9 * g, 4, 0.2), fill=rgba(t["glow"]))

        slide.paint(sep, 20, 0.6, 0)


# ---------------------------------------------------------------- ページの組み立て

ICON_SIZE = {"moon": 230, "wheel": 300, "fire": 112, "earth": 112, "air": 112, "water": 112}


def build(s, t, theme_name):
    """部品と、次の部品までの間隔（U = 30px 単位）のリストを返す。"""
    typ = s.get("type", "text")
    luna = theme_name == "luna"
    els = []

    def add(el, gap):
        if el is not None and (not isinstance(el, (Text, Eyebrow)) or el):
            els.append([el, gap])

    def icon(default_gap=0.8):
        if s.get("icon"):
            k = s["icon"]
            add(Art(k, t, s.get("icon_size", ICON_SIZE.get(k, 84))), default_gap)

    if typ == "cover":
        art = s.get("art")
        art_top = art and s.get("art_position", "top" if art == "moon" else "bottom") == "top"
        if art_top:
            add(Art(art, t, s.get("art_size", ICON_SIZE.get(art, 200))), 0.8)
        if s.get("eyebrow"):
            add(Eyebrow(s["eyebrow"], t), 0.8)
        add(Text(s.get("title", ""), "title", t, size=s.get("title_size")), 0.9)
        if s.get("subtitle"):
            add(Divider(t, "moon" if luna else "sparkle"), 0.8)
            add(Text(s["subtitle"], "subtitle", t, size=s.get("subtitle_size")), 1.0)
        if art and not art_top:
            add(Art(art, t, s.get("art_size", ICON_SIZE.get(art, 200))), 1.0)
        if s.get("note"):
            add(Text(s["note"], "note", t), 0)
    elif typ in ("text", "list"):
        icon()
        if s.get("eyebrow"):
            add(Eyebrow(s["eyebrow"], t), 0.7)
        if s.get("heading"):
            add(Text(s["heading"], "heading", t, size=s.get("heading_size")), 0.9)
            if s.get("divider", True) and (s.get("body") or s.get("sections") or s.get("items")):
                add(Divider(t, "moon" if luna else "sparkle"), 0.9)
        if typ == "text":
            if s.get("body"):
                add(Text(s["body"], "body", t, size=s.get("body_size"), emphasis=s.get("emphasis", ())), 1.3)
            for sec in s.get("sections", []):
                if sec.get("label"):
                    add(Label(sec["label"], t), 0.7)
                add(Text(sec.get("text", ""), "body", t, size=s.get("body_size"), emphasis=sec.get("emphasis", ())), 1.7)
        else:
            add(ListBlock(s.get("items", []), s.get("style", "check"), t), 1.3)
        if s.get("note"):
            add(Text(s["note"], "note", t), 0)
    elif typ == "closing":
        if luna:
            add(Art("moon", t, 190), 0.7)
        s1, s2, s3 = t["closing"]
        add(Text(f"最後まで\n見てくれてありがとう:{t['thanks']}:", "heading", t, size=s1), 0.8)
        add(Divider(t, "moon" if luna else "sparkle"), 0.8)
        add(Text("もっと詳しく知りたい人は", "subtitle", t, size=s2), 0.45)
        add(Text("**DMしてね**:letter:", "heading", t, size=s3), 1.2)
        if not luna:
            add(Art("wheel", t, 250), 1.2)
        add(Divider(t, "dots", width=560), 1.0)
        add(Columns(t), 0)
    else:
        raise SystemExit(f"type がわかりません: {typ}")
    return els


def load_background(path):
    """用意された背景画像を 1080x1350 にそろえ、文字が乗る真ん中を少しだけ暗くする。"""
    im = Image.open(path).convert("RGB")
    scale = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    left, top = (im.width - W) // 2, (im.height - H) // 2
    arr = np.asarray(im.crop((left, top, left + W, top + H))).astype("float32")
    yy, xx = np.mgrid[0:H, 0:W]
    calm = np.exp(-(((xx - W / 2) / (W * 0.40)) ** 2 + ((yy - H * 0.42) / (H * 0.34)) ** 2))[..., None]
    arr *= 1 - 0.35 * calm
    return Image.fromarray(np.clip(arr, 0, 255).astype("uint8")).convert("RGBA")


def render_slide(s, theme_name, seed, index, bg_path=None):
    t = THEMES[theme_name]
    rnd = random.Random(seed)
    if bg_path:
        # 用意された背景（飾りや枠が描かれている）を使うときは、枠を描かず、下の飾りをよけて文字を置く
        slide = Slide(t, load_background(bg_path))
        top, bottom = SAFE_T + 20, H - 300
    else:
        slide = Slide(t, background(theme_name, t, rnd, index))
        frame(slide, theme_name)
        top, bottom = SAFE_T, SAFE_B
    els = build(s, t, theme_name)
    avail = bottom - top
    g = 1.0
    for _ in range(14):
        hs = [el.measure(g) for el, _ in els]
        gaps = [gap * 30 * g for _, gap in els[:-1]]
        total = sum(hs) + sum(gaps)
        if total <= avail or g < 0.5:
            break
        g *= 0.95
    y = max(top, (top + bottom) / 2 - total / 2 - 8)
    for (el, _), h, gap in zip(els, hs, gaps + [0]):
        el.draw(slide, y)
        y += h + gap
    if theme_name == "rei" and s.get("constellation", True) and not bg_path:
        constellation(slide, rnd)
    if g < 1:
        slide.warnings.append(f"縦に入りきらないので {g:.2f} 倍に縮めました")
    return slide.img.convert("RGB"), slide.warnings


def contact_sheet(paths, out, thumb=270):
    ims = [Image.open(p).convert("RGB").resize((thumb, int(thumb * H / W)), Image.LANCZOS) for p in paths]
    gap = 12
    th = ims[0].height
    sheet = Image.new("RGB", (len(ims) * (thumb + gap) + gap, th + 2 * gap + 28), (36, 36, 40))
    d = ImageDraw.Draw(sheet)
    for i, im in enumerate(ims):
        x = gap + i * (thumb + gap)
        sheet.paste(im, (x, gap))
        d.text((x + thumb / 2, gap + th + 16), str(i + 1), font=font(18), fill=(200, 200, 200), anchor="mm")
    sheet.save(out, quality=90)
    return out


def main(argv):
    spec_path = Path(argv[0])
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    theme_name = spec.get("theme", "luna")
    if theme_name not in THEMES:
        raise SystemExit(f"theme は rei か luna: {theme_name}")
    slides = spec["slides"]
    if len(slides) > 10:
        print("※ インスタのカルーセルは10枚まで")
    out_dir = spec_path.with_suffix("")
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.jpg"):
        if old.stem.isdigit():
            old.unlink()
    seed = spec.get("seed", 7)
    paths = []
    # backgrounds: [画像, ...] を書くと、ページごとに順番に背景として使う（slide の background: で個別指定も可）
    bgs = [spec_path.parent / b if not Path(b).is_absolute() and not Path(b).exists() else Path(b) for b in spec.get("backgrounds", [])]
    for i, s in enumerate(slides, 1):
        bg = s.get("background") or (bgs[(i - 1) % len(bgs)] if bgs else None)
        img, warnings = render_slide(s, theme_name, seed * 100 + i, i, bg)
        path = out_dir / f"{i}.jpg"
        img.save(path, quality=92, subsampling=0)
        paths.append(path)
        print(f"{path}" + "".join(f"\n  ※ {w}" for w in warnings))
    if "--sheet" in argv:
        print(contact_sheet(paths, spec_path.with_name(spec_path.stem + ".contact.jpg")))


if __name__ == "__main__":
    main(sys.argv[1:])
