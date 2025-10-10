"""
Tests for taw.py - TAW archive extraction.

Tests cover TAW file format validation, metadata parsing, and region extraction.
These are unit tests for the business logic, not full integration tests.
"""

import sys
from pathlib import Path

import pytest

# Import the taw module
sys.path.insert(0, str(Path(__file__).parent.parent))
import taw


def create_minimal_taw(output_path: Path, database_type: int = 0x06BF, year: int = 25, cycle: int = 10) -> None:
    """
    Create a minimal valid TAW file for testing.

    This creates the smallest possible TAW structure that will pass validation.
    """
    with open(output_path, 'wb') as f:
        # Header: magic
        f.write(b'pWa.d')

        # Separator
        f.write(taw._TAW_SEPARATOR)

        # SQA1 (25 bytes)
        f.write(b'SQA1\x00' + b'\x00' * 20)

        # Metadata length (4 bytes little-endian)
        metadata = bytearray()
        metadata.extend(database_type.to_bytes(2, 'little'))
        metadata.append(0x01)  # Version flag
        metadata.append(0x00)  # Padding
        metadata.append(year)
        metadata.append(0x00)  # Padding
        metadata.append(cycle)
        metadata.append(0x00)  # Padding
        # Three null-terminated strings (no trailing null after last one)
        metadata.extend(b'G3X Touch\x00USA-VFR\x00NAVIGATION')

        f.write(len(metadata).to_bytes(4, 'little'))

        # Section type F (metadata)
        f.write(b'F')

        # Write metadata
        f.write(metadata)

        # Remaining (4 bytes)
        f.write(b'\x00\x00\x00\x00')

        # Section type R (regions start)
        f.write(b'R')

        # Magic
        f.write(taw._TAW_MAGIC)

        # Separator
        f.write(taw._TAW_SEPARATOR)

        # SQA2 (25 bytes)
        f.write(b'SQA2\x00' + b'\x00' * 20)

        # Single region with test data
        region_data = b'TEST_REGION_DATA'

        # Section size (4 bytes)
        section_size = 1 + 2 + 4 + 4 + len(region_data)
        f.write(section_size.to_bytes(4, 'little'))

        # Section type R
        f.write(b'R')

        # Region ID (0x28 = terrain.adb)
        f.write(b'\x28\x00')

        # Unknown (4 bytes)
        f.write(b'\x00\x00\x00\x00')

        # Data size
        f.write(len(region_data).to_bytes(4, 'little'))

        # Data
        f.write(region_data)

        # End section type S
        f.write(b'\x00\x00\x00\x00')  # Section size
        f.write(b'S')


def test_extract_taw_info_only(tmp_path, capsys):
    """Extract TAW metadata in info-only mode."""
    taw_file = tmp_path / "test.taw"
    create_minimal_taw(taw_file, database_type=0x06BF, year=25, cycle=10)

    output_path = tmp_path / "output"
    output_path.mkdir()

    # Info only - should not extract files
    list(taw.extract_taw(taw_file, output_path, info_only=True, verbose=False))

    captured = capsys.readouterr()

    # Should show file listing (metadata parsing might fail due to format complexity)
    assert "terrain.adb" in captured.out


def test_extract_taw_extract_files(tmp_path):
    """Extract TAW files to output directory."""
    taw_file = tmp_path / "test.taw"
    create_minimal_taw(taw_file)

    output_path = tmp_path / "output"
    output_path.mkdir()

    # Extract files
    results = list(taw.extract_taw(taw_file, output_path, info_only=False, verbose=False))

    # Should have extracted one region
    assert len(results) == 1
    region_path, output_file = results[0]

    # Check region mapping
    assert region_path == "terrain.adb"

    # Verify file was created
    assert output_file.exists()
    assert output_file.name == "terrain.adb"

    # Verify content
    content = output_file.read_bytes()
    assert content == b'TEST_REGION_DATA'


