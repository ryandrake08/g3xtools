"""
Tests for sdcard.py - Volume serial number reading and SD card detection.

Tests cover FAT32 volume serial number extraction and SD card detection logic.
Platform-specific functionality (unix_vsn, windows_vsn) uses mocking to avoid
requiring actual hardware devices.
"""

import sys
from pathlib import Path
from unittest import mock

import pytest

# Import the sdcard module
sys.path.insert(0, str(Path(__file__).parent.parent))
import sdcard


def test_unix_vsn_valid_fat32(tmp_path):
    """Read volume serial number from valid FAT32 device."""
    # Create a mock FAT32 boot sector
    device_file = tmp_path / "mock_device"

    # FAT32 boot sector structure (simplified)
    boot_sector = bytearray(512)

    # FAT32 signature at offset 82
    boot_sector[82 : 82 + 8] = b'FAT32   '

    # Volume serial number at offset 67 (4 bytes little-endian)
    # Example: 0x12345678
    boot_sector[67:71] = (0x12345678).to_bytes(4, 'little')

    device_file.write_bytes(boot_sector)

    vsn = sdcard._unix_vsn(str(device_file))

    assert vsn == 0x12345678


def test_unix_vsn_invalid_signature(tmp_path):
    """Reject device with invalid FAT32 signature."""
    device_file = tmp_path / "mock_device"

    # Boot sector with wrong signature
    boot_sector = bytearray(512)
    boot_sector[82 : 82 + 8] = b'NOTFAT32'
    boot_sector[67:71] = (0x12345678).to_bytes(4, 'little')

    device_file.write_bytes(boot_sector)

    with pytest.raises(ValueError, match="does not appear to be FAT32"):
        sdcard._unix_vsn(str(device_file))


def test_unix_vsn_short_read(tmp_path):
    """Reject device with incomplete boot sector."""
    device_file = tmp_path / "mock_device"

    # Write less than 512 bytes
    device_file.write_bytes(b'\x00' * 100)

    with pytest.raises(ValueError, match="Short read from device"):
        sdcard._unix_vsn(str(device_file))


def test_unix_vsn_nonexistent_device(tmp_path):
    """Handle nonexistent device gracefully."""
    bad_device = tmp_path / "does_not_exist"

    with pytest.raises(OSError, match="Error opening device"):
        sdcard._unix_vsn(str(bad_device))


def test_windows_vsn_valid_drive():
    """Read volume serial number from Windows drive (mocked)."""
    # Mock win32api.GetVolumeInformation
    mock_volume_info = ('SDCARD', 0xABCD1234, 255, 0, 'FAT32')

    mock_win32 = mock.Mock()
    mock_win32.GetVolumeInformation.return_value = mock_volume_info

    with mock.patch.dict('sys.modules', {'win32api': mock_win32}):
        vsn = sdcard._windows_vsn('D:')

        assert vsn == 0xABCD1234
        mock_win32.GetVolumeInformation.assert_called_once_with('D:\\')


def test_windows_vsn_normalize_drive_letter():
    """Normalize drive letter formats."""
    mock_volume_info = ('SDCARD', 0x12345678, 255, 0, 'FAT32')

    mock_win32 = mock.Mock()
    mock_win32.GetVolumeInformation.return_value = mock_volume_info

    with mock.patch.dict('sys.modules', {'win32api': mock_win32}):
        # Test different input formats
        vsn1 = sdcard._windows_vsn('D')
        vsn2 = sdcard._windows_vsn('D:')
        vsn3 = sdcard._windows_vsn('D:\\')

        assert vsn1 == vsn2 == vsn3 == 0x12345678

        # All should be normalized to 'D:\\'
        for call in mock_win32.GetVolumeInformation.call_args_list:
            assert call[0][0] == 'D:\\'


def test_windows_vsn_error_handling():
    """Handle Windows API errors."""
    mock_win32 = mock.Mock()
    mock_win32.GetVolumeInformation.side_effect = OSError("Device not ready")

    with (
        mock.patch.dict('sys.modules', {'win32api': mock_win32}),
        pytest.raises(OSError, match="Error accessing drive"),
    ):
        sdcard._windows_vsn('D:')


