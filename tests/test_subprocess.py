"""Unit tests for subprocess execution and output parsing."""

import sys
from nami.downloader import run_command, looks_like_media_output_line


def test_looks_like_media_output_line():
    assert looks_like_media_output_line("downloads/instagram/user/image.jpg")
    assert looks_like_media_output_line("# downloads/instagram/user/video.mp4")
    assert not looks_like_media_output_line("Downloading page 1...")
    assert not looks_like_media_output_line("Extracting information...")


def test_run_command_success():
    cmd = [sys.executable, "-c", "print('hello/world.jpg')"]
    rc, stdout, stderr = run_command(cmd, timeout=5)
    assert rc == 0
    assert "hello/world.jpg" in stdout


def test_run_command_timeout():
    cmd = [sys.executable, "-c", "import time; time.sleep(10)"]
    rc, stdout, stderr = run_command(cmd, timeout=1)
    assert rc == 124
    assert "Timed out" in stderr
