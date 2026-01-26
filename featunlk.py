#!/usr/bin/env python3
"""
Feature Unlock File Generator for Garmin Aviation Systems

Generates feature unlock files (feat_unlk.dat) that activate database features
on Garmin aviation systems. Unlock codes are tied to specific SD card volume
serial numbers and aircraft device serial numbers.

This tool creates device-specific unlock codes for navigation databases, terrain,
obstacles, and chart data. Each feature unlock entry is calculated using the
SD card volume serial number, device serial number, file CRC, and feature-specific
metadata.

Example usage:
    python3 featunlk.py -o /sdcard -f nav_data.bin -r "ldr_sys/avtn_db.bin" -N A1B2C3D4 -S 12345678
    python3 featunlk.py -c -o /sdcard -f terrain.bin -r "terrain.gca" -N A1B2C3D4 -S 12345678

This module is used by g3xdata.py to generate unlock codes for downloaded
aviation databases but can also be used standalone for manual unlock generation.

Upstream credit: https://github.com/dimaryaz/jdmtool/blob/main/src/jdmtool/featunlk.py

"""

import argparse
import datetime
import os
import pathlib
import struct
import zipfile
from enum import Enum
from io import BytesIO

""" Feature_Fields
0x000 |------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|
      | 0x01 | 0x00 |   SEC_ID    | 0x9A | 0x32 | 0x48 | 0x76 |       FEATURE BIT 1       |       FEATURE BIT 2       |
      |------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|

NAV DB:
0x010 |------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|
      |         VOLUME ID         | PREV |  REV |          FILE CRC         |                  DATE                   |
0x020 |------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|
      |                                       DATE                                 |          RESERVED                |
      |------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|

OTHER DB:
0x010 |------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|
      |         VOLUME ID         |          FILE CRC         |                   RESERVED                            |
0x020 |------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|
      |                                                    RESERVED                                                   |
      |------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|


0x030 |------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|
      | RES  |        CARD SERIAL        |                              RESERVED                                      |
0x040 |------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|
      |                                                    RESERVED                                                   |
0x050 |------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|
      |      |        CRC BLOCK 1        |  UNIT COUNT |   RESERVED  |         SYSTEM ID 1       |     SYSTEM ID 2    |
0x060 |------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|
      |  ..  |         SYSTEM ID 3       |        SYSTEM ID 4        |         SYSTEM ID 5       |     SYSTEM ID 6    |
      |------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|
        ...
0x370 |------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|
      |  ..  |         SYSTEM ID 199     |        SYSTEM ID 200      |          RESERVED         |      RESERVED      |
0x380 |------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|
      |  ..  |         RESERVED          |        RESERVED           |          CRC BLOCK 2      |      FULL CRC      |
0x390 |------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|------|
      |  ..  |
      |------|
"""

# Public API
__all__ = [
    'update_feature_unlock',
    'dump_feature_unlock',
]

_FEAT_UNLK = 'feat_unlk.dat'
_GARMIN_SECURITY_ID = 1727


def _encode_volume_id(vol_id: int) -> int:
    """
    Encodes volume ID for feature unlock structure.

    Args:
        vol_id: 32-bit volume serial number

    Returns:
        Encoded volume ID
    """
    return ~((vol_id << 31 & 0xFFFFFFFF) | (vol_id >> 1)) & 0xFFFFFFFF


def _decode_volume_id(encoded_vol_id: int) -> int:
    """
    Decodes volume ID from feature unlock structure.

    Args:
        encoded_vol_id: Encoded 32-bit volume serial number

    Returns:
        Decoded volume ID
    """
    return ~((encoded_vol_id << 1 & 0xFFFFFFFF) | (encoded_vol_id >> 31)) & 0xFFFFFFFF


def _truncate_system_id(system_id: int) -> int:
    """
    Truncates system ID to 32 bits with overflow handling.

    Args:
        system_id: 64-bit system serial number

    Returns:
        Truncated 32-bit system ID
    """
    return (system_id & 0xFFFFFFFF) + (system_id >> 32)


_CONTENT1_LEN = 0x55  # 85
_CONTENT2_LEN = 0x338  # 824

_SEC_ID_OFFSET = 191

_MAGIC1 = 0x1
_MAGIC2 = 0x7648329A  # Hard-coded in GrmNavdata.dll
_MAGIC3 = 0x6501

_NAVIGATION_PREVIEW_START = 129
_NAVIGATION_PREVIEW_END = 146

_CHUNK_SIZE = 0x8000