def test_read_vsn_unix_platform(tmp_path):
    """Route to unix_vsn on Unix platforms."""
    device_file = tmp_path / "mock_device"

    # Create valid FAT32 boot sector
    boot_sector = bytearray(512)
    boot_sector[82 : 82 + 8] = b'FAT32   '
    boot_sector[67:71] = (0x87654321).to_bytes(4, 'little')
    device_file.write_bytes(boot_sector)

    with mock.patch('sys.platform', 'linux'):
        vsn = sdcard.read_vsn(str(device_file))
        assert vsn == 0x87654321

    with mock.patch('sys.platform', 'darwin'):
        vsn = sdcard.read_vsn(str(device_file))
        assert vsn == 0x87654321


def test_read_vsn_windows_platform():
    """Route to windows_vsn on Windows platform."""
    mock_volume_info = ('SDCARD', 0x11223344, 255, 0, 'FAT32')

    mock_win32 = mock.Mock()
    mock_win32.GetVolumeInformation.return_value = mock_volume_info

    with mock.patch('sys.platform', 'win32'), mock.patch.dict('sys.modules', {'win32api': mock_win32}):
        vsn = sdcard.read_vsn('D:')
        assert vsn == 0x11223344


def test_get_platform_device_example():
    """Get platform-specific device path examples."""
    with mock.patch('sys.platform', 'darwin'):
        assert sdcard._get_platform_device_example() == "/dev/rdisk2s1"

    with mock.patch('sys.platform', 'linux'):
        assert sdcard._get_platform_device_example() == "/dev/sdb1"

    with mock.patch('sys.platform', 'win32'):
        assert sdcard._get_platform_device_example() == "D:"

    with mock.patch('sys.platform', 'unknown_os'):
        assert sdcard._get_platform_device_example() == "/dev/block_device"


def test_detect_sd_card_no_psutil():
    """Handle missing psutil library gracefully."""
    with mock.patch.dict('sys.modules', {'psutil': None}), mock.patch('builtins.__import__', side_effect=ImportError):
        result = sdcard.detect_sd_card()
        assert result == ""


def test_detect_sd_card_single_candidate():
    """Detect single SD card candidate."""
    try:
        import psutil  # noqa: F401
    except ImportError:
        pytest.skip("psutil not available")

    # Mock partition that matches SD card criteria
    mock_partition = mock.Mock()
    mock_partition.mountpoint = '/media/sdcard'
    mock_partition.fstype = 'fat32'

    with (
        mock.patch('psutil.disk_partitions', return_value=[mock_partition]),
        mock.patch('shutil.disk_usage', return_value=(16 * 1024**3, 0, 0)),
    ):  # 16 GB
        result = sdcard.detect_sd_card()
        assert result == '/media/sdcard'


def test_detect_sd_card_multiple_candidates():
    """Prefer smaller SD card when multiple found."""
    try:
        import psutil  # noqa: F401
    except ImportError:
        pytest.skip("psutil not available")

    # Mock two partitions
    mock_partition1 = mock.Mock()
    mock_partition1.mountpoint = '/media/sdcard1'
    mock_partition1.fstype = 'fat32'

    mock_partition2 = mock.Mock()
    mock_partition2.mountpoint = '/media/sdcard2'
    mock_partition2.fstype = 'fat32'

    def mock_disk_usage(path):
        if path == '/media/sdcard1':
            return (32 * 1024**3, 0, 0)  # 32 GB
        else:
            return (16 * 1024**3, 0, 0)  # 16 GB

    with (
        mock.patch('psutil.disk_partitions', return_value=[mock_partition1, mock_partition2]),
        mock.patch('shutil.disk_usage', side_effect=mock_disk_usage),
    ):
        result = sdcard.detect_sd_card()
        # Should prefer smaller (16 GB)
        assert result == '/media/sdcard2'


def test_detect_sd_card_filter_system_partitions_mac():
    """Filter out system partitions on macOS."""
    try:
        import psutil  # noqa: F401
    except ImportError:
        pytest.skip("psutil not available")

    # Mock system and SD card partitions
    system_partition = mock.Mock()
    system_partition.mountpoint = '/'
    system_partition.fstype = 'apfs'

    sd_partition = mock.Mock()
    sd_partition.mountpoint = '/Volumes/SDCARD'
    sd_partition.fstype = 'msdos'

    with (
        mock.patch('sys.platform', 'darwin'),
        mock.patch('psutil.disk_partitions', return_value=[system_partition, sd_partition]),
        mock.patch('shutil.disk_usage', return_value=(16 * 1024**3, 0, 0)),
    ):
        result = sdcard.detect_sd_card()
        assert result == '/Volumes/SDCARD'


