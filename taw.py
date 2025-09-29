#!/usr/bin/env python3
"""
TAW Archive Extractor for Garmin Navigation Databases

Extracts and analyzes Garmin TAW (navigation database) archive files used by
G3X and other Garmin aviation systems. TAW files contain navigation
data including airport directory, obstacles, terrain, and chart information.

This tool can both analyze TAW file contents and extract files to directory
structures suitable for SD card deployment to Garmin G3X systems.

Example usage:
    python3 taw.py archive.taw /output/path     # Extract archive
    python3 taw.py -i archive.taw               # Show contents only

This module is used by g3xdata.py to extract navigation database files
for SD card creation but can also be used standalone for TAW analysis.

Upstream credit: https://github.com/dimaryaz/jdmtool/blob/main/src/jdmtool/taw.py

"""

import argparse
import pathlib

TAW_SEPARATOR = b'\x00\x02\x00\x00\x00Dd\x00\x1b\x00\x00\x00A\xc8\x00'
TAW_MAGIC = b'KpGrd'

TAW_DATABASE_TYPES = {
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

TAW_REGION_PATHS = {
    0x01: "ldr_sys/avtn_db.bin",
    0x02: "ldr_sys/nav_db2.bin",
    0x03: "bmap.bin",
    0x04: "nav.bin",  # fake filename: used for GNS430/500 data cards
    0x05: "bmap2.bin",
    0x0A: "safetaxi.bin",
    0x0B: "safetaxi2.gca",
    0x14: "fc_tpc/fc_tpc.dat",
    0x1A: "rasters/rasters.xml",
    0x21: "terrain.tdb",
    0x22: "terrain_9as.tdb",
    0x23: "trn.dat",
    0x24: "fc_tpc/fc_tpc.dat",
    0x25: "fc_tpc/fc_tpc.fca",
    0x26: "standard.odb",
    0x27: "terrain.odb",
    0x28: "terrain.adb",
    0x32: ".System/AVTN/avtn_db.bin",
    0x33: "Poi/air_sport.gpi",
    0x35: ".System/AVTN/Obstacle.odb",
    0x36: ".System/AVTN/safetaxi.img",
    0x39: ".System/AVTN/FliteCharts/fc_tpc.dat",
    0x3A: ".System/AVTN/FliteCharts/fc_tpc.fca",
    0x4C: "fbo.gpi",
    0x4E: "apt_dir.gca",
    0x4F: "air_sport.gpi",
}

def extract_taw(input_path: pathlib.Path, dest_path: pathlib.Path, info_only: bool = False, skip_unknown_regions: bool = False, verbose: bool = False):
    debug = print if verbose else lambda *_: None

    with open(input_path, 'rb') as fd:

        # Read header

        magic = fd.read(5)
        if magic not in (b'pWa.d', b'wAt.d'):
            raise ValueError(f"Unexpected bytes: {magic}")

        sep = fd.read(len(TAW_SEPARATOR))
        if sep != TAW_SEPARATOR:
            raise ValueError(f"Unexpected separator bytes: {sep}")

        sqa1 = [s.decode() for s in fd.read(25).split(b'\x00')]

        metadata_len = int.from_bytes(fd.read(4), 'little')

        section_type = fd.read(1)
        if section_type != b'F':
            raise ValueError(f"Unexpected section type: {section_type}")

        metadata = fd.read(metadata_len)

        fd.read(4)  # Remaining

        section_type = fd.read(1)
        if section_type != b'R':
            raise ValueError(f"Unexpected section type: {section_type}")

        magic = fd.read(len(TAW_MAGIC))
        if magic != TAW_MAGIC:
            raise ValueError(f"Got unexpected magic bytes: {magic}")

        sep = fd.read(len(TAW_SEPARATOR))
        if sep != TAW_SEPARATOR:
            raise ValueError(f"Unexpected separator bytes: {sep}")

        sqa2 = [s.decode() for s in fd.read(25).split(b'\x00')]

        debug(f"SQA1: {sqa1}")
        debug(f"SQA2: {sqa2}")

        # Parse metadata

        try:
            database_type = int.from_bytes(metadata[:2], 'little')

            if metadata[2] == 0x00:
                year = metadata[8]
                cycle = metadata[12]
                text = metadata[16:]
            else:
                year = metadata[4]
                cycle = metadata[6]
                text = metadata[8:]

            parts = text.split(b'\x00')
            if len(parts) != 3:
                raise ValueError(f"Unexpected metadata: {metadata}")

            avionics=parts[0].decode()
            coverage=parts[1].decode()
            type=parts[2].decode()

            if info_only:
                debug()
                database_type_name = TAW_DATABASE_TYPES.get(database_type, "Unknown")
                print(f"Database type: {database_type:x} ({database_type_name})")
                print(f"Year: {year}")
                print(f"Cycle: {cycle}")
                print(f"Avionics: {avionics!r}")
                print(f"Coverage: {coverage!r}")
                print(f"Type: {type.upper()!r}")
                print()
        except ValueError as ex:
            print(ex)

        # Read sections

        while True:
            sect_start = fd.tell()
            sect_size = int.from_bytes(fd.read(4), 'little')

            section_type = fd.read(1)
            if section_type == b'S':
                break
            if section_type != b'R':
                raise ValueError(f"Unexpected section type: {section_type}")

            region = int.from_bytes(fd.read(2), 'little')
            unknown = int.from_bytes(fd.read(4), 'little')
            data_size = int.from_bytes(fd.read(4), 'little')
            data_start = fd.tell()

            debug(f"Section start: {sect_start:x}")
            debug(f"Section size: {sect_size:x}")

            region_path = TAW_REGION_PATHS.get(region)
            debug(f"Region: {region:02x} ({region_path or 'unknown'})")
            debug(f"Unknown: {unknown}")
            debug(f"Database start: {data_start}")
            debug(f"Database size: {data_size}")

            if region_path:
                output_file = pathlib.PurePosixPath(region_path)
            elif skip_unknown_regions:
                output_file = None
            else:
                output_file = f"region_{region:02x}.bin"

            if output_file:
                if info_only:
                    debug()
                    print(f"{data_size:>10} {output_file}")
                else:
                    assert fd.tell() == data_start
                    block_size = 0x1000
                    output_path = dest_path / output_file
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, 'wb') as fd_out:
                        for offset in range(0, data_size, block_size):
                            block = fd.read(min(data_size - offset, block_size))
                            fd_out.write(block)

                    yield (region_path, output_path)

            debug()

            # Seek to next section
            fd.seek(data_start + data_size)

        # Unknown extra bytes at the end
        tail = fd.read()
        debug(f"Tail: {tail}")

def main() -> None:
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Test Garmin API functions')
    parser.add_argument('input_file', nargs='?', help='Input .taw file')
    parser.add_argument('-o', '--output-path', default='.', help='Base output path')
    parser.add_argument('-i', '--info-only', action='store_true', help='Only output descriptive information, do not extract')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose debug output')
    args = parser.parse_args()

    list(extract_taw(args.input_file, args.output_path, info_only=args.info_only, verbose=args.verbose))

if __name__ == "__main__":
    main()