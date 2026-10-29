from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ncmelt.transcoder as transcoder


class FFmpegProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_cache = transcoder._ffmpeg_cache
        self._old_version = transcoder._ffmpeg_version_cache
        transcoder._ffmpeg_cache = None
        transcoder._ffmpeg_version_cache = None

    def tearDown(self) -> None:
        transcoder._ffmpeg_cache = self._old_cache
        transcoder._ffmpeg_version_cache = self._old_version

    def test_find_ffmpeg_reuses_the_version_probe(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fake = Path(temp) / "ffmpeg.exe"
            fake.write_bytes(b"fake")
            completed = subprocess.CompletedProcess(
                args=[str(fake)],
                returncode=0,
                stdout="ffmpeg version 7.1 Copyright (c) 2000-2024\n",
                stderr="",
            )
            with (
                patch.object(
                    transcoder, "_ffmpeg_candidates", return_value=[fake]
                ),
                patch.object(
                    transcoder.subprocess, "run", return_value=completed
                ) as run,
            ):
                self.assertEqual(transcoder.find_ffmpeg(), fake)
                self.assertEqual(transcoder.ffmpeg_version(), "FFmpeg 7.1")
                self.assertEqual(run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
