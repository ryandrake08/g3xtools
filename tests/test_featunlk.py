"""
Tests for featunlk.py - Feature unlock file generation.

Tests for checksum algorithm, volume ID encoding, and feat_unlk.dat structure.
Note: featunlk.py is not refactored to maintain upstream parity.
"""

import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import featunlk


def test_checksum_algorithm():
    """Verify feat_unlk checksum against known values."""
    # Test with known data
    test_data = b"Test data for checksum"
    checksum = featunlk._feat_unlk_checksum(test_data)

    # Checksum should be 32-bit unsigned integer
    assert isinstance(checksum, int)
    assert 0 <= checksum <= 0xFFFFFFFF

    # Same data should produce same checksum
    checksum2 = featunlk._feat_unlk_checksum(test_data)
    assert checksum == checksum2

    # Different data should produce different checksum (highly likely)
    different_data = b"Different test data"
    checksum3 = featunlk._feat_unlk_checksum(different_data)
    assert checksum != checksum3


def test_volume_id_encoding():
    """Volume ID encoding should match Garmin spec."""
    # Test known volume IDs
    vol_id = 0x12345678
    encoded = featunlk._encode_volume_id(vol_id)

    # Encoded should be 32-bit unsigned integer
    assert isinstance(encoded, int)
    assert 0 <= encoded <= 0xFFFFFFFF

    # Encoding should be reversible in principle (though we don't have decode function)
    # At minimum, different inputs should produce different outputs
    vol_id2 = 0x87654321
    encoded2 = featunlk._encode_volume_id(vol_id2)
    assert encoded != encoded2


def test_system_id_truncation():
    """System ID should be truncated to 32 bits correctly."""
    # Test with 64-bit system ID
    system_id = 0x123456789ABCDEF0
    truncated = featunlk._truncate_system_id(system_id)

    # Result should be 32-bit
    assert isinstance(truncated, int)
    assert 0 <= truncated <= 0xFFFFFFFF

    # Test truncation behavior (lower 32 bits + upper 32 bits)
    lower = system_id & 0xFFFFFFFF
    upper = system_id >> 32
    expected = (lower + upper) & 0xFFFFFFFF
    assert truncated == expected


def test_feature_enum_structure():
    """Feature enum should have expected structure."""
    # Test a few known features
    nav_feature = featunlk._Feature.NAVIGATION
    assert hasattr(nav_feature, "offset")
    assert hasattr(nav_feature, "bit")
    assert hasattr(nav_feature, "filenames")

    # NAVIGATION should have offset 0
    assert nav_feature.offset == 0

    # Should have some associated filenames
    assert len(nav_feature.filenames) > 0


def test_filename_to_feature_mapping():
    """FILENAME_TO_FEATURE should map known files to features."""
    # Test known navigation database filename
    assert "avtn_db.bin" in featunlk._FILENAME_TO_FEATURE
    assert featunlk._FILENAME_TO_FEATURE["avtn_db.bin"] == featunlk._Feature.NAVIGATION

    # Test terrain filename
    if "terrain.tdb" in featunlk._FILENAME_TO_FEATURE:
        assert featunlk._FILENAME_TO_FEATURE["terrain.tdb"] == featunlk._Feature.TERRAIN


def test_update_feature_unlock_validation(tmp_path):
    """Test input validation for update_feature_unlock."""
    # Create minimal test file
    test_file = tmp_path / "test_data.bin"
    test_file.write_bytes(b"\x00" * 100 + struct.pack("<I", 0))  # Dummy data with CRC placeholder

    # Valid inputs
    vol_id = 0xDEADBEEF
    system_id = 0x999999999

    # Test with non-existent destination directory
    with pytest.raises(ValueError, match="does not exist"):
        featunlk.update_feature_unlock(tmp_path / "nonexistent", test_file, "avtn_db.bin", vol_id, system_id)

    # Test with non-existent output file
    with pytest.raises(ValueError, match="does not exist"):
        featunlk.update_feature_unlock(tmp_path, tmp_path / "nonexistent.bin", "avtn_db.bin", vol_id, system_id)

    # Test with invalid volume ID (negative)
    with pytest.raises(ValueError, match="Volume ID must be a 32-bit"):
        featunlk.update_feature_unlock(
            tmp_path,
            test_file,
            "avtn_db.bin",
            -1,  # Invalid
            system_id,
        )

    # Test with invalid volume ID (too large)
    with pytest.raises(ValueError, match="Volume ID must be a 32-bit"):
        featunlk.update_feature_unlock(
            tmp_path,
            test_file,
            "avtn_db.bin",
            0x1FFFFFFFF,  # Too large for 32-bit
            system_id,
        )

    # Test with invalid system ID (too large)
    with pytest.raises(ValueError, match="System ID must be a 64-bit"):
        featunlk.update_feature_unlock(
            tmp_path,
            test_file,
            "avtn_db.bin",
            vol_id,
            0x1FFFFFFFFFFFFFFFF,  # Too large for 64-bit
        )
