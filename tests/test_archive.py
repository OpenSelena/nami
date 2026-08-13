"""Unit tests for Nami archive management and locks."""

from nami.archive import init_archive_dir, reset_archive, ArchiveLock


def test_archive_preservation_on_empty_dir(tmp_path):
    target_dir = tmp_path / "Photos"
    archive_file = init_archive_dir(target_dir)

    # Simulate existing archive file
    archive_file.write_text("https://instagram.com/p/123/\nhttps://instagram.com/p/456/\n")
    assert archive_file.exists()

    # Call init_archive_dir again when directory contains no media files
    same_archive = init_archive_dir(target_dir)
    assert same_archive.exists()
    assert "https://instagram.com/p/123/" in same_archive.read_text()


def test_archive_explicit_reset(tmp_path):
    target_dir = tmp_path / "Videos"
    archive_file = init_archive_dir(target_dir)
    archive_file.write_text("data")
    assert archive_file.exists()

    res = reset_archive(target_dir)
    assert res is True
    assert not archive_file.exists()


def test_archive_lock(tmp_path):
    lock_dir = tmp_path / "LockTest"
    lock1 = ArchiveLock(lock_dir)
    assert lock1.acquire() is True

    lock2 = ArchiveLock(lock_dir)
    assert lock2.acquire(timeout=0.2) is False

    lock1.release()
    assert lock2.acquire(timeout=0.2) is True
    lock2.release()


def test_archive_persistence_after_manual_media_deletion(tmp_path):
    target_dir = tmp_path / "Instagram_Media"
    target_dir.mkdir(parents=True, exist_ok=True)
    archive_file = init_archive_dir(target_dir)

    # Create dummy media files and record entries in archive
    media1 = target_dir / "2026-01-01_12-00-00_UTC.jpg"
    media1.write_bytes(b"dummy image data")
    archive_file.write_text("instagram 123456789\ninstagram 987654321\n")

    assert media1.exists()
    assert archive_file.exists()

    # User manually deletes all media files from target_dir
    media1.unlink()
    assert not media1.exists()

    # Re-initialize or check archive dir
    rechecked_archive = init_archive_dir(target_dir)

    # Verify archive.txt remains intact and uncorrupted
    assert rechecked_archive.exists()
    content = rechecked_archive.read_text()
    assert "instagram 123456789" in content
    assert "instagram 987654321" in content