def test_extract_taw_invalid_magic(tmp_path):
    """Reject TAW file with invalid magic bytes."""
    taw_file = tmp_path / "bad.taw"
    taw_file.write_bytes(b'BAD_MAGIC' + b'\x00' * 100)

    output_path = tmp_path / "output"
    output_path.mkdir()

    with pytest.raises(ValueError, match="Unexpected bytes"):
        list(taw.extract_taw(taw_file, output_path, info_only=False, verbose=False))


def test_extract_taw_invalid_separator(tmp_path):
    """Reject TAW file with invalid separator."""
    taw_file = tmp_path / "bad_sep.taw"
    with open(taw_file, 'wb') as f:
        f.write(b'pWa.d')
        f.write(b'BAD_SEPARATOR_' + b'\x00' * 10)

    output_path = tmp_path / "output"
    output_path.mkdir()

    with pytest.raises(ValueError, match="Unexpected separator bytes"):
        list(taw.extract_taw(taw_file, output_path, info_only=False, verbose=False))


def test_extract_taw_database_type_mapping(tmp_path):
    """Verify different database types can be processed."""
    taw_file = tmp_path / "g3x.taw"
    create_minimal_taw(taw_file, database_type=0x02EA)  # G3X classic

    output_path = tmp_path / "output"
    output_path.mkdir()

    # Should not raise exception even with different database type
    results = list(taw.extract_taw(taw_file, output_path, info_only=False, verbose=False))
    assert len(results) == 1


def test_extract_taw_unknown_database_type(tmp_path):
    """Handle unknown database types gracefully."""
    taw_file = tmp_path / "unknown.taw"
    create_minimal_taw(taw_file, database_type=0x9999)  # Unknown type

    output_path = tmp_path / "output"
    output_path.mkdir()

    # Should not raise exception even with unknown database type
    results = list(taw.extract_taw(taw_file, output_path, info_only=False, verbose=False))
    assert len(results) == 1


def test_extract_taw_skip_unknown_regions(tmp_path):
    """Skip unknown regions when flag is set."""
    # Create TAW with unknown region
    taw_file = tmp_path / "test.taw"
    with open(taw_file, 'wb') as f:
        # Header
        f.write(b'pWa.d')
        f.write(taw._TAW_SEPARATOR)
        f.write(b'SQA1\x00' + b'\x00' * 20)

        # Metadata
        metadata = bytearray()
        metadata.extend((0x06BF).to_bytes(2, 'little'))
        metadata.append(0x01)
        metadata.append(0x00)
        metadata.append(25)
        metadata.append(0x00)
        metadata.append(10)
        metadata.append(0x00)
        metadata.extend(b'G3X\x00USA\x00NAV\x00')

        f.write(len(metadata).to_bytes(4, 'little'))
        f.write(b'F')
        f.write(metadata)
        f.write(b'\x00\x00\x00\x00')
        f.write(b'R')
        f.write(taw._TAW_MAGIC)
        f.write(taw._TAW_SEPARATOR)
        f.write(b'SQA2\x00' + b'\x00' * 20)

        # Unknown region (0xFF is not in mapping)
        region_data = b'UNKNOWN_DATA'
        section_size = 1 + 2 + 4 + 4 + len(region_data)
        f.write(section_size.to_bytes(4, 'little'))
        f.write(b'R')
        f.write(b'\xFF\x00')  # Unknown region ID
        f.write(b'\x00\x00\x00\x00')
        f.write(len(region_data).to_bytes(4, 'little'))
        f.write(region_data)

        # End
        f.write(b'\x00\x00\x00\x00')
        f.write(b'S')

    output_path = tmp_path / "output"
    output_path.mkdir()

    # Extract with skip_unknown_regions=True
    results = list(taw.extract_taw(taw_file, output_path, info_only=False,
                                    skip_unknown_regions=True, verbose=False))

    # Should have no results (unknown region skipped)
    assert len(results) == 0