def test_detect_sd_card_filter_by_filesystem():
    """Filter partitions by filesystem type."""
    try:
        import psutil  # noqa: F401
    except ImportError:
        pytest.skip("psutil not available")

    # Mock partitions with different filesystems
    ntfs_partition = mock.Mock()
    ntfs_partition.mountpoint = '/media/ntfs'
    ntfs_partition.fstype = 'ntfs'

    fat32_partition = mock.Mock()
    fat32_partition.mountpoint = '/media/sdcard'
    fat32_partition.fstype = 'fat32'

    with (
        mock.patch('psutil.disk_partitions', return_value=[ntfs_partition, fat32_partition]),
        mock.patch('shutil.disk_usage', return_value=(16 * 1024**3, 0, 0)),
    ):
        result = sdcard.detect_sd_card()
        # Should only return FAT32
        assert result == '/media/sdcard'


def test_detect_sd_card_filter_by_size():
    """Filter partitions by size range."""
    try:
        import psutil  # noqa: F401
    except ImportError:
        pytest.skip("psutil not available")

    # Mock partitions with different sizes
    too_small = mock.Mock()
    too_small.mountpoint = '/media/small'
    too_small.fstype = 'fat32'

    just_right = mock.Mock()
    just_right.mountpoint = '/media/sdcard'
    just_right.fstype = 'fat32'

    too_large = mock.Mock()
    too_large.mountpoint = '/media/large'
    too_large.fstype = 'fat32'

    def mock_disk_usage(path):
        if path == '/media/small':
            return (2 * 1024**3, 0, 0)  # 2 GB - too small
        elif path == '/media/large':
            return (128 * 1024**3, 0, 0)  # 128 GB - too large
        else:
            return (16 * 1024**3, 0, 0)  # 16 GB - just right

    with (
        mock.patch('psutil.disk_partitions', return_value=[too_small, just_right, too_large]),
        mock.patch('shutil.disk_usage', side_effect=mock_disk_usage),
    ):
        result = sdcard.detect_sd_card()
        assert result == '/media/sdcard'


def test_detect_sd_card_no_candidates():
    """Return empty string when no SD cards found."""
    try:
        import psutil  # noqa: F401
    except ImportError:
        pytest.skip("psutil not available")

    # Mock partition that doesn't match criteria
    mock_partition = mock.Mock()
    mock_partition.mountpoint = '/media/usb'
    mock_partition.fstype = 'ntfs'  # Not FAT32

    with (
        mock.patch('psutil.disk_partitions', return_value=[mock_partition]),
        mock.patch('shutil.disk_usage', return_value=(16 * 1024**3, 0, 0)),
    ):
        result = sdcard.detect_sd_card()
        assert result == ""


# Tests for caching functionality


def test_get_mount_point_darwin():
    """Get mount point from device on macOS."""
    mock_output = """
   Device Identifier:        disk2s1
   Device Node:              /dev/disk2s1
   Mount Point:              /Volumes/GARMIN
   Volume Name:              GARMIN
"""
    with mock.patch('sys.platform', 'darwin'), mock.patch('subprocess.run') as mock_run:
        mock_run.return_value = mock.Mock(returncode=0, stdout=mock_output)

        result = sdcard._get_mount_point('/dev/disk2s1')

        assert result == '/Volumes/GARMIN'
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ['diskutil', 'info', '/dev/disk2s1']


def test_get_mount_point_linux():
    """Get mount point from device on Linux."""
    with mock.patch('sys.platform', 'linux'), mock.patch('subprocess.run') as mock_run:
        mock_run.return_value = mock.Mock(returncode=0, stdout='/media/sdcard\n')

        result = sdcard._get_mount_point('/dev/sdb1')

        assert result == '/media/sdcard'
        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == ['findmnt', '-n', '-o', 'TARGET', '/dev/sdb1']