# Database content magic numbers
_DB_MAGIC = 0xA5DBACE1
_DB_MAGIC2 = 0x63614030

# Device type lookup - maps security ID to device model name
_DATABASE_TYPES = {
    0x0091: "GPSMAP 196",
    0x00BF: "Gx000",
    0x0104: "GPSMAP 296",
    0x0190: "G500",
    0x01F2: "G500H/GPSx75",
    0x0253: "GPSMAP 496",
    0x0294: "AERA 660",
    0x02E9: "GPSMAP 696",
    0x02EA: "G3X",
    0x02F0: "GPS175",
    0x0402: "GtnXi",
    0x0465: "GI275",
    0x0618: "AERA 760",
    0x06BF: "G3X Touch",
    0x0738: "GTR2X5",
    0x07DC: "GTXi",
}


class _Feature(Enum):
    NAVIGATION = 0, 0, ['ldr_sys/avtn_db.bin', 'avtn_db.bin', '.System/AVTN/avtn_db.bin']
    CONFIG_ENABLE = 913, 2, []  # type: ignore[var-annotated]
    TERRAIN = 1826, 3, ['terrain_9as.tdb', 'trn.dat', '.System/AVTN/terrain.tdb', 'terrain.tdb']
    OBSTACLE = 2739, 4, ['terrain.odb', '.System/AVTN/obstacle.odb', 'obstacle.odb']
    APT_TERRAIN = 3652, 5, ['terrain.adb']
    CHARTVIEW = 4565, 6, ['Charts/crcfiles.txt', 'crcfiles.txt']
    SAFETAXI = 5478, 7, ['safetaxi.bin', '.System/AVTN/safetaxi.img', 'safetaxi.img']
    FLITE_CHARTS = 6391, 8, ['fc_tpc/fc_tpc.dat', 'fc_tpc.dat', '.System/AVTN/FliteCharts/fc_tpc.dat']
    BASEMAP = 7304, 10, ['bmap.bin']
    AIRPORT_DIR = 8217, 10, ['apt_dir.gca', 'fbo.gpi']
    AIR_SPORT = 9130, 10, ['air_sport.gpi', 'Poi/air_sport.gpi']
    NAVIGATION_2 = 10043, 10, []  # type: ignore[var-annotated]
    SECTIONALS = 10956, 10, ['rasters/rasters.xml', 'rasters.xml']  # IFR_VFR_CHARTS
    OBSTACLE2 = 11869, 10, ['standard.odb']
    NAV_DB2 = 12782, 10, ['ldr_sys/nav_db2.bin', 'nav_db2.bin']
    NAV_DB2_STBY = 13695, 10, []  # type: ignore[var-annotated]
    SYSTEM_COPY = 14608, 11, []  # type: ignore[var-annotated]
    CONFIG_ENABLE_NO_SERNO = 15521, 2, []  # type: ignore[var-annotated]
    SAFETAXI2 = 16434, 10, ['safetaxi2.gca']
    BASEMAP2 = 17347, 10, ['bmap2.bin']

    # Unknown Features and Offsets
    # LVL_4_CONFIG = 0, 1, []
    # INSTALLER_UNLOCK = 0, 9, []

    def __init__(self, offset: int, bit: int, filenames: list[str]):
        self.offset = offset
        self.bit = bit
        self.filenames = filenames


_FILENAME_TO_FEATURE: dict[str, _Feature] = {
    filename: feature for feature in _Feature for filename in feature.filenames
}

_FEAT_UNLK_POLYNOMIAL_1 = 0x076DC419
_FEAT_UNLK_POLYNOMIAL_2 = 0x77073096


def _create_lookup_table(polynomial: int, length: int) -> list[int]:
    lookup_table: list[int] = []
    for index in range(length):
        value = index << 24
        for _ in range(8):
            if value & (1 << 31):
                value = ((value << 1) & 0xFFFFFFFF) ^ polynomial
            else:
                value <<= 1

        lookup_table.append(value)

    return lookup_table


__feat_unlk_lookup_table = [
    x ^ y
    for x in _create_lookup_table(_FEAT_UNLK_POLYNOMIAL_1, 64)
    for y in _create_lookup_table(_FEAT_UNLK_POLYNOMIAL_2, 4)
]


def _feat_unlk_checksum(data: bytes, value: int = 0xFFFFFFFF) -> int:
    """
    Computes Garmin feature unlock checksum.

    Args:
        data: Bytes to checksum
        value: Initial checksum value

    Returns:
        32-bit checksum value
    """
    for b in data:
        index = b ^ (value & 0xFF)
        value = __feat_unlk_lookup_table[index] ^ (value >> 8)
    return value


