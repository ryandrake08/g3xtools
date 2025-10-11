#!/usr/bin/env python3
"""
SD Card Volume Serial Number Reader with Caching

Reads volume serial numbers from FAT32 block devices and automatically caches them
based on mount point's volume label and size to avoid requiring elevated privileges
on subsequent reads.

Usage:
    python3 sdcard.py /dev/rdisk2s1               # Read VSN from device (requires sudo on Unix)
    python3 sdcard.py --cached /Volumes/GARMIN    # Check cached VSN for mount point
    python3 sdcard.py --label /Volumes/GARMIN     # Show volume label
    python3 sdcard.py --clear-cache               # Clear VSN cache

Workflow:
    1. Run once with sudo to read VSN from block device (e.g., /dev/rdisk2s1)
    2. VSN is automatically cached using the mount point (e.g., /Volumes/GARMIN)
    3. Subsequent tools can use get_vsn() to retrieve cached VSN without privileges

Caching:
    VSNs are cached by volume label + size (e.g., "GARMIN:16.0GB") in
    ~/.cache/g3xtools/vsn_cache.json. The mount point is automatically determined
    from the block device path.
"""

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
from typing import Optional, Union

import cache

# Public API
__all__ = [
    'read_vsn',
    'detect_sd_card',
    'get_vsn',
]

# FAT32 filesystem constants
SECTOR_SIZE = 512
FAT32_VSN_OFFSET = 67  # FAT32 volume serial number offset
FAT32_SIGNATURE_OFFSET = 82  # "FAT32   " string location
FAT32_SIGNATURE = b'FAT32   '  # Expected filesystem type string

# SD card detection thresholds (per Garmin specifications)
SD_CARD_MIN_SIZE_GB = 7.0   # Minimum size to consider as SD card
SD_CARD_MAX_SIZE_GB = 33.0  # Maximum size to consider as SD card

# VSN cache file
def _get_vsn_cache_path() -> pathlib.Path:
    """Get path to VSN cache file"""
    cache_dir = cache.user_cache_path('g3xtools', 'g3xtools')
    return cache_dir / 'vsn_cache.json'

