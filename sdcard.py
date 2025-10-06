#!/usr/bin/env python3
"""
sdcard.py

Read volume serial number from FAT volume and detect SD card mount points.
Assumes FAT32 format and reads VSN from offset 67.

Usage: python3 sdcard.py /dev/diskN
"""

import sys
import shutil

# FAT32 filesystem constants
SECTOR_SIZE = 512
FAT32_VSN_OFFSET = 67  # FAT32 volume serial number offset

# SD card detection thresholds (per Garmin specifications)
SD_CARD_MIN_SIZE_GB = 7.5   # Minimum size to consider as SD card
SD_CARD_MAX_SIZE_GB = 33.0  # Maximum size to consider as SD card

def unix_vsn(device_path: str) -> int:
    """Extract volume serial number from FAT32 device and return as integer."""
    try:
        with open(device_path, 'rb') as fp:
            buffer = fp.read(SECTOR_SIZE)

            if len(buffer) != SECTOR_SIZE:
                raise ValueError(f"Could only read {len(buffer)} bytes, expected {SECTOR_SIZE}")

            # Extract 4 bytes at FAT32_VSN_OFFSET and convert to integer (little-endian order)
            vsn_bytes = buffer[FAT32_VSN_OFFSET:FAT32_VSN_OFFSET + 4]
            return int.from_bytes(vsn_bytes, byteorder='little')

    except IOError as e:
        raise IOError(f"Error opening device {device_path}: {e}")

def windows_vsn(drive_letter: str) -> int:
    """Extract volume serial number from Windows drive and return as integer."""
    import win32api # pyright: ignore[reportMissingModuleSource]

    # Normalize drive letter format (ensure it ends with :\)
    if not drive_letter.endswith(':\\'):
        if drive_letter.endswith(':'):
            drive_letter += '\\'
        else:
            drive_letter = drive_letter.upper() + ':\\'

    try:
        # GetVolumeInformation returns (label, serial, max_filename_len, flags, filesystem)
        volume_info = win32api.GetVolumeInformation(drive_letter)
        return volume_info[1]  # serial number is at index 1
    except Exception as e:
        raise IOError(f"Error accessing drive {drive_letter}: {e}")

def get_platform_device_example() -> str:
    """Get platform-specific device path example"""
    if sys.platform == 'darwin':
        return "/dev/rdisk2s1"
    elif sys.platform.startswith('linux'):
        return "/dev/sdb1"
    elif sys.platform == 'win32':
        return "D:"
    else:
        return "/dev/block_device"

def detect_sd_card() -> str:
    """Detect and select SD card mount point.

    Returns:
        Path to SD card mount point, or empty string if no suitable candidate found

    Filters by:
    - FAT32 filesystem only (includes 'msdos' which may be FAT32)
    - SD card sizes between 8-32 GB only
    - Excludes system mount points
    """
    try:
        import psutil
    except ImportError:
        print("Warning: psutil library not available for SD card detection", file=sys.stderr)
        return ""

    candidates = []

    for partition in psutil.disk_partitions():
        mountpoint = partition.mountpoint

        # Skip system partitions
        if sys.platform == 'darwin' and mountpoint in ['/', '/System', '/Library', '/Applications', '/usr', '/var']:
            continue
        if sys.platform.startswith('linux') and mountpoint in ['/', '/boot', '/home', '/usr', '/var']:
            continue
        if sys.platform == 'win32' and mountpoint.upper() in ['C:\\']:
            continue

        # Filter for FAT32 filesystem only (msdos on macOS is typically FAT32)
        if partition.fstype.lower() not in ['fat32', 'msdos']:
            continue

        # Check if size matches SD card sizes (8-32 GB)
        try:
            total, _, _ = shutil.disk_usage(mountpoint)
            size_gb = total / (1024**3)

            # Only accept SD cards within expected size range
            if SD_CARD_MIN_SIZE_GB <= size_gb <= SD_CARD_MAX_SIZE_GB:
                candidates.append({
                    'path': mountpoint,
                    'size_gb': size_gb
                })
        except:
            continue

    # Selection logic
    if len(candidates) == 0:
        print("Warning: No suitable SD card detected", file=sys.stderr)
        return ""
    elif len(candidates) == 1:
        return candidates[0]['path']
    else:
        # Multiple candidates - prefer smaller sizes (more likely to be SD cards vs external drives)
        candidates.sort(key=lambda x: x['size_gb'])
        print(f"Warning: Multiple SD card candidates found. Selecting smallest: {candidates[0]['path']}")
        return candidates[0]['path']

def read_vsn(device: str) -> int:
    """Read volume serial number from device using appropriate platform-specific method.

    Args:
        device: Device path (Unix: /dev/rdisk2s1, Windows: D:)

    Returns:
        Volume serial number as integer

    Raises:
        IOError: If device cannot be accessed or read
        ValueError: If device path is invalid or data cannot be parsed
    """
    # Use appropriate function based on platform
    if sys.platform == 'win32':
        return windows_vsn(device)
    else:
        return unix_vsn(device)

def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python3 sdcard.py <device>", file=sys.stderr)
        print("Example: python3 sdcard.py /dev/sdb1 (Linux) or python3 sdcard.py /dev/rdisk2s1 (Mac) or python3 sdcard.py D: (Windows)", file=sys.stderr)
        sys.exit(1)

    try:
        result = read_vsn(sys.argv[1])
        print(f"{result:08X}")
    except (IOError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()