def update_feature_unlock(
    dest_dir: pathlib.Path,
    output_file_path: pathlib.Path,
    region_path: str,
    vol_id: int,
    system_id: int,
    check_crc: bool = False,
) -> None:
    # Validate paths
    if not dest_dir.exists():
        raise ValueError(f"Destination directory does not exist: {dest_dir}")
    if not dest_dir.is_dir():
        raise ValueError(f"Destination path is not a directory: {dest_dir}")
    if not output_file_path.exists():
        raise ValueError(f"Output file does not exist: {output_file_path}")
    if not output_file_path.is_file():
        raise ValueError(f"Output path is not a file: {output_file_path}")

    # Validate integer ranges
    if not (0 <= vol_id <= 0xFFFFFFFF):
        raise ValueError(f"Volume ID must be a 32-bit unsigned integer: {vol_id:#x}")
    if not (0 <= system_id <= 0xFFFFFFFFFFFFFFFF):
        raise ValueError(f"System ID must be a 64-bit unsigned integer: {system_id:#x}")

    # Look up feature from region filename
    feature = _FILENAME_TO_FEATURE.get(region_path)
    if feature is None:
        return

    preview = None
    with open(output_file_path, 'rb') as data:
        last_block = block = data.read(_CHUNK_SIZE)

        if feature == _Feature.NAVIGATION:
            preview = block[_NAVIGATION_PREVIEW_START:_NAVIGATION_PREVIEW_END]

        chk = 0xFFFFFFFF
        while block:
            last_block = block
            if check_crc:
                chk = _feat_unlk_checksum(block, chk)
            block = data.read(_CHUNK_SIZE)

    if check_crc and chk != 0:
        raise ValueError(f"{output_file_path} failed the checksum")

    checksum = int.from_bytes(last_block[-4:], 'little')

    # Build feat_unlk structure
    content1 = BytesIO()

    content1.write(_MAGIC1.to_bytes(2, 'little'))
    content1.write(((_GARMIN_SECURITY_ID - _SEC_ID_OFFSET + 0x10000) & 0xFFFF).to_bytes(2, 'little'))
    content1.write(_MAGIC2.to_bytes(4, 'little'))
    content1.write((1 << feature.bit).to_bytes(4, 'little'))
    content1.write((0).to_bytes(4, 'little'))
    content1.write(_encode_volume_id(vol_id).to_bytes(4, 'little'))

    if feature == _Feature.NAVIGATION:
        content1.write(_MAGIC3.to_bytes(2, 'little'))

    content1.write(checksum.to_bytes(4, 'little'))

    preview_len = _NAVIGATION_PREVIEW_END - _NAVIGATION_PREVIEW_START
    if feature == _Feature.NAVIGATION:
        if preview is None or len(preview) != preview_len:
            raise ValueError(
                f"Invalid preview data: expected {preview_len} bytes, got {len(preview) if preview else 0}"
            )
        content1.write(preview)
    else:
        content1.write(b'\x00' * preview_len)

    content1.write(b'\x00' * (_CONTENT1_LEN - len(content1.getbuffer()) - 4))

    chk1 = _feat_unlk_checksum(bytes(content1.getbuffer()))
    content1.write(chk1.to_bytes(4, 'little'))
    if len(content1.getbuffer()) != _CONTENT1_LEN:
        raise ValueError(f"Invalid content1 length: expected {_CONTENT1_LEN} bytes, got {len(content1.getbuffer())}")

    content2 = BytesIO()

    content2.write((0).to_bytes(4, 'little'))
    content2.write(_truncate_system_id(system_id).to_bytes(4, 'little'))
    content2.write(b'\x00' * (_CONTENT2_LEN - len(content2.getbuffer()) - 4))

    chk2 = _feat_unlk_checksum(bytes(content2.getbuffer()))
    content2.write(chk2.to_bytes(4, 'little'))
    if len(content2.getbuffer()) != _CONTENT2_LEN:
        raise ValueError(f"Invalid content2 length: expected {_CONTENT2_LEN} bytes, got {len(content2.getbuffer())}")

    chk3 = _feat_unlk_checksum(content1.getvalue() + content2.getvalue())

    feat_unlk = dest_dir / _FEAT_UNLK

    # Make writable before opening (if file exists)
    if feat_unlk.exists():
        feat_unlk.chmod(0o644)

    # Open the file in read+write mode - but make sure it exists first.
    # Why is there no mode that accomplishes both of these in one call?
    with open(feat_unlk, 'ab'):
        pass
    with open(feat_unlk, 'r+b') as out:
        out.seek(feature.offset)
        out.write(content1.getbuffer())
        out.write(content2.getbuffer())
        out.write(chk3.to_bytes(4, 'little'))

    # Make read-only to be consistent with JDM
    feat_unlk.chmod(0o444)


