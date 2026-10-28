"""Build synthetic .ncm files for tests (not affiliated with Netease)."""

from __future__ import annotations

import base64
import json
import struct
import zlib
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Util.strxor import strxor

MAGIC = b"CTENFDAM"
CORE_KEY = bytes.fromhex("687A4852416D736F356B496E62617857")
META_KEY = bytes.fromhex("2331346C6A6B5F215C5D2630553C2728")
KEY_PREFIX = b"neteasecloudmusic"
META_PREFIX = b"163 key(Don't modify):"
MUSIC_PREFIX = b"music:"


def _pad(data: bytes) -> bytes:
    amount = 16 - len(data) % 16
    return data + bytes([amount]) * amount


def build_key_stream(key: bytes) -> bytes:
    box = list(range(256))
    j = 0
    for i in range(256):
        j = (j + box[i] + key[i % len(key)]) & 0xFF
        box[i], box[j] = box[j], box[i]
    out = bytearray(256)
    for i in range(256):
        i2 = (i + 1) & 0xFF
        j = (box[i2] + i2) & 0xFF
        out[i] = box[(box[i2] + box[j]) & 0xFF]
    return bytes(out)


def encrypt_audio(audio: bytes, key: bytes) -> bytes:
    stream = build_key_stream(key)
    repeats = (len(audio) + 255) // 256
    return strxor(audio, (stream * repeats)[: len(audio)])


def build_ncm(
    audio: bytes,
    metadata: dict | None = None,
    cover: bytes = b"",
    cover2: bytes = b"",
    key: bytes = b"0123456789abcdef",
    corrupt_crc: bool = False,
) -> bytes:
    encrypted_key = AES.new(CORE_KEY, AES.MODE_ECB).encrypt(_pad(KEY_PREFIX + key))
    encrypted_key = bytes(b ^ 0x64 for b in encrypted_key)

    if metadata is None:
        metadata = {
            "musicName": "测试歌曲",
            "artist": [["测试歌手", 1]],
            "album": "测试专辑",
            "bitrate": 320000,
            "duration": 12000,
            "format": "mp3",
        }
    meta_json = json.dumps(metadata, ensure_ascii=False, separators=(",", ":")).encode()
    meta_plain = AES.new(META_KEY, AES.MODE_ECB).encrypt(_pad(MUSIC_PREFIX + meta_json))
    encoded = base64.b64encode(meta_plain)
    encrypted_meta = bytes(b ^ 0x63 for b in META_PREFIX + encoded)

    header = bytearray()
    header += MAGIC
    header += b"\x01\x70"
    header += struct.pack("<I", len(encrypted_key))
    header += encrypted_key
    header += struct.pack("<I", len(encrypted_meta))
    header += encrypted_meta
    crc = zlib.crc32(header) & 0xFFFFFFFF
    if corrupt_crc:
        crc ^= 0xFFFFFFFF
    header += struct.pack("<I", crc)
    header += b"\x01"
    header += struct.pack("<I", len(cover) + len(cover2))
    header += struct.pack("<I", len(cover))
    header += cover
    header += cover2
    header += encrypt_audio(audio, key)
    return bytes(header)


def write_ncm(path: Path, audio: bytes, metadata: dict | None = None, cover: bytes = b"") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_ncm(audio, metadata=metadata, cover=cover))
    return path
