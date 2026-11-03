"""リールに音（自作のBGM）を入れる。音はこのコードで作るので、他の人の曲は使っていない。

  python add_audio.py videos/renai/07_xxx.mp4 --mood luna
"""

import argparse
import re
import subprocess
import tempfile
import wave
import zlib
from pathlib import Path

import imageio_ffmpeg
import numpy as np

SR = 44100
# 和音（MIDI の音の高さ）と、上で鳴らす鈴の音。ルナは切なめ、レイは星空らしく明るめ
MOODS = {
    "luna": {"chords": [[45, 57, 60, 64, 71], [41, 53, 57, 60, 64], [48, 55, 59, 64, 67], [43, 50, 59, 62, 69]],
             "bells": [76, 79, 81, 84, 88], "chord_sec": 4.8},
    "rei": {"chords": [[50, 57, 62, 66, 73], [47, 54, 59, 62, 69], [43, 55, 59, 62, 66], [45, 52, 57, 61, 66]],
            "bells": [78, 81, 83, 85, 90], "chord_sec": 4.2},
}


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def pad(n, mood, shift):
    """和音をゆっくり重ねて入れ替える、やわらかい音の層"""
    t = np.arange(n) / SR
    out = np.zeros((n, 2))
    sec = mood["chord_sec"]
    k = 0
    while k * sec < n / SR:
        start = k * sec
        chord = mood["chords"][k % len(mood["chords"])]
        x = np.clip((t - start) / (sec * 1.5), 0, 1)
        env = np.sin(np.pi * x) ** 2  # 前後の和音と半分ずつ重なる
        for i, note in enumerate(chord):
            f = hz(note + shift)
            for ch, detune in enumerate((0.9985, 1.0015)):
                w = 2 * np.pi * f * detune * t
                out[:, ch] += env * (np.sin(w) + 0.22 * np.sin(2 * w) + 0.06 * np.sin(3 * w)) * (1.0 if i else 0.75)
        k += 1
    lfo = 0.92 + 0.08 * np.sin(2 * np.pi * 0.09 * t)
    return out * lfo[:, None] / 5


def bells(n, mood, shift, rnd):
    """ときどき鳴る、小さな鈴の音"""
    out = np.zeros((n, 2))
    size = int(SR * 3.0)
    t = np.arange(size) / SR
    at = 1.5 + rnd.uniform(0, 1)
    while at < n / SR - 1.5:
        f = hz(mood["bells"][rnd.integers(len(mood["bells"]))] + shift)
        env = np.exp(-t * 2.4) * np.clip(t / 0.006, 0, 1)
        tone = env * (np.sin(2 * np.pi * f * t) + 0.3 * np.exp(-t * 3) * np.sin(2 * np.pi * 2.0 * f * t) + 0.12 * np.exp(-t * 6) * np.sin(2 * np.pi * 3.01 * f * t))
        pan = rnd.uniform(0.3, 0.7)
        vol = rnd.uniform(0.09, 0.16)
        s = int(at * SR)
        e = min(n, s + size)
        out[s:e, 0] += tone[: e - s] * vol * (1 - pan)
        out[s:e, 1] += tone[: e - s] * vol * pan
        at += rnd.choice([1.2, 1.8, 2.4, 3.6])
    return out


def reverb(x, rnd, wet=0.32):
    size = int(SR * 2.2)
    t = np.arange(size) / SR
    res = np.zeros_like(x)
    for ch in range(2):
        ir = rnd.standard_normal(size) * np.exp(-t * 3.2)
        ir /= np.sqrt((ir ** 2).sum())
        m = x.shape[0] + size
        res[:, ch] = np.fft.irfft(np.fft.rfft(x[:, ch], m) * np.fft.rfft(ir, m), m)[: x.shape[0]]
    return x * (1 - wet) + res * wet


def make_track(seconds, mood_name, seed):
    rnd = np.random.default_rng(seed)
    mood = MOODS[mood_name]
    n = int(seconds * SR)
    shift = int(rnd.integers(-2, 3))  # 動画ごとに少し高さを変える
    x = reverb(pad(n, mood, shift) + bells(n, mood, shift, rnd), rnd)
    x *= 10 ** (-20 / 20) / np.sqrt((x ** 2).mean())  # 聞こえる大きさをそろえる
    x *= min(1.0, 10 ** (-3 / 20) / np.abs(x).max())  # 音割れしないように
    fade = np.ones(n)
    a, b = int(0.4 * SR), int(1.2 * SR)
    fade[:a] = np.linspace(0, 1, a)
    fade[-b:] = np.linspace(1, 0, b)
    return x * fade[:, None]


def add_audio(path, mood_name):
    path = Path(path)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    _, seconds = imageio_ffmpeg.count_frames_and_secs(str(path))
    track = make_track(seconds, mood_name, zlib.crc32(path.name.encode()))
    with tempfile.TemporaryDirectory() as tmp:
        wav_path, out = Path(tmp) / "a.wav", Path(tmp) / "out.mp4"
        with wave.open(str(wav_path), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((track * 32767).astype("<i2").tobytes())
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(path), "-i", str(wav_path), "-map", "0:v:0", "-map", "1:a:0",
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(out)], check=True)
        info = subprocess.run([ffmpeg, "-i", str(out)], capture_output=True, text=True).stderr
        if not re.search(r"Stream .*Audio: aac", info):
            raise RuntimeError(f"音が入りませんでした: {path}")
        path.write_bytes(out.read_bytes())
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--mood", default="luna", choices=list(MOODS))
    a = ap.parse_args()
    for v in a.videos:
        print(add_audio(v, a.mood))