def _calculate_crc_and_preview_of_file(feature: _Feature, filename: pathlib.Path) -> tuple[int, bytes]:
    """
    Calculates the CRC and preview bytes for a feature data file.

    Args:
        feature: The feature type
        filename: Path to the data file

    Returns:
        Tuple of (crc, preview_bytes)
    """
    chk = 0xFFFFFFFF

    with open(filename, 'rb') as fd:
        block = fd.read(_CHUNK_SIZE)

        preview = block[_NAVIGATION_PREVIEW_START:_NAVIGATION_PREVIEW_END]
        while True:
            chk = _feat_unlk_checksum(block, chk)
            next_block = fd.read(_CHUNK_SIZE)
            if not next_block:
                break
            block = next_block

        if feature != _Feature.CHARTVIEW:
            if chk != 0:
                raise ValueError(f"{filename} failed the checksum")
            chk = int.from_bytes(block[-4:], 'little')

    return chk, preview


def _display_content_of_dat_file(feature: _Feature, dat_file: pathlib.Path) -> None:
    """Displays detailed content from a database file based on feature type."""
    format_date = "%d-%b-%Y"

    header_bytes = footer_bytes = footer2_bytes = b''

    if feature == _Feature.SAFETAXI2 and zipfile.is_zipfile(dat_file):
        with zipfile.ZipFile(dat_file, 'r') as zip_fp, zip_fp.open('safetaxi2.bin') as fd:
            header_bytes = fd.read(0x200)
            fd.seek(-0x102, os.SEEK_END)
            footer_bytes = fd.read(0x102)
    elif feature != _Feature.CHARTVIEW:
        with open(dat_file, 'rb') as fd:
            header_bytes = fd.read(0x200)
            fd.seek(-0x102, os.SEEK_END)
            footer_bytes = fd.read(0x102)
            fd.seek(-0x1F2, os.SEEK_END)
            footer2_bytes = fd.read(0x1F2)

    if feature in (_Feature.NAVIGATION, _Feature.NAV_DB2):
        (region, year, man, _) = [x.strip() for x in header_bytes[0x9F:0xEF].decode('ascii').split("\0")]
        print(f'** Region: {region}')
        print(f'** {year}')
        print(f'** {man}')

        print('** Revision: ' + chr(header_bytes[0x92]))
        (cycle, f_month, f_day, f_year, t_month, t_day, t_year) = struct.unpack(
            '<HBBHBBH', header_bytes[0x81 : 0x81 + 0xA]
        )
        print('** Cycle: ', cycle)
        cus_date1 = datetime.date(f_year, f_month, f_day).strftime(format_date).upper()
        cus_date2 = datetime.date(t_year, t_month, t_day).strftime(format_date).upper()
        print(f'** Effective {cus_date1} to {cus_date2}')
    elif feature in (_Feature.OBSTACLE,):
        if header_bytes[0x30 : 0x30 + 10] == b'Garmin Ltd':
            print('** ' + header_bytes[0x30 : 0x30 + 10].decode('ascii'))
            (f_day, f_month, f_year) = struct.unpack('<HHH', header_bytes[0x10 : 0x10 + 0x6])
            (t_day, t_month, t_year) = struct.unpack('<HHH', header_bytes[0x92 : 0x92 + 0x6])
            cus_date1 = datetime.date(f_year, f_month, f_day).strftime(format_date).upper()
            cus_date2 = datetime.date(t_year, t_month, t_day).strftime(format_date).upper()
            print(f'** Effective {cus_date1} to {cus_date2}')
        else:
            print('** Cycle: ' + footer_bytes[0x4 : 0x4 + 4].decode('ascii'))
            print('** ' + footer_bytes[0x20 : 0x20 + 11].decode('ascii'))
            print('** ' + footer_bytes[0x2B : 0x2B + 20].decode('ascii'))
            print('** ' + footer_bytes[0x98 : 0x98 + 20].decode('ascii'))
    elif feature in (_Feature.TERRAIN,):
        print(f"DB_MAGIC: 0x{int.from_bytes(header_bytes[0:4], 'little'):08X}")
        print('** ' + header_bytes[0x58 : 0x58 + 19].decode('ascii'))
        print('** Cycle: ' + footer2_bytes[0x1 : 0x1 + 4].decode('ascii'))
        print('** ' + header_bytes[0x78 : 0x78 + 12].decode('ascii'))
        print('** ' + header_bytes[0x86 : 0x86 + 4].decode('ascii'))
        print('** ' + header_bytes[0x8C : 0x8C + 4].decode('ascii'))
    elif feature in (_Feature.OBSTACLE2, _Feature.SAFETAXI2):
        if int.from_bytes(footer_bytes[0:4], 'little') != _DB_MAGIC:
            print('WRONG MAGIC!!')
            print(f"0x{int.from_bytes(footer_bytes[0:4], 'little'):08X}")
        print('** ' + footer_bytes[-0x6A:-0x61].decode('ascii'))
        print('** ' + footer_bytes[4:8].decode('ascii'))
        print('** ' + footer_bytes[28:43].decode('ascii'))
        print('** ' + footer_bytes[43 : 43 + 30].decode('ascii'))
        print('** ' + footer_bytes[152 : 152 + 20].decode('ascii'))
        (f_month, f_day, f_year) = struct.unpack('<BBH', footer_bytes[-0xFA : -0xFA + 0x4])
        (t_month, t_day, t_year) = struct.unpack('<BBH', footer_bytes[-0xF6 : -0xF6 + 0x4])
        cus_date1 = datetime.date(f_year, f_month, f_day).strftime(format_date).upper()
        cus_date2 = datetime.date(t_year, t_month, t_day).strftime(format_date).upper()
        print(f'** Effective {cus_date1} to {cus_date2}')
    elif feature in (_Feature.AIRPORT_DIR,):
        if int.from_bytes(footer_bytes[0:4], 'little') == _DB_MAGIC:
            print('** Cycle: ' + footer_bytes[0x4 : 0x4 + 4].decode('ascii'))
            (f_month, f_day, f_year, t_month, t_day, t_year) = struct.unpack('<BBHBBH', footer_bytes[0x8 : 0x8 + 8])
            cus_date1 = datetime.date(f_year, f_month, f_day).strftime(format_date).upper()
            cus_date2 = datetime.date(t_year, t_month, t_day).strftime(format_date).upper()
            print(f'** Effective {cus_date1} to {cus_date2}')
            print('** ' + footer_bytes[0x20 : 0x20 + 11].decode('ascii'))
            print('** ' + footer_bytes[0x2B : 0x2B + 20].decode('ascii'))
            print('** ' + footer_bytes[0x98 : 0x98 + 20].decode('ascii'))
        elif int.from_bytes(footer_bytes[0:4], 'little') == _DB_MAGIC2:
            print('** ' + header_bytes[0x54 : 0x54 + 40].decode('ascii'))
            cus_date1 = (
                datetime.date.fromordinal(int.from_bytes(header_bytes[0xCA : 0xCA + 4], 'little') - 3840609)
                .strftime(format_date)
                .upper()
            )
            cus_date2 = (
                datetime.date.fromordinal(int.from_bytes(header_bytes[0x94 : 0x94 + 4], 'little') - 3840611)
                .strftime(format_date)
                .upper()
            )
            print(f'** Effective {cus_date1} to {cus_date2}')
        else:
            print('!= DB_MAGIC and != DB_MAGIC2')
            print('WRONG MAGIC!!')
            print(f"0x{int.from_bytes(footer_bytes[0:4], 'little'):08X}")
    elif feature in (_Feature.FLITE_CHARTS,):
        print('** ' + header_bytes[0x18 : 0x18 + 12].decode('ascii'))
        print('** ' + header_bytes[0x24 : 0x24 + 20].decode('ascii'))
        print('** ' + header_bytes[0x95 : 0x95 + 20].decode('ascii'))
        (f_month, f_day, f_year) = struct.unpack('<BBH', header_bytes[0x6 : 0x6 + 0x4])
        (t_month, t_day, t_year) = struct.unpack('<BBH', header_bytes[0x0A : 0x0A + 0x4])
        cus_date1 = datetime.date(f_year, f_month, f_day).strftime(format_date).upper()
        cus_date2 = datetime.date(t_year, t_month, t_day).strftime(format_date).upper()
        print(f'** Effective {cus_date1} to {cus_date2}')
    elif feature in (_Feature.CHARTVIEW,):
        with open(dat_file.parent / 'chartview.hif', 'rb') as fd:
            header_bytes = fd.read(0x200)
        print('** ' + header_bytes[0x0A : 0x0A + 9].decode('ascii'))
        print('** Cycle: ' + header_bytes[0x23 : 0x23 + 7].decode('ascii'))
        with open(dat_file.parent / 'charts.ini', 'rb') as fd:
            header_bytes = fd.read(0x200)
        cus_date1 = (
            datetime.date.fromordinal(int(header_bytes[30 : 30 + 7].decode('ascii')) - 1721424)
            .strftime(format_date)
            .upper()
        )
        cus_date2 = (
            datetime.date.fromordinal(int(header_bytes[59 : 59 + 7].decode('ascii')) - 1721424)
            .strftime(format_date)
            .upper()
        )
        print(f'** Effective {cus_date1} to {cus_date2}')
    elif feature in (_Feature.SAFETAXI, _Feature.BASEMAP, _Feature.BASEMAP2):
        xor_byte = header_bytes[0x00]
        if xor_byte:
            print(f'** XOR BYTE: {xor_byte:02x}')

        if header_bytes[16:22] != b'DSKIMG':
            raise ValueError('No DSKIMG file')

        if header_bytes[0x41:0x47] != b'GARMIN':
            print(header_bytes[0x41:0x46])
            raise ValueError('File is not by GARMIN')

        map_version = str(header_bytes[0x08]) + '.' + str(header_bytes[0x09])
        print(f'** MAP Version: {map_version}')

        update_month = int(header_bytes[0x0A])
        update_year = int(header_bytes[0x0B]) + 1900
        print(f'** Update: {update_month}/{update_year}')

        name = header_bytes[0x49 : 0x49 + 20].decode('ascii')
        print(f'** {name}')
        cycle = header_bytes[0x59 : 0x59 + 4].decode('ascii')
        print(f'** Cycle: {cycle}')
        description = header_bytes[0x65:0x83].decode('ascii')
        if description.strip():
            print(f'** {description}')
        c_year = int.from_bytes(header_bytes[0x39 : 0x39 + 2], 'little')
        c_month = int(header_bytes[0x3B])
        c_day = int(header_bytes[0x3C])
        cus_date1 = datetime.date(c_year, c_month, c_day).strftime(format_date).upper()
        print(f'** Creation Date: {cus_date1}')

        if int.from_bytes(header_bytes[0x83:0x85], 'little') == 0xDEAD:
            version = str(header_bytes[0x85]) + '.' + str(header_bytes[0x86])
            release = int.from_bytes(header_bytes[0x87:0x89], 'little')
            print(f'** Creation Software Version: {version} ({release})')
        if feature in (_Feature.SAFETAXI,):
            cus_date1 = (
                datetime.date.fromordinal(int(int.from_bytes(header_bytes[0x20 : 0x20 + 2], 'little') / 135) + 739221)
                .strftime(format_date)
                .upper()
            )
            cus_date2 = (
                datetime.date.fromordinal(int(int.from_bytes(header_bytes[0x22 : 0x22 + 2], 'little') / 135) + 739221)
                .strftime(format_date)
                .upper()
            )
            print(f'** Effective {cus_date1} to {cus_date2}')
    elif feature in (_Feature.SECTIONALS,):
        print('** Cycle: ' + header_bytes[101 : 101 + 4].decode('ascii'))
        cus_date1 = (
            datetime.datetime.strptime(header_bytes[171 : 171 + 10].decode('ascii'), "%m/%d/%Y")
            .date()
            .strftime(format_date)
            .upper()
        )
        print(f'** Effective_date: {cus_date1}')
        print('** ' + header_bytes[216 : 216 + 21].decode('ascii'))
    elif feature in (_Feature.AIR_SPORT,):
        print('** header_bytes')
        print('** ' + header_bytes[0x18:0x2A].decode('ascii'))
        print('** ' + header_bytes[0x5A:0x76].decode('ascii'))
        print('** ' + header_bytes[0x7B:0x89].decode('ascii'))
        cus_date1 = (
            datetime.date.fromordinal(int.from_bytes(header_bytes[0x8C : 0x8C + 4], 'little') + 490625)
            .strftime(format_date)
            .upper()
        )
        cus_date2 = (
            datetime.date.fromordinal(int.from_bytes(header_bytes[0x90 : 0x90 + 4], 'little') + 491001)
            .strftime(format_date)
            .upper()
        )
        print(f'** Effective {cus_date1} to {cus_date2}')
    else:  # Feature.APT_TERRAIN
        print('** UNKNOWN DATA TYPE')
        print(header_bytes)


