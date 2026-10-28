from __future__ import annotations

import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis

from ncmelt.converter import convert_ncm
from ncmelt.errors import ConversionCancelled, NCMFormatError
from ncmelt.formats import OUTPUT_FORMATS
from ncmelt.transcoder import find_ffmpeg
from tests.make_samples import make_samples


class ConverterIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sample_dir = Path(__file__).resolve().parent / "generated"
        cls.samples = make_samples(cls.sample_dir)
        cls.by_name = {path.name: path for path in cls.samples}
        cls.flac = cls.by_name["01-night-voyage-flac.ncm"]
        cls.mp3_320 = cls.by_name["02-before-rain-mp3-320.ncm"]
        cls.mp3_128 = cls.by_name["03-city-light-mp3-128.ncm"]
        cls.aac = cls.by_name["04-starry-dream-aac-256.ncm"]
        cls.ffmpeg = find_ffmpeg()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.out = Path(self.temp.name) / "output"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _decode_ok(self, path: Path) -> None:
        result = subprocess.run(
            [
                str(self.ffmpeg),
                "-hide_banner",
                "-v",
                "error",
                "-xerror",
                "-i",
                str(path),
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            creationflags=0x08000000,
        )
        self.assertEqual(
            result.returncode, 0, result.stderr.decode("utf-8", "replace")
        )

    def _tags(self, path: Path, fmt_id: str):
        audio = MutagenFile(path)
        self.assertIsNotNone(audio)
        if fmt_id == "mp3":
            tags = ID3(path)
            return str(tags["TIT2"]), str(tags["TPE1"]), str(tags["TALB"]), tags.getall("APIC")
        if fmt_id == "flac":
            tags = FLAC(path)
            return tags["title"][0], tags["artist"][0], tags["album"][0], tags.pictures
        if fmt_id == "m4a":
            tags = MP4(path)
            return (
                tags["\xa9nam"][0],
                tags["\xa9ART"][0],
                tags["\xa9alb"][0],
                tags["covr"],
            )
        if fmt_id == "ogg":
            tags = OggVorbis(path)
            return (
                tags["title"][0],
                tags["artist"][0],
                tags["album"][0],
                tags.get("metadata_block_picture", []),
            )
        return None, None, None, None

    def test_every_output_format(self) -> None:
        for fmt in OUTPUT_FORMATS:
            for quality in fmt.qualities:
                with self.subTest(fmt=fmt.id, quality=quality.id):
                    result = convert_ncm(
                        self.flac, self.out / f"{fmt.id}-{quality.id}", fmt.id, quality.id
                    )
                    self.assertTrue(result.output.is_file())
                    self.assertEqual(result.output.suffix.lower(), "." + fmt.extension)
                    self._decode_ok(result.output)
                    audio = MutagenFile(result.output)
                    self.assertGreater(audio.info.length, 20)
                    if fmt.id in ("mp3", "m4a", "ogg") and quality.bitrate_kbps:
                        self.assertGreater(result.media.bitrate_kbps, 80)
                    if fmt.lossless:
                        self.assertTrue(result.media.lossless)
                    title, artist, album, cover = self._tags(result.output, fmt.id)
                    if fmt.id != "wav":
                        self.assertEqual(title, "夜航")
                        self.assertEqual(artist, "林间电台")
                        self.assertEqual(album, "城市微光")
                        self.assertTrue(cover)

    def test_all_source_formats(self) -> None:
        for source in (self.flac, self.mp3_320, self.mp3_128, self.aac):
            with self.subTest(source=source.name):
                result = convert_ncm(source, self.out / "formats", "mp3", "192")
                self.assertTrue(result.output.is_file())
                self._decode_ok(result.output)
                self.assertGreaterEqual(result.media.bitrate_kbps, 190)
                self.assertLessEqual(result.media.bitrate_kbps, 194)

    def test_metadata_names_output(self) -> None:
        result = convert_ncm(self.flac, self.out, "mp3", "320")
        self.assertEqual(result.output.name, "林间电台 - 夜航.mp3")
        self.assertEqual(result.header.metadata.album, "城市微光")

    def test_title_only_naming(self) -> None:
        result = convert_ncm(
            self.flac, self.out, "flac", "standard", naming="title"
        )
        self.assertEqual(result.output.name, "夜航.flac")

    def test_existing_name_gets_number(self) -> None:
        first = convert_ncm(self.flac, self.out, "mp3", "128")
        second = convert_ncm(self.flac, self.out, "mp3", "128")
        self.assertEqual(first.output.name, "林间电台 - 夜航.mp3")
        self.assertEqual(second.output.name, "林间电台 - 夜航 (1).mp3")

    def test_exact_destination_and_overwrite(self) -> None:
        target = Path(self.temp.name) / "custom-name.mp3"
        result = convert_ncm(
            self.flac,
            target.parent,
            "mp3",
            "128",
            destination=target,
        )
        self.assertEqual(result.output, target)
        with self.assertRaises(Exception):
            convert_ncm(
                self.flac,
                target.parent,
                "mp3",
                "128",
                destination=target,
            )
        result = convert_ncm(
            self.flac,
            target.parent,
            "mp3",
            "192",
            destination=target,
            overwrite=True,
        )
        self.assertEqual(result.output, target)
        self._decode_ok(target)

    def test_no_tags_or_cover(self) -> None:
        result = convert_ncm(
            self.flac,
            self.out,
            "mp3",
            "128",
            write_tags=False,
        )
        self._decode_ok(result.output)
        audio = MutagenFile(result.output)
        self.assertIsNotNone(audio)

    def test_cancel_before_start(self) -> None:
        event = threading.Event()
        event.set()
        with self.assertRaises(ConversionCancelled):
            convert_ncm(self.flac, self.out, "mp3", "320", cancel_event=event)

    def test_original_ncm_is_preserved(self) -> None:
        size = self.flac.stat().st_size
        convert_ncm(self.flac, self.out, "flac", "standard")
        self.assertEqual(self.flac.stat().st_size, size)

    def test_invalid_ncm(self) -> None:
        bad = Path(self.temp.name) / "bad.ncm"
        bad.write_bytes(b"not an ncm")
        with self.assertRaises(NCMFormatError):
            convert_ncm(bad, self.out, "mp3", "320")


if __name__ == "__main__":
    unittest.main()
