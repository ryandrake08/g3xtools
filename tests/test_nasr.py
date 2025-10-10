"""
Tests for nasr.py - NASR database functions.

Tests cover filename sanitization and database loading.
Web scraping and CSV processing functions are better suited for integration tests.
"""

import sys
from pathlib import Path

import msgpack
import pytest

# Import the nasr module
sys.path.insert(0, str(Path(__file__).parent.parent))
import nasr


def test_sanitize_filename_simple():
    """Sanitize simple valid filename."""
    result = nasr.sanitize_filename("test.txt")
    assert result == "test.txt"


def test_sanitize_filename_with_spaces():
    """Replace spaces with underscores."""
    result = nasr.sanitize_filename("my file.txt")
    assert result == "my_file.txt"


def test_sanitize_filename_special_chars():
    """Remove special characters."""
    result = nasr.sanitize_filename("file@#$%name!.txt")
    assert result == "file____name_.txt"


def test_sanitize_filename_path_traversal():
    """Prevent path traversal attacks."""
    result = nasr.sanitize_filename("../../etc/passwd")
    assert ".." not in result
    assert "/" not in result
    # Extracts just the filename part
    assert result == "passwd"


def test_sanitize_filename_from_url():
    """Extract filename from URL path."""
    result = nasr.sanitize_filename("https://example.com/path/to/file.zip")
    assert result == "file.zip"


def test_sanitize_filename_windows_path():
    """Extract filename from Windows path."""
    result = nasr.sanitize_filename("C:\\Users\\test\\file.dat")
    assert result == "file.dat"


def test_sanitize_filename_leading_dots():
    """Remove leading dots."""
    result = nasr.sanitize_filename("...test.txt")
    assert not result.startswith(".")


def test_sanitize_filename_trailing_dots():
    """Remove trailing dots."""
    result = nasr.sanitize_filename("test.txt...")
    assert not result.endswith(".")


def test_sanitize_filename_empty():
    """Handle empty filename."""
    with pytest.raises(ValueError, match="cannot be empty"):
        nasr.sanitize_filename("")


def test_sanitize_filename_dot():
    """Replace single dot with default."""
    result = nasr.sanitize_filename(".")
    assert result == "downloaded_file"


def test_sanitize_filename_dotdot():
    """Replace double dot with default."""
    result = nasr.sanitize_filename("..")
    assert result == "downloaded_file"


def test_sanitize_filename_max_length():
    """Truncate long filenames."""
    long_name = "a" * 300 + ".txt"
    result = nasr.sanitize_filename(long_name)
    assert len(result) <= 255
    assert result.endswith(".txt")


def test_sanitize_filename_max_length_no_extension():
    """Truncate long filename without extension."""
    long_name = "a" * 300
    result = nasr.sanitize_filename(long_name)
    assert len(result) <= 255
    assert len(result) == 255


def test_sanitize_filename_preserves_valid_chars():
    """Preserve valid characters."""
    result = nasr.sanitize_filename("test-file_123.v2.dat")
    assert result == "test-file_123.v2.dat"


def test_sanitize_filename_unicode():
    """Handle unicode characters."""
    result = nasr.sanitize_filename("файл.txt")
    assert result == "____.txt"


def test_sanitize_filename_multiple_dots():
    """Handle multiple dots in filename."""
    result = nasr.sanitize_filename("archive.tar.gz")
    assert result == "archive.tar.gz"


def test_load_nasr_database_not_found(tmp_path, monkeypatch):
    """Handle missing database file."""
    # Point to empty directory
    monkeypatch.setattr(nasr, '_NASR_DATABASE_PATH', tmp_path / 'nasr.msgpack')

    with pytest.raises(FileNotFoundError, match="NASR database not found"):
        nasr.load_nasr_database()


def test_load_nasr_database_valid(tmp_path, monkeypatch):
    """Load valid NASR database."""
    # Create test database
    db_path = tmp_path / 'nasr.msgpack'
    test_data = {
        'waypoints': [
            ['KHAF', 'airport', 37.513, -122.501, 'US', 'KHAF'],
            ['VPMIN', 'fix', 37.5, -122.5, 'US', ''],
        ],
        'airways': [
            ['V25', 'V25', 'Victor'],
        ],
        'connections': {
            0: [(1, 0)],
            1: [(0, 0)],
        }
    }

    with open(db_path, 'wb') as f:
        buffer = msgpack.packb(test_data)
        assert buffer
        f.write(buffer)

    # Point to test database
    monkeypatch.setattr(nasr, '_NASR_DATABASE_PATH', db_path)

    # Load and verify
    database = nasr.load_nasr_database()

    assert 'waypoints' in database
    assert 'airways' in database
    assert 'connections' in database
    assert len(database['waypoints']) == 2
    assert len(database['airways']) == 1
    assert database['waypoints'][0][0] == 'KHAF'


def test_load_nasr_database_corrupted(tmp_path, monkeypatch):
    """Handle corrupted database file."""
    # Create corrupted file
    db_path = tmp_path / 'nasr.msgpack'
    db_path.write_bytes(b'not valid msgpack data')

    # Point to test database
    monkeypatch.setattr(nasr, '_NASR_DATABASE_PATH', db_path)

    with pytest.raises(RuntimeError, match="Failed to load NASR database"):
        nasr.load_nasr_database()


def test_load_nasr_database_empty(tmp_path, monkeypatch):
    """Handle empty database file."""
    # Create empty file
    db_path = tmp_path / 'nasr.msgpack'
    db_path.write_bytes(b'')

    # Point to test database
    monkeypatch.setattr(nasr, '_NASR_DATABASE_PATH', db_path)

    with pytest.raises(RuntimeError, match="Failed to load NASR database"):
        nasr.load_nasr_database()


def test_load_nasr_database_wrong_structure(tmp_path, monkeypatch):
    """Load database with unexpected structure."""
    # Create database with wrong structure
    db_path = tmp_path / 'nasr.msgpack'
    test_data = {'wrong': 'structure'}

    with open(db_path, 'wb') as f:
        buffer = msgpack.packb(test_data)
        assert buffer
        f.write(buffer)

    # Point to test database
    monkeypatch.setattr(nasr, '_NASR_DATABASE_PATH', db_path)

    # Should load but won't have expected keys
    database = nasr.load_nasr_database()
    assert 'wrong' in database
    assert 'waypoints' not in database


def test_sanitize_filename_null_bytes():
    """Remove null bytes from filename."""
    result = nasr.sanitize_filename("file\x00name.txt")
    assert "\x00" not in result
    assert result == "file_name.txt"


def test_sanitize_filename_newlines():
    """Remove newlines from filename."""
    result = nasr.sanitize_filename("file\nname\r.txt")
    assert "\n" not in result
    assert "\r" not in result
    assert result == "file_name_.txt"


def test_sanitize_filename_only_invalid_chars():
    """Handle filename with only invalid characters."""
    result = nasr.sanitize_filename("@#$%^&*()")
    # Invalid chars become underscores, then get stripped
    assert result == "_________"


def test_sanitize_filename_mixed_slashes():
    """Handle mixed forward and back slashes."""
    result = nasr.sanitize_filename("path/to\\file.txt")
    assert result == "file.txt"


def test_sanitize_filename_custom_max_length():
    """Respect custom max length parameter."""
    long_name = "a" * 50 + ".txt"
    result = nasr.sanitize_filename(long_name, max_length=20)
    assert len(result) <= 20
    assert result.endswith(".txt")