def _display_content_of_feat_unlk(
    featunlk: pathlib.Path, feature: _Feature, show_missing: bool = False, check_crc: bool = False
) -> None:
    """Displays the content of a single feature from a feat_unlk.dat file."""
    print(f"\n---- {feature.name} ----")

    with open(featunlk, 'rb') as fd:
        fd.seek(feature.offset)

        content1_bytes = fd.read(_CONTENT1_LEN)
        if all(b == 0 for b in content1_bytes):
            print("* No content")
            return
        chk1 = _feat_unlk_checksum(content1_bytes)
        if chk1 != 0:
            raise ValueError("Content1 failed the checksum")

        content2_bytes = fd.read(_CONTENT2_LEN)
        chk2 = _feat_unlk_checksum(content2_bytes)
        if chk2 != 0:
            raise ValueError("Content2 failed the checksum")

        overall_chk = fd.read(4)
        chk3 = _feat_unlk_checksum(content2_bytes + overall_chk, 0)
        if chk3 != 0:
            raise ValueError(f"Content failed the checksum: {chk3:08x}")

    content1 = BytesIO(content1_bytes[:-4])

    magic = int.from_bytes(content1.read(2), 'little')
    if magic != _MAGIC1:
        raise ValueError(f"Unexpected magic number: 0x{magic:04X}")

    security_id = (int.from_bytes(content1.read(2), 'little') + _SEC_ID_OFFSET) & 0xFFFF
    device_model_val = _DATABASE_TYPES.get(security_id, "Unknown")
    print(f"* garmin_sec_id: {security_id}, device_model: ({device_model_val})")

    magic = int.from_bytes(content1.read(4), 'little')
    if magic != _MAGIC2:
        raise ValueError(f"Unexpected magic number: 0x{magic:08X}")

    file_feature_bit = int.from_bytes(content1.read(4), 'little')
    if file_feature_bit != 1 << feature.bit:
        raise ValueError(f"Incorrect bit: file: {file_feature_bit:04x}, expected: {1 << feature.bit:04x}")

    if not all(b == 0 for b in content1.read(4)):
        raise ValueError("Expected zeros")

    vol_id = _decode_volume_id(int.from_bytes(content1.read(4), 'little'))
    print(f"* Volume ID: {vol_id:08X}")

    if feature == _Feature.NAVIGATION:
        magic = int.from_bytes(content1.read(2), 'little')
        if magic != _MAGIC3:
            raise ValueError(f"Unexpected magic number: 0x{magic:04X}")

    expected_chk = int.from_bytes(content1.read(4), 'little')
    expected_preview = content1.read(17)

    if feature != _Feature.NAVIGATION:
        if not all(b == 0 for b in expected_preview):
            raise ValueError("Expected zeros in the content")

        # read 2 Bytes to be at same offset as Feature.NAVIGATION
        byte = content1.tell()
        if not all(b == 0 for b in content1.read(2)):
            if show_missing:
                print("- Expected zeros in the content but got: ", [hex(x) for x in content1_bytes[byte : byte + 2]])
            else:
                print("- Expected zeros in the content")

    if check_crc:
        for filename in feature.filenames:
            dat_file = featunlk.parent.joinpath(filename)
            if dat_file.is_file():
                crc, preview = _calculate_crc_and_preview_of_file(feature, dat_file)

                # wrong file
                if crc != expected_chk:
                    print(f'- {filename} exists, but has wrong CRC')
                    continue

                print(f'* {filename} has correct CRC')

                if feature == _Feature.NAVIGATION and expected_preview != preview:
                    raise ValueError("Preview data mismatch")

                _display_content_of_dat_file(feature, dat_file)
                break
        else:
            print('- Unknown Filename or CRC not found in files')
            print('* Expected Chk: ', hex(expected_chk))

    # OFFSET 0x2B
    byte = content1.tell()
    if not all(b == 0 for b in content1.read(8)):
        if show_missing:
            print("- Expected zeros in the content but got: ", [hex(x) for x in content1_bytes[byte : byte + 8]])
        else:
            print("- Expected zeros in the content")

    # OFFSET 0x33
    card_id = int.from_bytes(content1.read(4), 'little')
    if card_id != 0:
        print(f'* Card ID: 0x{card_id:08x}')

    byte = content1.tell()
    if not all(b == 0 for b in content1.read()):
        if show_missing:
            print("- Expected zeros in the content but got: ", [hex(x) for x in content1_bytes[byte:-4]])
        else:
            print("- Expected zeros in the content")

    # start CONTENT2
    content2 = BytesIO(content2_bytes[:-4])
    unit_count = int.from_bytes(content2.read(2), 'little')

    byte = content2.tell()
    if not all(b == 0 for b in content2.read(2)):
        if show_missing:
            print("- Expected zeros in the content2 but got: ", [hex(x) for x in content2_bytes[byte : byte + 2]])
        else:
            print("- Expected zeros in the content2")

    system_id = int.from_bytes(content2.read(4), 'little')

    if unit_count != 0:
        print(f'* Still allowed onto {unit_count} systems')
    else:
        print(f"* Truncated avionics_id: {system_id:08X}")
        possible_system_ids = [system_id - i | i << 32 for i in range(1, 4)]
        print(f"  (Possible values: {', '.join(f'{v:X}' for v in possible_system_ids)}, ...)")

    byte = content2.tell()
    if not all(b == 0 for b in content2.read()):
        if show_missing:
            print("- Expected zeros in the content2 but got: ", [hex(x) for x in content2_bytes[byte:-4]])
        else:
            print("- Expected zeros in the content2")


