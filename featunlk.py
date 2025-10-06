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
import pathlib
from typing import List
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

FEAT_UNLK = 'feat_unlk.dat'
GARMIN_SECURITY_ID = 1727

def encode_volume_id(vol_id: int) -> int:
    return ~((vol_id << 31 & 0xFFFFFFFF) | (vol_id >> 1)) & 0xFFFFFFFF


def truncate_system_id(system_id: int) -> int:
    return (system_id & 0xFFFFFFFF) + (system_id >> 32)

CONTENT1_LEN = 0x55   # 85
CONTENT2_LEN = 0x338  # 824

SEC_ID_OFFSET = 191

MAGIC1 = 0x1
MAGIC2 = 0x7648329A  # Hard-coded in GrmNavdata.dll
MAGIC3 = 0x6501

NAVIGATION_PREVIEW_START = 129
NAVIGATION_PREVIEW_END = 146

CHUNK_SIZE = 0x8000

class Feature(Enum):
    NAVIGATION = 0, 0, ['ldr_sys/avtn_db.bin', 'avtn_db.bin', '.System/AVTN/avtn_db.bin']
    CONFIG_ENABLE = 913, 2, []
    TERRAIN = 1826, 3, ['terrain_9as.tdb', 'trn.dat', '.System/AVTN/terrain.tdb', 'terrain.tdb']
    OBSTACLE = 2739, 4, ['terrain.odb', '.System/AVTN/obstacle.odb', 'obstacle.odb']
    APT_TERRAIN = 3652, 5, ['terrain.adb']
    CHARTVIEW = 4565, 6, ['Charts/crcfiles.txt', 'crcfiles.txt']
    SAFETAXI = 5478, 7, ['safetaxi.bin', '.System/AVTN/safetaxi.img', 'safetaxi.img']
    FLITE_CHARTS = 6391, 8, ['fc_tpc/fc_tpc.dat', 'fc_tpc.dat', '.System/AVTN/FliteCharts/fc_tpc.dat']
    BASEMAP = 7304, 10, ['bmap.bin']
    AIRPORT_DIR = 8217, 10, ['apt_dir.gca', 'fbo.gpi']
    AIR_SPORT = 9130, 10, ['air_sport.gpi', 'Poi/air_sport.gpi']
    NAVIGATION_2 = 10043, 10, []
    SECTIONALS = 10956, 10, ['rasters/rasters.xml', 'rasters.xml']  # IFR_VFR_CHARTS
    OBSTACLE2 = 11869, 10, ['standard.odb']
    NAV_DB2 = 12782, 10, ['ldr_sys/nav_db2.bin', 'nav_db2.bin']
    NAV_DB2_STBY = 13695, 10, []
    SYSTEM_COPY = 14608, 11, []
    CONFIG_ENABLE_NO_SERNO = 15521, 2, []
    SAFETAXI2 = 16434, 10, ['safetaxi2.gca']
    BASEMAP2 = 17347, 10, ['bmap2.bin']

    # Unknown Features and Offsets
    # LVL_4_CONFIG = 0, 1, []
    # INSTALLER_UNLOCK = 0, 9, []

    def __init__(self, offset: int, bit: int, filenames: list[str]):
        self.offset = offset
        self.bit = bit
        self.filenames = filenames

FILENAME_TO_FEATURE: dict[str, Feature] = {
    filename: feature
    for feature in Feature
    for filename in feature.filenames
}

FEAT_UNLK_POLYNOMIAL_1 = 0x076dc419
FEAT_UNLK_POLYNOMIAL_2 = 0x77073096

def _create_lookup_table(polynomial: int, length: int) -> List[int]:
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

_feat_unlk_lookup_table = [
    x ^ y
    for x in _create_lookup_table(FEAT_UNLK_POLYNOMIAL_1, 64)
    for y in _create_lookup_table(FEAT_UNLK_POLYNOMIAL_2, 4)
]

def feat_unlk_checksum(data: bytes, value: int = 0xFFFFFFFF) -> int:
    for b in data:
        index = b ^ (value & 0xFF)
        value = _feat_unlk_lookup_table[index] ^ (value >> 8)
    return value

