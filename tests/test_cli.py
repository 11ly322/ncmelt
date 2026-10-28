from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ncmelt.transcoder import find_ffmpeg
from tests.make_samples import make_samples


class CLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parent.parent
        cls.sample_dir = Path(__file__).resolve().parent / "generated"
        cls.flac = make_samples(cls.sample_dir)[0]

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.out = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _run(self, *args: str):
        return subprocess.run(
            [sys.executable, "-m", "ncmelt.cli", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=0x08000000,
        )

    def test_mp3_output(self) -> None:
        target = self.out / "output.mp3"
        result = self._run(str(self.flac), "-o", str(target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(target.is_file())
        self.assertGreater(target.stat().st_size, 1024)
        decode = subprocess.run(
            [str(find_ffmpeg()), "-v", "error", "-xerror", "-i", str(target), "-f", "null", "-"],
            capture_output=True,
            creationflags=0x08000000,
        )
        self.assertEqual(decode.returncode, 0, decode.stderr.decode("utf-8", "replace"))

    def test_flac_output_and_quality(self) -> None:
        target = self.out / "output.flac"
        result = self._run(str(self.flac), "-o", str(target), "--quality", "max")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(target.is_file())
        with target.open("rb") as fh:
            self.assertEqual(fh.read(4), b"fLaC")

    def test_name_style_and_no_tags(self) -> None:
        result = self._run(
            str(self.flac),
            "-o",
            str(self.out),
            "--name-style",
            "title",
            "--no-tags",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.out / "夜航.mp3").is_file())

    def test_missing_input(self) -> None:
        result = self._run(str(self.out / "missing.ncm"), "-o", str(self.out / "x.mp3"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("找不到输入文件", result.stderr)

    def test_invalid_quality(self) -> None:
        target = self.out / "x.flac"
        result = self._run(str(self.flac), "-o", str(target), "--quality", "320")
        self.assertEqual(result.returncode, 2)
        self.assertIn("不支持音质", result.stderr)

    def test_overwrite_works_in_output_directory(self) -> None:
        first = self._run(
            str(self.flac), "-o", str(self.out), "--name-style", "title"
        )
        self.assertEqual(first.returncode, 0, first.stderr)
        target = self.out / "夜航.mp3"
        self.assertTrue(target.is_file())
        old_mtime = target.stat().st_mtime
        target.touch()

        second = self._run(
            str(self.flac),
            "-o",
            str(self.out),
            "--name-style",
            "title",
            "--overwrite",
        )
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertFalse((self.out / "夜航 (1).mp3").exists())
        self.assertGreaterEqual(target.stat().st_mtime, old_mtime)

    def test_multiple_inputs_reject_file_output_path(self) -> None:
        samples = make_samples(self.sample_dir)
        target = self.out / "mix.mp3"
        result = self._run(str(samples[0]), str(samples[1]), "-o", str(target))
        self.assertEqual(result.returncode, 2)
        self.assertIn("必须是输出目录", result.stderr)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