def dump_feature_unlock(
    featunlk: pathlib.Path, feature_name: str = "", show_missing: bool = False, check_crc: bool = False
) -> int:
    """
    Dumps the contents of a feat_unlk.dat file.

    Args:
        featunlk: Path to the feat_unlk.dat file
        feature_name: Optional feature name or filename to display (None for all)
        show_missing: Show detailed info about unexpected non-zero bytes
        check_crc: Verify CRC of associated data files (slow)

    Returns:
        0 on success, 1 on error
    """
    if not featunlk.exists():
        print(f"File not found: {featunlk}")
        return 1

    if not feature_name:
        for feature in _Feature:
            _display_content_of_feat_unlk(featunlk, feature, show_missing, check_crc)
        return 0
    else:
        # Try as feature name first
        try:
            feature = _Feature[feature_name]
        except KeyError:
            # Try as filename
            feature_lookup = _FILENAME_TO_FEATURE.get(feature_name)

            if feature_lookup is None:
                print(f"Unsupported feature: {feature_name}")
                print()
                print("Supported feature names and file paths:")
                for f in _Feature:
                    print(f"  {f.name}: {', '.join(f.filenames)}")
                return 1

            feature = feature_lookup

        _display_content_of_feat_unlk(featunlk, feature, show_missing, check_crc)
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Feature unlock file tool for Garmin aviation systems",
        epilog="""
Examples:
  Dump all features:    %(prog)s /sdcard/feat_unlk.dat
  Dump one feature:     %(prog)s /sdcard/feat_unlk.dat --feature NAVIGATION
  Update feat_unlk:     %(prog)s nav_data.bin -u -o /sdcard -r "ldr_sys/avtn_db.bin" -N A1B2C3D4 -S 12345678
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # File path (required for both modes, different meaning)
    parser.add_argument("file_path", type=pathlib.Path, metavar="FILE", help="Path to feat_unlk.dat file")

    # Mode selection
    parser.add_argument("-u", "--update", action="store_true", help="Update feat_unlk.dat (default is dump )")

    # Dump-specific arguments
    parser.add_argument("-f", "--feature", dest="feature_name", help="Feature name or filename to display")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show detailed info about unexpected bytes found in featunlk.dat"
    )

    # Update-specific arguments
    parser.add_argument("-o", "--output", dest="dest_dir", type=pathlib.Path, help="Destination directory")
    parser.add_argument("-r", "--region", dest="region_path", help="TAW region name")
    parser.add_argument(
        "-N", "--vsn", dest="vol_id", type=lambda x: int(x, 16), help="SD card volume serial number in hex"
    )
    parser.add_argument(
        "-S", "--system-serial", dest="system_id", type=lambda x: int(x, 16), help="System serial number in hex"
    )
    parser.add_argument("-c", "--check-crc", action="store_true", help="Verify CRC of data files (slow)")

    args = parser.parse_args()

    if args.update:
        # Update mode - validate required arguments
        if not args.dest_dir:
            parser.error("--output is required for update mode")
        if not args.region_path:
            parser.error("--region is required for update mode")
        if args.vol_id is None:
            parser.error("--vsn is required for update mode")
        if args.system_id is None:
            parser.error("--system-serial is required for update mode")

        update_feature_unlock(
            args.dest_dir, args.file_path, args.region_path, args.vol_id, args.system_id, args.check_crc
        )
    else:
        # Dump mode (default)
        result = dump_feature_unlock(args.file_path, args.feature_name or "", args.verbose, args.check_crc)
        raise SystemExit(result)


if __name__ == "__main__":
    """ This is executed when run from the command line """
    main()
