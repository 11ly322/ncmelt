"""Generate small, fully synthetic NCM files used by the test suite."""

from __future__ import annotations

import math
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ncmelt.transcoder import find_ffmpeg
from tests.ncm_fixture import build_ncm

SAMPLE_RATE = 44100
DURATION = 24.0


def _note(freq: float, t: np.ndarray, amplitude: float = 0.2) -> np.ndarray:
    # A soft electric-piano-like tone with two harmonics and gentle decay.
    attack = np.minimum(1.0, t / 0.02)
    decay = np.exp(-0.55 * t)
    wave_data = (
        np.sin(2 * math.pi * freq * t)
        + 0.25 * np.sin(2 * math.pi * freq * 2.01 * t)
        + 0.08 * np.sin(2 * math.pi * freq * 3.99 * t)
    )
    return amplitude * attack * decay * wave_data


def make_music(path: Path) -> None:
    t = np.arange(int(SAMPLE_RATE * DURATION)) / SAMPLE_RATE
    left = np.zeros_like(t)
    right = np.zeros_like(t)
    progression = [
        [261.63, 329.63, 392.00, 493.88],
        [220.00, 261.63, 329.63, 392.00],
        [174.61, 220.00, 261.63, 329.63],
        [196.00, 246.94, 293.66, 392.00],
    ]
    bar = 4.0
    for bar_index in range(int(DURATION // bar)):
        start = bar_index * bar
        chord = progression[bar_index % len(progression)]
        for step in range(8):
            note_start = start + step * 0.5
            note_t = t - note_start
            mask = (note_t >= 0) & (note_t < 2.4)
            freq = chord[step % len(chord)] * (2 if step in (2, 5) else 1)
            tone = _note(freq, note_t, 0.16)
            pan = 0.25 + 0.5 * ((step % 4) / 3)
            left += np.where(mask, tone * (1.0 - 0.35 * pan), 0.0)
            right += np.where(mask, tone * (0.65 + 0.35 * pan), 0.0)
        for freq in chord:
            note_t = t - start
            mask = (note_t >= 0) & (note_t < bar)
            pad = 0.035 * np.sin(2 * math.pi * freq * 0.5 * note_t) * np.minimum(1, note_t / 1.5)
            left += np.where(mask, pad, 0.0)
            right += np.where(mask, pad, 0.0)

    # Simple kick / tick for a little rhythm.
    for beat in range(int(DURATION * 2)):
        note_start = beat * 0.5
        note_t = t - note_start
        mask = (note_t >= 0) & (note_t < 0.12)
        kick = (
            0.10
            * np.sin(2 * math.pi * 70 * note_t)
            * np.exp(-35 * np.maximum(note_t, 0))
        )
        left += np.where(mask, kick, 0.0)
        right += np.where(mask, kick, 0.0)

    # Gentle fade in/out and light stereo width.
    fade = np.ones_like(t)
    fade_in = min(int(1.0 * SAMPLE_RATE), len(fade))
    fade[:fade_in] = np.linspace(0, 1, fade_in, endpoint=False)
    fade_out = min(int(2.0 * SAMPLE_RATE), len(fade))
    fade[-fade_out:] = np.linspace(1, 0, fade_out, endpoint=False)
    left = left * fade
    right = right * fade
    peak = max(np.max(np.abs(left)), np.max(np.abs(right)), 1e-6)
    scale = 0.88 / peak
    stereo = np.stack([left * scale, right * scale], axis=1)
    pcm = (np.clip(stereo, -1, 1) * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(2)
        fh.setsampwidth(2)
        fh.setframerate(SAMPLE_RATE)
        fh.writeframes(pcm.tobytes())


def make_cover(path: Path) -> None:
    size = 640
    image = Image.new("RGB", (size, size), "#131a2c")
    pixels = image.load()
    for y in range(size):
        for x in range(size):
            r = int(18 + 36 * (x / size) + 18 * math.sin(y / 55))
            g = int(20 + 16 * (y / size))
            b = int(42 + 52 * (1 - y / size) + 20 * math.cos(x / 70))
            pixels[x, y] = (r, g, b)
    draw = ImageDraw.Draw(image)
    # Soft glowing moon and a minimal skyline.
    for radius in range(180, 40, -4):
        alpha = int(3 + (180 - radius) / 8)
        draw.ellipse(
            (420 - radius, 190 - radius, 420 + radius, 190 + radius),
            fill=(235 - alpha, 90 + alpha // 4, 115 + alpha // 3),
        )
    draw.ellipse((370, 140, 470, 240), fill=(255, 214, 181))
    draw.rectangle((0, 470, 640, 640), fill=(9, 13, 24))
    for index, height in enumerate([70, 120, 52, 160, 95, 135, 60, 110]):
        x = 20 + index * 80
        draw.rectangle((x, 640 - height, x + 52, 640), fill=(12, 19, 34))
        for wy in range(640 - height + 12, 620, 24):
            for wx in range(x + 9, x + 44, 16):
                draw.rectangle((wx, wy, wx + 5, wy + 8), fill=(255, 200, 120))
    # Waveform line.
    points = []
    for x in range(60, 580, 4):
        y = 330 + int(26 * math.sin(x / 15) * math.sin(x / 43))
        points.append((x, y))
    draw.line(points, fill=(255, 96, 126), width=4)
    font_path = Path(r"C:\Windows\Fonts\msyhbd.ttc")
    if font_path.exists():
        title_font = ImageFont.truetype(str(font_path), 46)
        small_font = ImageFont.truetype(str(font_path), 22)
    else:
        title_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    draw.text((54, 50), "夜航", fill=(248, 244, 240), font=title_font)
    draw.text((57, 112), "NIGHT  VOYAGE", fill=(190, 180, 205), font=small_font)
    image.save(path, format="PNG", optimize=True)


def encode(ffmpeg: Path, source: Path, destination: Path, args: list[str]) -> None:
    cmd = [
        str(ffmpeg),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        *args,
        str(destination),
    ]
    subprocess.run(cmd, check=True, creationflags=0x08000000)


def make_samples(root: Path) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg()
    wav = root / "source.wav"
    cover = root / "cover.png"
    make_music(wav)
    make_cover(cover)
    cover_bytes = cover.read_bytes()

    definitions = [
        {
            "file": "01-night-voyage-flac.ncm",
            "title": "夜航",
            "artist": "林间电台",
            "album": "城市微光",
            "format": "flac",
            "bitrate": 912000,
            "audio": ("flac", ["-c:a", "flac", "-compression_level", "5"]),
        },
        {
            "file": "02-before-rain-mp3-320.ncm",
            "title": "雨停之前",
            "artist": "北岸乐队",
            "album": "潮汐手记",
            "format": "mp3",
            "bitrate": 320000,
            "audio": ("mp3", ["-c:a", "libmp3lame", "-b:a", "320k"]),
        },
        {
            "file": "03-city-light-mp3-128.ncm",
            "title": "城市微光",
            "artist": "林间电台",
            "album": "城市微光",
            "format": "mp3",
            "bitrate": 128000,
            "audio": ("mp3", ["-c:a", "libmp3lame", "-b:a", "128k"]),
        },
        {
            "file": "04-starry-dream-aac-256.ncm",
            "title": "星河入梦",
            "artist": "远山合唱团",
            "album": "夜行列车",
            "format": "aac",
            "bitrate": 256000,
            "audio": ("m4a", ["-c:a", "aac", "-b:a", "256k"]),
        },
    ]
    result: list[Path] = []
    for item in definitions:
        suffix, args = item["audio"]
        encoded = root / f"encoded.{suffix}"
        encode(ffmpeg, wav, encoded, args)
        metadata = {
            "musicName": item["title"],
            "artist": [[item["artist"], 100]],
            "album": item["album"],
            "bitrate": item["bitrate"],
            "duration": int(DURATION * 1000),
            "format": item["format"],
        }
        ncm = root / item["file"]
        ncm.write_bytes(build_ncm(encoded.read_bytes(), metadata=metadata, cover=cover_bytes))
        result.append(ncm)
    return result


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    target = Path(__file__).resolve().parent / "generated"
    files = make_samples(target)
    for file in files:
        print(file, file.stat().st_size)