def _get_mount_point(device: str) -> str:
    """
    Get mount point for a device.

    Works cross-platform without requiring elevated privileges.

    Args:
        device: Device path (e.g., /dev/sdb1, /dev/rdisk2s1, D:)

    Returns:
        Mount point path as string, or empty string if not mounted or error
    """
    try:
        if sys.platform == 'darwin':
            # macOS: use diskutil info
            result = subprocess.run(
                ['diskutil', 'info', device],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if 'Mount Point:' in line:
                        mount_point = line.split('Mount Point:', 1)[1].strip()
                        return mount_point if mount_point != 'Not applicable (no file system)' else ''

        elif sys.platform.startswith('linux'):
            # Linux: use findmnt
            result = subprocess.run(
                ['findmnt', '-n', '-o', 'TARGET', device],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()

        elif sys.platform == 'win32':
            # Windows: drive letter is the mount point
            # Normalize to drive letter only
            if device.endswith(':\\'):
                return device
            elif device.endswith(':'):
                return device + '\\'
            else:
                return device.upper() + ':\\'

    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        pass

    return ''

def _get_volume_label(path: str) -> str:
    """
    Read volume label from mounted filesystem.

    Works cross-platform without requiring elevated privileges.

    Args:
        path: Mount point (Unix/Mac) or drive letter (Windows)

    Returns:
        Volume label as string, or empty string if no label or error
    """
    try:
        if sys.platform == 'darwin':
            # macOS: use diskutil info
            result = subprocess.run(
                ['diskutil', 'info', path],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if 'Volume Name:' in line:
                        label = line.split('Volume Name:', 1)[1].strip()
                        return label if label != 'Not applicable (no file system)' else ''

        elif sys.platform.startswith('linux'):
            # Linux: use lsblk or findmnt
            # Try lsblk first (more reliable for labels)
            result = subprocess.run(
                ['lsblk', '-n', '-o', 'LABEL', path],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()

            # Fallback to findmnt
            result = subprocess.run(
                ['findmnt', '-n', '-o', 'LABEL', path],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()

        elif sys.platform == 'win32':
            # Windows: use wmic or PowerShell
            # Normalize drive letter
            if not path.endswith(':\\'):
                if path.endswith(':'):
                    path += '\\'
                else:
                    path = path.upper() + ':\\'

            # Try wmic first
            result = subprocess.run(
                ['wmic', 'volume', 'where', f'DriveLetter="{path[:-1]}"', 'get', 'Label'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.strip().splitlines()
                if len(lines) >= 2:
                    return lines[1].strip()

    except (subprocess.SubprocessError, OSError, FileNotFoundError):
        pass

    return ''

def _make_cache_key(label: str, size_bytes: int) -> str:
    """
    Create cache key from volume label and size.

    Uses both label and size to handle multiple cards with same label.
    Size is rounded to nearest GB to handle slight filesystem overhead differences.
    """
    size_gb = round(size_bytes / (1024**3), 1)
    return f"{label}:{size_gb}GB"

def _get_cached_vsn(path: str) -> Optional[int]:
    """
    Get cached VSN for a volume.

    Args:
        path: Mount point or drive letter

    Returns:
        Cached VSN as integer, or None if not cached
    """
    try:
        # Get volume info
        label = _get_volume_label(path)
        total, _, _ = shutil.disk_usage(path)
        cache_key = _make_cache_key(label, total)

        # Read cache
        cache_file = _get_vsn_cache_path()
        if not cache_file.exists():
            return None

        with open(cache_file) as f:
            cache: dict[str, str] = json.load(f)

        vsn_hex = cache.get(cache_key)
        if vsn_hex:
            return int(vsn_hex, 16)

    except (OSError, ValueError, json.JSONDecodeError):
        pass

    return None

def _cache_vsn(path: str, vsn: int) -> None:
    """
    Cache VSN for a volume.

    Args:
        path: Mount point or drive letter
        vsn: Volume serial number to cache
    """
    try:
        # Get volume info
        label = _get_volume_label(path)
        total, _, _ = shutil.disk_usage(path)
        cache_key = _make_cache_key(label, total)

        # Read existing cache
        cache_file = _get_vsn_cache_path()
        cache: dict[str, str] = {}
        if cache_file.exists():
            with open(cache_file) as f:
                cache = json.load(f)

        # Update cache
        cache[cache_key] = f"{vsn:08X}"

        # Write cache
        with open(cache_file, 'w') as f:
            json.dump(cache, f, indent=2)

    except (OSError, json.JSONDecodeError):
        # Silently fail - caching is optional
        pass

def _clear_vsn_cache() -> None:
    """Clear the VSN cache file"""
    try:
        cache_file = _get_vsn_cache_path()
        if cache_file.exists():
            cache_file.unlink()
    except OSError:
        pass

def _unix_vsn(device_path: str) -> int:
    """Extract volume serial number from FAT32 device and return as integer."""
    try:
        with open(device_path, 'rb') as fp:
            buffer = fp.read(SECTOR_SIZE)

            if len(buffer) != SECTOR_SIZE:
                raise ValueError(f"Short read from device: read {len(buffer)} bytes, expected {SECTOR_SIZE}. Device may not be a valid block device or may be corrupted.")

            # Validate FAT32 filesystem signature
            signature = buffer[FAT32_SIGNATURE_OFFSET:FAT32_SIGNATURE_OFFSET + len(FAT32_SIGNATURE)]
            if signature != FAT32_SIGNATURE:
                raise ValueError(f"Device {device_path} does not appear to be FAT32. Found signature: {signature!r}, expected: {FAT32_SIGNATURE!r}")

            # Extract 4 bytes at FAT32_VSN_OFFSET and convert to integer (little-endian order)
            vsn_bytes = buffer[FAT32_VSN_OFFSET:FAT32_VSN_OFFSET + 4]
            vsn = int.from_bytes(vsn_bytes, byteorder='little')

            # Validate VSN is in valid 32-bit unsigned range
            if not 0 <= vsn <= 0xFFFFFFFF:
                raise ValueError(f"Volume serial number out of range: {vsn:#x}")

            return vsn

    except PermissionError as e:
        raise OSError(f"Permission denied accessing {device_path}. Try running with sudo/administrator privileges.") from e
    except OSError as e:
        raise OSError(f"Error opening device {device_path}: {e}") from e

def _windows_vsn(drive_letter: str) -> int:
    """Extract volume serial number from Windows drive and return as integer."""
    import win32api  # pyright: ignore[reportMissingModuleSource]

    # Normalize drive letter format (ensure it ends with :\)
    if not drive_letter.endswith(':\\'):
        if drive_letter.endswith(':'):
            drive_letter += '\\'
        else:
            drive_letter = drive_letter.upper() + ':\\'

    try:
        # GetVolumeInformation returns (label, serial, max_filename_len, flags, filesystem)
        volume_info = win32api.GetVolumeInformation(drive_letter)
        vsn: int = volume_info[1]  # serial number is at index 1

        # Validate VSN is in valid 32-bit unsigned range
        if not 0 <= vsn <= 0xFFFFFFFF:
            raise ValueError(f"Volume serial number out of range: {vsn:#x}")

        return vsn
    except ImportError as e:
        raise ImportError("pywin32 package required for Windows volume serial number reading") from e
    except OSError as e:
        raise OSError(f"Error accessing drive {drive_letter}: {e}") from e

def _get_platform_device_example() -> str:
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

    candidates: list[dict[str, Union[float, str]]] = []

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
        except (OSError, PermissionError):
            # Skip partitions we can't access
            continue

    # Selection logic
    if len(candidates) == 0:
        print("Warning: No suitable SD card detected", file=sys.stderr)
        return ""
    elif len(candidates) == 1:
        path: str = str(candidates[0]['path'])
        return path
    else:
        # Multiple candidates - prefer smaller sizes (more likely to be SD cards vs external drives)
        candidates.sort(key=lambda x: x['size_gb'])
        path = str(candidates[0]['path'])
        print(f"Warning: Multiple SD card candidates found. Selecting smallest: {path}")
        return path

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
        return _windows_vsn(device)
    else:
        return _unix_vsn(device)

def get_vsn(vsn_arg: Optional[str], output_arg: Optional[str], verbose: bool = False) -> Optional[int]:
    """
    Get VSN from argument, environment, or cache with automatic fallback.

    Encapsulates the complete VSN resolution logic:
    1. Try explicit VSN argument
    2. Try cached VSN for output path (or auto-detected SD card)
    3. Print helpful error messages if not found

    Args:
        vsn_arg: Explicit VSN hex string (e.g., "A1B2C3D4"), or None
        output_arg: Mount point path to check cache, or None to auto-detect
        verbose: If True, print verbose status messages

    Returns:
        VSN as integer, or None if not found

    Example:
        >>> vsn = get_vsn(vsn_arg, output_arg, args.verbose)
        >>> if vsn:
        ...     print(f"Using VSN: {vsn:08X}")
    """
    vprint = print if verbose else lambda *_a, **_k: None

    if vsn_arg:
        # Explicit VSN provided
        try:
            return int(vsn_arg, 16)
        except ValueError:
            print(f"Error: Invalid volume serial number (must be hex): {vsn_arg}", file=sys.stderr)
            return None

    # Auto-detect SD card if no output path provided
    if not output_arg:
        output_arg = detect_sd_card()
        if output_arg:
            vprint(f"Auto-detected SD card: {output_arg}")

    if output_arg:
        # Try to read from cache using output path (mount point)
        vprint(f"Checking VSN cache for {output_arg}")
        card_serial = _get_cached_vsn(output_arg)
        if card_serial:
            vprint(f"Using cached VSN: {card_serial:08X}")
            return card_serial
        else:
            # Get device example for user instructions
            device_example = _get_platform_device_example()
            print(f"Warning: VSN not in cache for {output_arg}.", file=sys.stderr)
            print(f"To cache VSN, run: sudo python3 sdcard.py {device_example}", file=sys.stderr)
            print("Or specify VSN directly with: --vsn <hex_value>", file=sys.stderr)
            return None

    return None

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Read volume serial numbers from SD card block devices with caching support',
        epilog='Examples:\n'
               '  sudo %(prog)s /dev/rdisk2s1         # Read VSN and cache (requires sudo)\n'
               '  %(prog)s --cached /Volumes/GARMIN   # Check cached VSN (no sudo needed)\n'
               '  %(prog)s --label /Volumes/GARMIN    # Show volume label\n'
               '  %(prog)s --clear-cache              # Clear VSN cache',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('device', nargs='?', help='Block device path (e.g., /dev/rdisk2s1, /dev/sdb1, D:)')
    group.add_argument('--cached', metavar='MOUNT_POINT', help='Check cached VSN for mount point')
    group.add_argument('--label', metavar='MOUNT_POINT', help='Show volume label for mount point')
    group.add_argument('--clear-cache', action='store_true', help='Clear VSN cache')

    args = parser.parse_args()

    try:
        # Clear cache
        if args.clear_cache:
            _clear_vsn_cache()
            print("VSN cache cleared")
            return

        # Show label
        if args.label:
            label = _get_volume_label(args.label)
            if label:
                print(label)
            else:
                print("(no label)", file=sys.stderr)
            return

        # Check cache
        if args.cached:
            cached_vsn = _get_cached_vsn(args.cached)
            if cached_vsn is not None:
                print(f"{cached_vsn:08X}")
            else:
                print("Error: VSN not in cache. Read from device first to populate cache.", file=sys.stderr)
                sys.exit(1)
            return

        # Read VSN from device
        if args.device:
            result = read_vsn(args.device)
            print(f"{result:08X}")

            # Try to find mount point and cache the VSN
            mount_point = _get_mount_point(args.device)
            if mount_point:
                _cache_vsn(mount_point, result)
                print(f"Cached VSN for {mount_point}", file=sys.stderr)

    except (OSError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