def test_get_mount_point_windows():
    """Get mount point from device on Windows."""
    with mock.patch('sys.platform', 'win32'):
        assert sdcard._get_mount_point('D:') == 'D:\\'
        assert sdcard._get_mount_point('D:\\') == 'D:\\'
        assert sdcard._get_mount_point('E') == 'E:\\'


def test_get_mount_point_not_mounted():
    """Return empty string when device not mounted."""
    mock_output = """
   Device Identifier:        disk2s1
   Mount Point:              Not applicable (no file system)
"""
    with mock.patch('sys.platform', 'darwin'), mock.patch('subprocess.run') as mock_run:
        mock_run.return_value = mock.Mock(returncode=0, stdout=mock_output)

        result = sdcard._get_mount_point('/dev/disk2s1')

        assert result == ''


def test_get_mount_point_error():
    """Return empty string on error."""
    with mock.patch('sys.platform', 'darwin'), mock.patch('subprocess.run', side_effect=OSError("Command failed")):
        result = sdcard._get_mount_point('/dev/disk2s1')

        assert result == ''


def test_get_volume_label_darwin():
    """Get volume label on macOS."""
    mock_output = """
   Device Identifier:        disk2s1
   Volume Name:              GARMIN
"""
    with mock.patch('sys.platform', 'darwin'), mock.patch('subprocess.run') as mock_run:
        mock_run.return_value = mock.Mock(returncode=0, stdout=mock_output)

        result = sdcard._get_volume_label('/Volumes/GARMIN')

        assert result == 'GARMIN'


def test_get_volume_label_linux():
    """Get volume label on Linux."""
    with mock.patch('sys.platform', 'linux'), mock.patch('subprocess.run') as mock_run:
        mock_run.return_value = mock.Mock(returncode=0, stdout='SDCARD\n')

        result = sdcard._get_volume_label('/media/sdcard')

        assert result == 'SDCARD'
        # Should try lsblk first
        assert mock_run.call_args[0][0] == ['lsblk', '-n', '-o', 'LABEL', '/media/sdcard']


def test_get_volume_label_linux_fallback():
    """Use findmnt as fallback on Linux."""
    with mock.patch('sys.platform', 'linux'), mock.patch('subprocess.run') as mock_run:
        # lsblk fails, findmnt succeeds
        mock_run.side_effect = [mock.Mock(returncode=1, stdout=''), mock.Mock(returncode=0, stdout='SDCARD\n')]

        result = sdcard._get_volume_label('/media/sdcard')

        assert result == 'SDCARD'
        assert mock_run.call_count == 2


def test_get_volume_label_windows():
    """Get volume label on Windows."""
    mock_output = """Label
SDCARD
"""
    with mock.patch('sys.platform', 'win32'), mock.patch('subprocess.run') as mock_run:
        mock_run.return_value = mock.Mock(returncode=0, stdout=mock_output)

        result = sdcard._get_volume_label('D:')

        assert result == 'SDCARD'


def test_get_volume_label_empty():
    """Handle volumes with no label."""
    with mock.patch('sys.platform', 'linux'), mock.patch('subprocess.run') as mock_run:
        mock_run.return_value = mock.Mock(returncode=0, stdout='\n')

        result = sdcard._get_volume_label('/media/sdcard')

        assert result == ''


def test_get_volume_label_error():
    """Return empty string on error."""
    with mock.patch('sys.platform', 'darwin'), mock.patch('subprocess.run', side_effect=OSError("Command failed")):
        result = sdcard._get_volume_label('/Volumes/GARMIN')

        assert result == ''


def test_make_cache_key():
    """Create cache key from label and size."""
    # 16 GB card
    key = sdcard._make_cache_key('GARMIN', 16 * 1024**3)
    assert key == 'GARMIN:16.0GB'

    # 32 GB card
    key = sdcard._make_cache_key('SDCARD', 32 * 1024**3)
    assert key == 'SDCARD:32.0GB'

    # Round to nearest 0.1 GB
    key = sdcard._make_cache_key('TEST', int(15.87 * 1024**3))
    assert key == 'TEST:15.9GB'