def update_feature_unlock(dest_dir: pathlib.Path, output_file_path: pathlib.Path, region_path: str, vol_id: int, security_id: int, system_id: int, check: bool=False) -> None:
    # Look up feature from region filename
    feature = FILENAME_TO_FEATURE.get(region_path)
    if feature is None:
        return

    preview = None
    with open(output_file_path, 'rb') as data:
        last_block = block = data.read(CHUNK_SIZE)

        if feature == Feature.NAVIGATION:
            preview = block[NAVIGATION_PREVIEW_START:NAVIGATION_PREVIEW_END]

        chk = 0xFFFFFFFF
        while block:
            last_block = block
            if check:
                chk = feat_unlk_checksum(block, chk)
            block = data.read(CHUNK_SIZE)

    if check and chk != 0:
        raise ValueError(f"{output_file_path} failed the checksum")

    checksum = int.from_bytes(last_block[-4:], 'little')

    # Build feat_unlk structure
    content1 = BytesIO()

    content1.write(MAGIC1.to_bytes(2, 'little'))
    content1.write(((security_id - SEC_ID_OFFSET + 0x10000) & 0XFFFF).to_bytes(2, 'little'))
    content1.write(MAGIC2.to_bytes(4, 'little'))
    content1.write((1 << feature.bit).to_bytes(4, 'little'))
    content1.write((0).to_bytes(4, 'little'))
    content1.write(encode_volume_id(vol_id).to_bytes(4, 'little'))

    if feature == Feature.NAVIGATION:
        content1.write(MAGIC3.to_bytes(2, 'little'))

    content1.write(checksum.to_bytes(4, 'little'))

    preview_len = NAVIGATION_PREVIEW_END - NAVIGATION_PREVIEW_START
    if feature == Feature.NAVIGATION:
        assert preview is not None and len(preview) == preview_len, preview
        content1.write(preview)
    else:
        content1.write(b'\x00' * preview_len)

    content1.write(b'\x00' * (CONTENT1_LEN - len(content1.getbuffer()) - 4))

    chk1 = feat_unlk_checksum(bytes(content1.getbuffer()))
    content1.write(chk1.to_bytes(4, 'little'))
    assert len(content1.getbuffer()) == CONTENT1_LEN, len(content1.getbuffer())

    content2 = BytesIO()

    content2.write((0).to_bytes(4, 'little'))
    content2.write(truncate_system_id(system_id).to_bytes(4, 'little'))
    content2.write(b'\x00' * (CONTENT2_LEN - len(content2.getbuffer()) - 4))

    chk2 = feat_unlk_checksum(bytes(content2.getbuffer()))
    content2.write(chk2.to_bytes(4, 'little'))
    assert len(content2.getbuffer()) == CONTENT2_LEN, len(content2.getbuffer())

    chk3 = feat_unlk_checksum(content1.getvalue() + content2.getvalue())

    feat_unlk = dest_dir / FEAT_UNLK

    # JDM makes the file read-only, so make it writable again (if it exists)
    try:
        feat_unlk.chmod(0o644)
    except OSError:
        pass

    # Open the file in read+write mode - but make sure it exists first.
    # Why is there no mode that accomplishes both of these in one call?
    with open(feat_unlk, 'ab'):
        pass
    with open(feat_unlk, 'r+b') as out:
        out.seek(feature.offset)
        out.write(content1.getbuffer())
        out.write(content2.getbuffer())
        out.write(chk3.to_bytes(4, 'little'))

    # Make it read-only just to be consistent with JDM.
    try:
        feat_unlk.chmod(0o444)
    except OSError:
        pass

def main() -> None:
    parser = argparse.ArgumentParser(description="Update feat_unlk.dat to enable a feature")
    parser.add_argument("-o", "--output", dest="dest_dir", type=pathlib.Path, required=True, help="Destination directory")
    parser.add_argument("-f", "--file", dest="data_file_path", type=pathlib.Path, required=True, help="Data file path")
    parser.add_argument("-r", "--region", dest="region_path", required=True, help="TAW region name")
    parser.add_argument("-N", "--vsn", dest="vol_id", type=int, required=True, help="SD card volume serial number")
    parser.add_argument("-S", "--system-serial", dest="system_id", type=int, required=True, help="System serial number")
    parser.add_argument("-c", "--check-crc", action="store_true", help="Perform CRC check during processing (slow)")

    args = parser.parse_args()

    update_feature_unlock(
        args.dest_dir,
        args.data_file_path,
        args.region_path,
        args.vol_id,
        GARMIN_SECURITY_ID,
        args.system_id,
        args.check_crc
    )

if __name__ == "__main__":
    """ This is executed when run from the command line """
    main()