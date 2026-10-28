from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from ncmelt.converter import build_output_path, sanitize_filename
from ncmelt.errors import (
    ConversionCancelled,
    NCMFormatError,
    NCMTruncatedError,
)
from ncmelt.ncm import NCMFile, build_key_stream, detect_container
from tests.ncm_fixture import build_key_stream as fixture_key_stream
from tests.ncm_fixture import build_ncm, encrypt_audio

PNG = b"\x89PNG\r\n\x1a\n" + b"fake-png-data" * 4


class NCMReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _write(self, audio: bytes, metadata: dict | None = None) -> Path:
        path = self.dir / "song.ncm"
        path.write_bytes(build_ncm(audio, metadata=metadata, cover=PNG))
        return path

    def test_key_stream_matches_fixture_builder(self) -> None:
        key = b"0123456789abcdef"
        self.assertEqual(build_key_stream(key), fixture_key_stream(key))

    def test_inspect_reads_metadata_and_cover(self) -> None:
        path = self._write(b"ID3" + b"\x00" * 100)
        header = NCMFile(path).inspect()
        self.assertEqual(header.container, "mp3")
        self.assertEqual(header.metadata.title, "测试歌曲")
        self.assertEqual(header.metadata.artist_text, "测试歌手")
        self.assertEqual(header.metadata.album, "测试专辑")
        self.assertEqual(header.metadata.bitrate, 320000)
        self.assertEqual(header.metadata.duration_ms, 12000)
        self.assertEqual(header.cover, PNG)
        self.assertEqual(header.cover_mime, "image/png")
        self.assertEqual(header.audio_size, 103)
        self.assertEqual(header.warnings, [])

    def test_decrypt_roundtrip_across_chunks(self) -> None:
        audio = b"ID3" + bytes(range(256)) * 9000 + b"tail"
        path = self._write(audio)
        with tempfile.TemporaryDirectory() as out_dir:
            extracted = NCMFile(path).extract(out_dir)
            self.assertEqual(extracted.path.read_bytes(), audio)
            self.assertEqual(extracted.container, "mp3")

    def test_decrypt_cancelled(self) -> None:
        audio = b"ID3" + b"A" * 500_000
        path = self._write(audio)
        cancel = threading.Event()
        cancel.set()
        with tempfile.TemporaryDirectory() as out_dir:
            with self.assertRaises(ConversionCancelled):
                NCMFile(path).extract(out_dir, cancel_event=cancel)

    def test_flac_detection(self) -> None:
        audio = b"fLaC" + b"\x00" * 500
        path = self._write(
            audio,
            {
                "musicName": "无损歌曲",
                "artist": [["歌手", 1]],
                "album": "",
                "bitrate": 900000,
                "duration": 300000,
                "format": "flac",
            },
        )
        header = NCMFile(path).inspect()
        self.assertEqual(header.container, "flac")
        self.assertTrue(header.is_lossless)
        self.assertEqual(header.metadata.quality_text, "无损")
        self.assertEqual(header.metadata.duration_text, "05:00")

    def test_aac_detection(self) -> None:
        audio = b"\xff\xf1" + b"\x00" * 300
        path = self._write(audio, {"format": "aac", "musicName": "AAC"})
        self.assertEqual(NCMFile(path).inspect().container, "aac")

    def test_no_cover(self) -> None:
        path = self.dir / "no-cover.ncm"
        path.write_bytes(build_ncm(b"ID3" + b"\x00" * 100, cover=b""))
        header = NCMFile(path).inspect()
        self.assertEqual(header.cover, b"")
        self.assertEqual(header.cover_mime, "image/jpeg")

    def test_bad_magic(self) -> None:
        path = self.dir / "bad.ncm"
        path.write_bytes(b"NOTNCM!!" + b"\x00" * 100)
        with self.assertRaises(NCMFormatError):
            NCMFile(path).inspect()

    def test_truncated_header(self) -> None:
        path = self._write(b"ID3" + b"\x00" * 100)
        path.write_bytes(path.read_bytes()[:20])
        with self.assertRaises(NCMTruncatedError):
            NCMFile(path).inspect()

    def test_corrupt_header_crc_is_warning(self) -> None:
        path = self.dir / "crc.ncm"
        path.write_bytes(build_ncm(b"ID3" + b"\x00" * 100, corrupt_crc=True))
        header = NCMFile(path).inspect()
        self.assertTrue(header.warnings)
        self.assertIn("校验码", header.warnings[0])

    def test_container_detection(self) -> None:
        self.assertEqual(detect_container(b"ID3\x04\x00"), "mp3")
        self.assertEqual(detect_container(b"\xff\xfb\x90\x00"), "mp3")
        self.assertEqual(detect_container(b"\xff\xf1\x50\x00"), "aac")
        self.assertEqual(detect_container(b"fLaC\x00\x00"), "flac")
        self.assertEqual(detect_container(b"OggS\x00\x02"), "ogg")
        self.assertEqual(detect_container(b"RIFF\x00\x00\x00\x00WAVE"), "wav")
        self.assertEqual(detect_container(b"\x00\x00\x00\x20ftypM4A "), "m4a")

    def test_encrypt_audio_is_reversible(self) -> None:
        key = b"0123456789abcdef"
        audio = b"ID3" + bytes(range(256)) * 3
        encrypted = encrypt_audio(audio, key)
        self.assertNotEqual(audio, encrypted)
        self.assertEqual(encrypt_audio(encrypted, key), audio)


class NamingTests(unittest.TestCase):
    def test_sanitize_invalid_characters(self) -> None:
        self.assertEqual(sanitize_filename('a<b>c:d"e/f\\g|h?i*j'), "a_b_c_d_e_f_g_h_i_j")

    def test_sanitize_reserved_name(self) -> None:
        self.assertEqual(sanitize_filename("CON"), "_CON")
        self.assertEqual(sanitize_filename("nul.txt"), "_nul.txt")

    def test_sanitize_trims(self) -> None:
        self.assertEqual(sanitize_filename("  hello...  "), "hello")

    def test_output_name_uses_metadata_and_avoids_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "fallback.ncm"
            source.write_bytes(b"")
            from ncmelt.ncm import NCMMetadata, NCMHeader

            header = NCMHeader(
                path=source,
                metadata=NCMMetadata(title="晴天", artists=["周杰伦"], album="叶惠美"),
                key_stream=b"",
                cover=b"",
                cover_mime="image/jpeg",
                audio_offset=0,
                file_size=100,
                audio_size=100,
                container="mp3",
            )
            first = build_output_path(source, header, root, "mp3")
            self.assertEqual(first.name, "周杰伦 - 晴天.mp3")
            first.write_bytes(b"x")
            second = build_output_path(source, header, root, "mp3")
            self.assertEqual(second.name, "周杰伦 - 晴天 (1).mp3")


if __name__ == "__main__":
    unittest.main()