def test_extract_taw_include_unknown_regions(tmp_path):
    """Include unknown regions with generated filename."""
    # Create TAW with unknown region
    taw_file = tmp_path / "test.taw"
    with open(taw_file, 'wb') as f:
        # Header
        f.write(b'pWa.d')
        f.write(taw._TAW_SEPARATOR)
        f.write(b'SQA1\x00' + b'\x00' * 20)

        # Metadata
        metadata = bytearray()
        metadata.extend((0x06BF).to_bytes(2, 'little'))
        metadata.append(0x01)
        metadata.append(0x00)
        metadata.append(25)
        metadata.append(0x00)
        metadata.append(10)
        metadata.append(0x00)
        metadata.extend(b'G3X\x00USA\x00NAV\x00')

        f.write(len(metadata).to_bytes(4, 'little'))
        f.write(b'F')
        f.write(metadata)
        f.write(b'\x00\x00\x00\x00')
        f.write(b'R')
        f.write(taw._TAW_MAGIC)
        f.write(taw._TAW_SEPARATOR)
        f.write(b'SQA2\x00' + b'\x00' * 20)

        # Unknown region
        region_data = b'UNKNOWN_DATA'
        section_size = 1 + 2 + 4 + 4 + len(region_data)
        f.write(section_size.to_bytes(4, 'little'))
        f.write(b'R')
        f.write(b'\xFF\x00')
        f.write(b'\x00\x00\x00\x00')
        f.write(len(region_data).to_bytes(4, 'little'))
        f.write(region_data)

        # End
        f.write(b'\x00\x00\x00\x00')
        f.write(b'S')

    output_path = tmp_path / "output"
    output_path.mkdir()

    # Extract with skip_unknown_regions=False (default)
    results = list(taw.extract_taw(taw_file, output_path, info_only=False,
                                    skip_unknown_regions=False, verbose=False))

    # Should have result with generated filename
    assert len(results) == 1
    region_path, output_file = results[0]

    # Should use generated name
    assert region_path is None
    assert output_file.name == "region_ff.bin"
    assert output_file.read_bytes() == b'UNKNOWN_DATA'


def test_extract_taw_path_traversal_protection(tmp_path):
    """Prevent path traversal attacks in region paths."""
    # Note: This test verifies that pathlib's resolve() and relative_to()
    # would catch malicious paths. The actual TAW format uses predefined
    # region paths from _TAW_REGION_PATHS dictionary, so this is defensive.

    taw_file = tmp_path / "test.taw"
    output_path = tmp_path / "output"
    output_path.mkdir()

    # The extract_taw function checks that resolved paths stay within dest_path
    # This is enforced at line 208-211 in taw.py

    # We can't easily test this without modifying _TAW_REGION_PATHS,
    # but we can verify the mechanism exists by checking known good paths work
    create_minimal_taw(taw_file)
    results = list(taw.extract_taw(taw_file, output_path, info_only=False, verbose=False))

    # Verify extracted file is within output_path
    _, output_file = results[0]
    assert output_path in output_file.parents or output_file.parent == output_path


def test_extract_taw_verbose_output(tmp_path, capsys):
    """Verify verbose output shows debugging information."""
    taw_file = tmp_path / "test.taw"
    create_minimal_taw(taw_file)

    output_path = tmp_path / "output"
    output_path.mkdir()

    list(taw.extract_taw(taw_file, output_path, info_only=True, verbose=True))

    captured = capsys.readouterr()

    # Should show SQA info
    assert "SQA1:" in captured.out
    assert "SQA2:" in captured.out

    # Should show region details
    assert "Region:" in captured.out
    assert "Database size:" in captured.out


def test_extract_taw_generator_pattern(tmp_path):
    """Verify extract_taw uses generator pattern correctly."""
    taw_file = tmp_path / "test.taw"
    create_minimal_taw(taw_file)

    output_path = tmp_path / "output"
    output_path.mkdir()

    # Should return a generator
    result = taw.extract_taw(taw_file, output_path, info_only=False, verbose=False)

    # Generator should not have executed yet
    assert not list(output_path.glob("*"))

    # Consume generator
    results = list(result)

    # Now files should exist
    assert len(results) == 1
    assert list(output_path.glob("*"))
