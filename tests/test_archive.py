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