def test_cache_vsn_and_get_cached_vsn(tmp_path):
    """Cache and retrieve VSN."""
    mount_point = '/media/sdcard'
    vsn = 0xABCD1234

    with (
        mock.patch('sdcard._get_vsn_cache_path', return_value=tmp_path / 'vsn_cache.json'),
        mock.patch('sdcard._get_volume_label', return_value='GARMIN'),
        mock.patch('shutil.disk_usage', return_value=(16 * 1024**3, 0, 0)),
    ):
        # Cache the VSN
        sdcard._cache_vsn(mount_point, vsn)

        # Retrieve it
        cached_vsn = sdcard._get_cached_vsn(mount_point)

        assert cached_vsn == vsn


def test_get_cached_vsn_not_found(tmp_path):
    """Return None when VSN not in cache."""
    mount_point = '/media/sdcard'

    with (
        mock.patch('sdcard._get_vsn_cache_path', return_value=tmp_path / 'vsn_cache.json'),
        mock.patch('sdcard._get_volume_label', return_value='GARMIN'),
        mock.patch('shutil.disk_usage', return_value=(16 * 1024**3, 0, 0)),
    ):
        cached_vsn = sdcard._get_cached_vsn(mount_point)

        assert cached_vsn is None


def test_get_cached_vsn_different_size(tmp_path):
    """Don't match VSN if size differs."""
    mount_point = '/media/sdcard'
    vsn = 0xABCD1234

    with (
        mock.patch('sdcard._get_vsn_cache_path', return_value=tmp_path / 'vsn_cache.json'),
        mock.patch('sdcard._get_volume_label', return_value='GARMIN'),
    ):
        # Cache with 16GB size
        with mock.patch('shutil.disk_usage', return_value=(16 * 1024**3, 0, 0)):
            sdcard._cache_vsn(mount_point, vsn)

        # Try to retrieve with 32GB size
        with mock.patch('shutil.disk_usage', return_value=(32 * 1024**3, 0, 0)):
            cached_vsn = sdcard._get_cached_vsn(mount_point)
            assert cached_vsn is None


def test_cache_vsn_multiple_cards(tmp_path):
    """Cache multiple cards with same label but different sizes."""
    vsn1 = 0x11111111
    vsn2 = 0x22222222

    with (
        mock.patch('sdcard._get_vsn_cache_path', return_value=tmp_path / 'vsn_cache.json'),
        mock.patch('sdcard._get_volume_label', return_value='GARMIN'),
    ):
        # Cache 16GB card
        with mock.patch('shutil.disk_usage', return_value=(16 * 1024**3, 0, 0)):
            sdcard._cache_vsn('/media/sdcard1', vsn1)

        # Cache 32GB card with same label
        with mock.patch('shutil.disk_usage', return_value=(32 * 1024**3, 0, 0)):
            sdcard._cache_vsn('/media/sdcard2', vsn2)

        # Retrieve both
        with mock.patch('shutil.disk_usage', return_value=(16 * 1024**3, 0, 0)):
            assert sdcard._get_cached_vsn('/media/sdcard1') == vsn1

        with mock.patch('shutil.disk_usage', return_value=(32 * 1024**3, 0, 0)):
            assert sdcard._get_cached_vsn('/media/sdcard2') == vsn2


def test_cache_vsn_error_handling(tmp_path):
    """Handle errors gracefully when caching."""
    # Should not raise exception even if caching fails
    with (
        mock.patch('sdcard._get_vsn_cache_path', return_value=tmp_path / 'readonly' / 'vsn_cache.json'),
        mock.patch('sdcard._get_volume_label', return_value='GARMIN'),
        mock.patch('shutil.disk_usage', return_value=(16 * 1024**3, 0, 0)),
    ):
        # Should not raise
        sdcard._cache_vsn('/media/sdcard', 0x12345678)


def test_get_cached_vsn_corrupted_cache(tmp_path):
    """Handle corrupted cache file gracefully."""
    cache_file = tmp_path / 'vsn_cache.json'
    cache_file.write_text('not valid json{')

    with (
        mock.patch('sdcard._get_vsn_cache_path', return_value=cache_file),
        mock.patch('sdcard._get_volume_label', return_value='GARMIN'),
        mock.patch('shutil.disk_usage', return_value=(16 * 1024**3, 0, 0)),
    ):
        # Should return None, not raise
        cached_vsn = sdcard._get_cached_vsn('/media/sdcard')
        assert cached_vsn is None


