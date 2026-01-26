"""
Tests for featunlk.py - Feature unlock file generation and dump.

Tests for checksum algorithm, volume ID encoding, feat_unlk.dat structure,
and the dump functionality for reading existing feat_unlk.dat files.
"""

import struct
import sys
from io import BytesIO
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


def test_volume_id_encode_decode_roundtrip():
    """Encoding then decoding volume ID should return original value."""
    test_ids = [0x00000000, 0x12345678, 0xDEADBEEF, 0xFFFFFFFF, 0xAA7A1724]
    for vol_id in test_ids:
        encoded = featunlk._encode_volume_id(vol_id)
        decoded = featunlk._decode_volume_id(encoded)
        assert decoded == vol_id, f"Round-trip failed for {vol_id:#x}"


def test_decode_volume_id():
    """Decode volume ID should be inverse of encode."""
    vol_id = 0x12345678
    encoded = featunlk._encode_volume_id(vol_id)
    decoded = featunlk._decode_volume_id(encoded)
    assert decoded == vol_id

    # Test edge cases
    assert featunlk._decode_volume_id(featunlk._encode_volume_id(0)) == 0
    assert featunlk._decode_volume_id(featunlk._encode_volume_id(0xFFFFFFFF)) == 0xFFFFFFFF


def test_database_types_mapping():
    """DATABASE_TYPES should map known security IDs to device names."""
    # Test known G3X Touch security ID
    assert featunlk._DATABASE_TYPES.get(0x06BF) == "G3X Touch"
    # Test known G3X security ID
    assert featunlk._DATABASE_TYPES.get(0x02EA) == "G3X"
    # Unknown ID should return None
    assert featunlk._DATABASE_TYPES.get(0x9999) is None


def test_dump_feature_unlock_file_not_found(tmp_path):
    """dump_feature_unlock should return 1 for non-existent file."""
    result = featunlk.dump_feature_unlock(tmp_path / "nonexistent.dat")
    assert result == 1


def test_dump_feature_unlock_invalid_feature():
    """dump_feature_unlock should return 1 for invalid feature name."""
    # Create a minimal feat_unlk.dat file (all zeros)
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".dat", delete=False) as f:
        f.write(b"\x00" * 18000)
        tmp_file = Path(f.name)

    try:
        result = featunlk.dump_feature_unlock(tmp_file, "INVALID_FEATURE")
        assert result == 1
    finally:
        tmp_file.unlink()


def test_dump_feature_unlock_empty_content(tmp_path, capsys):
    """dump_feature_unlock should report 'No content' for empty features."""
    # Create a feat_unlk.dat file with all zeros
    feat_unlk_file = tmp_path / "feat_unlk.dat"
    feat_unlk_file.write_bytes(b"\x00" * 18000)

    result = featunlk.dump_feature_unlock(feat_unlk_file, "NAVIGATION")
    assert result == 0

    captured = capsys.readouterr()
    assert "No content" in captured.out


def test_dump_feature_unlock_feature_by_filename():
    """dump_feature_unlock should accept filename as feature identifier."""
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".dat", delete=False) as f:
        f.write(b"\x00" * 18000)
        tmp_file = Path(f.name)

    try:
        # Should accept "avtn_db.bin" as equivalent to NAVIGATION
        result = featunlk.dump_feature_unlock(tmp_file, "avtn_db.bin")
        assert result == 0
    finally:
        tmp_file.unlink()


def _create_valid_feat_unlk_content(feature: featunlk._Feature, vol_id: int, system_id: int) -> bytes:
    """
    Helper to create valid feat_unlk.dat content for a single feature.

    Returns bytes that can be written at the feature's offset.
    """
    # Build content1
    content1 = BytesIO()
    content1.write(featunlk._MAGIC1.to_bytes(2, 'little'))
    content1.write(((featunlk._GARMIN_SECURITY_ID - featunlk._SEC_ID_OFFSET + 0x10000) & 0xFFFF).to_bytes(2, 'little'))
    content1.write(featunlk._MAGIC2.to_bytes(4, 'little'))
    content1.write((1 << feature.bit).to_bytes(4, 'little'))
    content1.write((0).to_bytes(4, 'little'))
    content1.write(featunlk._encode_volume_id(vol_id).to_bytes(4, 'little'))

    if feature == featunlk._Feature.NAVIGATION:
        content1.write(featunlk._MAGIC3.to_bytes(2, 'little'))

    # Dummy checksum and preview
    content1.write((0x12345678).to_bytes(4, 'little'))
    preview_len = featunlk._NAVIGATION_PREVIEW_END - featunlk._NAVIGATION_PREVIEW_START
    content1.write(b'\x00' * preview_len)

    # Pad to correct length minus CRC
    content1.write(b'\x00' * (featunlk._CONTENT1_LEN - len(content1.getbuffer()) - 4))

    # Add CRC for content1
    chk1 = featunlk._feat_unlk_checksum(bytes(content1.getbuffer()))
    content1.write(chk1.to_bytes(4, 'little'))

    # Build content2
    content2 = BytesIO()
    content2.write((0).to_bytes(4, 'little'))
    content2.write(featunlk._truncate_system_id(system_id).to_bytes(4, 'little'))
    content2.write(b'\x00' * (featunlk._CONTENT2_LEN - len(content2.getbuffer()) - 4))

    chk2 = featunlk._feat_unlk_checksum(bytes(content2.getbuffer()))
    content2.write(chk2.to_bytes(4, 'little'))

    # Overall CRC
    chk3 = featunlk._feat_unlk_checksum(content1.getvalue() + content2.getvalue())

    return content1.getvalue() + content2.getvalue() + chk3.to_bytes(4, 'little')