def test_clear_vsn_cache(tmp_path):
    """Clear the VSN cache."""
    cache_file = tmp_path / 'vsn_cache.json'
    cache_file.write_text('{"GARMIN:16.0GB": "ABCD1234"}')

    with mock.patch('sdcard._get_vsn_cache_path', return_value=cache_file):
        sdcard._clear_vsn_cache()

        assert not cache_file.exists()


def test_clear_vsn_cache_nonexistent():
    """Clearing nonexistent cache doesn't error."""
    with mock.patch('sdcard._get_vsn_cache_path', return_value=Path('/nonexistent/vsn_cache.json')):
        # Should not raise
        sdcard._clear_vsn_cache()


def test_get_vsn_with_explicit_vsn():
    """Use explicit VSN when provided."""
    vsn = sdcard.get_vsn('A1B2C3D4', None, verbose=False)
    assert vsn == 0xA1B2C3D4


def test_get_vsn_invalid_hex():
    """Handle invalid hex VSN gracefully."""
    vsn = sdcard.get_vsn('NOTAHEX', None, verbose=False)
    assert vsn is None


def test_get_vsn_from_cache(tmp_path):
    """Retrieve VSN from cache when not explicitly provided."""
    mount_point = '/media/sdcard'
    cached_vsn = 0x12345678

    with (
        mock.patch('sdcard._get_vsn_cache_path', return_value=tmp_path / 'vsn_cache.json'),
        mock.patch('sdcard._get_volume_label', return_value='GARMIN'),
        mock.patch('shutil.disk_usage', return_value=(16 * 1024**3, 0, 0)),
    ):
        # Pre-populate cache
        sdcard._cache_vsn(mount_point, cached_vsn)

        # Retrieve via get_vsn
        vsn = sdcard.get_vsn(None, mount_point, verbose=False)
        assert vsn == cached_vsn


def test_get_vsn_auto_detect_sd_card(tmp_path):
    """Auto-detect SD card when no output path provided."""
    try:
        import psutil  # noqa: F401
    except ImportError:
        pytest.skip("psutil not available")

    mount_point = '/media/sdcard'
    cached_vsn = 0x87654321

    # Mock SD card detection
    mock_partition = mock.Mock()
    mock_partition.mountpoint = mount_point
    mock_partition.fstype = 'fat32'

    with (
        mock.patch('sdcard._get_vsn_cache_path', return_value=tmp_path / 'vsn_cache.json'),
        mock.patch('sdcard._get_volume_label', return_value='GARMIN'),
        mock.patch('shutil.disk_usage', return_value=(16 * 1024**3, 0, 0)),
        mock.patch('psutil.disk_partitions', return_value=[mock_partition]),
    ):
        # Pre-populate cache
        sdcard._cache_vsn(mount_point, cached_vsn)

        # Auto-detect and retrieve
        vsn = sdcard.get_vsn(None, None, verbose=False)
        assert vsn == cached_vsn


def test_get_vsn_not_in_cache():
    """Return None and print warning when VSN not in cache."""
    mount_point = '/media/sdcard'

    with (
        mock.patch('sdcard._get_cached_vsn', return_value=None),
        mock.patch('sdcard._get_platform_device_example', return_value='/dev/sdb1'),
    ):
        vsn = sdcard.get_vsn(None, mount_point, verbose=False)
        assert vsn is None


def test_get_vsn_verbose_output(tmp_path, capsys):
    """Test verbose output messages."""
    mount_point = '/media/sdcard'
    cached_vsn = 0xABCDEF12

    with (
        mock.patch('sdcard._get_vsn_cache_path', return_value=tmp_path / 'vsn_cache.json'),
        mock.patch('sdcard._get_volume_label', return_value='GARMIN'),
        mock.patch('shutil.disk_usage', return_value=(16 * 1024**3, 0, 0)),
    ):
        # Pre-populate cache
        sdcard._cache_vsn(mount_point, cached_vsn)

        # Retrieve with verbose=True
        vsn = sdcard.get_vsn(None, mount_point, verbose=True)

        assert vsn == cached_vsn

        # Check verbose output
        captured = capsys.readouterr()
        assert 'Checking VSN cache' in captured.out
        assert 'Using cached VSN: ABCDEF12' in captured.out