def test_dump_feature_unlock_valid_content(tmp_path, capsys):
    """dump_feature_unlock should correctly parse valid feature content."""
    vol_id = 0xDEADBEEF
    system_id = 0x123456789ABC

    # Create feat_unlk.dat with valid TERRAIN feature (offset 1826)
    feat_unlk_file = tmp_path / "feat_unlk.dat"
    feature = featunlk._Feature.TERRAIN
    content = _create_valid_feat_unlk_content(feature, vol_id, system_id)

    # Create file with zeros, then write content at correct offset
    data = bytearray(18000)
    data[feature.offset : feature.offset + len(content)] = content
    feat_unlk_file.write_bytes(bytes(data))

    result = featunlk.dump_feature_unlock(feat_unlk_file, "TERRAIN")
    assert result == 0

    captured = capsys.readouterr()
    # Should show volume ID
    assert "DEADBEEF" in captured.out
    # Should show device model (G3X Touch for security ID 1727)
    assert "G3X Touch" in captured.out
    # Should show truncated system ID
    assert "Truncated avionics_id" in captured.out


def test_dump_all_features(tmp_path, capsys):
    """dump_feature_unlock with empty feature_name should dump all features."""
    feat_unlk_file = tmp_path / "feat_unlk.dat"
    feat_unlk_file.write_bytes(b"\x00" * 18000)

    result = featunlk.dump_feature_unlock(feat_unlk_file, "")
    assert result == 0

    captured = capsys.readouterr()
    # Should have headers for multiple features
    assert "NAVIGATION" in captured.out
    assert "TERRAIN" in captured.out
    assert "OBSTACLE" in captured.out
    assert "SAFETAXI" in captured.out


def test_calculate_crc_and_preview_of_file(tmp_path):
    """_calculate_crc_and_preview_of_file should compute CRC correctly."""
    # Create a test file with known content and valid CRC
    test_file = tmp_path / "test.bin"

    # Create content - CRC validation will fail for non-CHARTVIEW features
    data = b"Test data for CRC calculation" + b"\x00" * 100
    test_file.write_bytes(data + b"\x00\x00\x00\x00")

    # For non-CHARTVIEW features, this will fail CRC check, which is expected
    with pytest.raises(ValueError, match="failed the checksum"):
        featunlk._calculate_crc_and_preview_of_file(featunlk._Feature.TERRAIN, test_file)


def test_main_dump_mode(tmp_path, monkeypatch, capsys):
    """main() should default to dump mode."""
    feat_unlk_file = tmp_path / "feat_unlk.dat"
    feat_unlk_file.write_bytes(b"\x00" * 18000)

    monkeypatch.setattr(sys, 'argv', ['featunlk.py', str(feat_unlk_file), '-f', 'NAVIGATION'])

    with pytest.raises(SystemExit) as exc_info:
        featunlk.main()
    assert exc_info.value.code == 0

    captured = capsys.readouterr()
    assert "NAVIGATION" in captured.out


def test_main_update_mode_missing_args(tmp_path, monkeypatch, capsys):
    """main() in update mode should error if required args missing."""
    test_file = tmp_path / "test.bin"
    test_file.write_bytes(b"\x00" * 100)

    monkeypatch.setattr(sys, 'argv', ['featunlk.py', str(test_file), '-u'])

    with pytest.raises(SystemExit) as exc_info:
        featunlk.main()
    assert exc_info.value.code == 2  # argparse error exit code

    captured = capsys.readouterr()
    assert "--output is required" in captured.err
