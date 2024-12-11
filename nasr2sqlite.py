 #!/usr/bin/env python3

"""
This script downloads NASR (National Airspace System Resource) data from the FAA website.
Then it extracts the data from the downloaded zip file and creates a SQLite database.

Command Line Arguments:
    --current: Downloads the Current data.
    --preview: Downloads the Preview data.
    --name: Downloads archived data by name.
    --list: Lists the available NASR data in the Archive section.
    --filename: Specifies the NASR data filename. Uses basename of URL if not provided.
    --db: Specifies the output database filename. Uses 'nasr.db' if not provided.

Usage:
    python nasr2sqlite.py --current [--filename <filename>] [--db <filename>]
    python nasr2sqlite.py --preview [--filename <filename>] [--db <filename>]
    python nasr2sqlite.py --list
        (then)
    python nasr2sqlite.py --name <name> [--filename <filename>] [--db <filename>]

        (to skip downloading)
    python nasr2sqlite.py --filename <filename> [--db <filename>]

Raises:
    FileNotFoundError: If no data is found for the specified criteria.
    urllib.error.HTTPError: If there is an HTTP error during the download process.
"""

import argparse
import collections
import csv
import io
import sqlite3
import os
import nasr

def main():
    """
    Main function to download NASR data from www.faa.gov and populate a SQLite database.
    """

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Download NASR data from www.faa.gov and populate a SQLite database.')
    parser.add_argument('--current', action='store_true', help='Download the Current data.')
    parser.add_argument('--preview', action='store_true', help='Download the Preview data.')
    parser.add_argument('--name', help='Download archived data by name.')
    parser.add_argument('--list', action='store_true', help='List of NASR data in the Archive section.')
    parser.add_argument('--filename', help='Specify the NASR data filename. Uses basename of URL if not provided.')
    parser.add_argument('--db', default='nasr.db', help='Specify the output database filename.')
    parser.add_argument('--build-geometry', action='store_true', help='Build geometry columns for positions.')
    parser.add_argument('--build-spatial-index', action='store_true', help='Build spatial indices for geometry columns.')
    args = parser.parse_args()

    # Process the archive section
    if args.list:
        # List available NASR data if --list is passed, then exit
        print('\n'.join(nasr.list_archives().keys()))
        return

    if args.name:
        # Look up fullzip link by name
        fullzip_link = nasr.list_archives().get(args.name)

        # Download the file
        filename = nasr.download(fullzip_link, args.filename)

    elif args.preview or args.current:
        # Process the Preview or Current section
        fullzip_link = list(nasr.current_or_preview('Preview' if args.preview else 'Current').values())[0]

        # Download the file
        filename = nasr.download(fullzip_link, args.filename)

    elif args.filename:
        filename = args.filename

    else:
        raise FileNotFoundError('nasr: No data found or specified.')

    # Delete old database if it already exists
    if os.path.exists(args.db):
        os.remove(args.db)

    # Create a connection to the SQLite database
    conn = sqlite3.connect(args.db)
    c = conn.cursor()

    # Open archive
    with nasr.CsvZip(filename) as csv_archive:
        # Create a dictionary to hold the table structures
        table_structures = collections.defaultdict(list)

        # Find all .csv files in the archive
        csv_files = [name for name in csv_archive.namelist() if name.endswith('.csv')]

        # Read the structure files in order to create the tables
        for csv_filename in [name for name in csv_files if name.endswith('_CSV_DATA_STRUCTURE.csv')]:
            # Open the structure file
            with csv_archive.open(csv_filename) as csv_file:
                csv_reader = csv.DictReader(io.TextIOWrapper(csv_file, encoding='us-ascii', errors='strict'))

                # Populate the table structures dictionary
                for row in csv_reader:
                    csv_table_name = row['CSV File']
                    column_name = row['Column Name']
                    max_length = row['Max Length']
                    data_type = row['Data Type']
                    nullable = row['Nullable']

                    # Determine the SQLite data type
                    if data_type == 'VARCHAR':
                        sqlite_type = f'VARCHAR({max_length})'
                    elif data_type == 'NUMBER':
                        # SQLite does not have NUMERIC(p,s) so we have to determine if it is an INTEGER or REAL
                        if ',0)' in max_length:
                            sqlite_type = 'INTEGER'
                        else:
                            sqlite_type = 'REAL'
                    else:
                        raise ValueError(f"Unknown data type: {data_type}")

                    # Determine if the column is nullable
                    not_null = ' NOT NULL' if nullable == 'N' else ''

                    # Append the column definition to the table structure
                    table_structures[csv_table_name].append(f'{column_name} {sqlite_type}{not_null}')

        # Add the data to the tables
        for csv_filename in [name for name in csv_files if not name.endswith('_CSV_DATA_STRUCTURE.csv')]:
            # Determine the table name
            csv_table_name = os.path.splitext(csv_filename)[0]
            column_definition = table_structures[csv_table_name]

            # Create the table
            c.execute(f'CREATE TABLE IF NOT EXISTS {csv_table_name} ({", ".join(column_definition)})')

            # File encoding is usually iso-8859-1
            file_encodings = { 'CDR': 'utf-8' }
            file_encoding = file_encodings.get(csv_table_name, 'iso-8859-1')

            # Open the data file
            with csv_archive.open(csv_filename) as csv_file:
                csv_reader = csv.DictReader(io.TextIOWrapper(csv_file, encoding=file_encoding, errors='strict'))
                for row in csv_reader:
                    # Insert the data
                    c.execute(f'INSERT INTO {csv_table_name} VALUES ({', '.join(['?'] * len(row))})', tuple(row.values()))

    # Run nasr_initialize.sql to add some helpful columns not included in the NASR data
    with open('nasr_initialize.sql', encoding='us-ascii') as f:
        c.executescript(f.read())

    conn.commit()

    if args.build_geometry:
        try:
            # Load spatialite extension
            conn.enable_load_extension(True)
            conn.load_extension('mod_spatialite')
        except sqlite3.OperationalError as e:
            # Exit early on failure. The rest of the script just adds geometry columns.
            print('Error loading mod_spatialite:', e, 'Spatialite support will not be available.')
            conn.close()
            exit(0)

        # Create the spatialite metadata
        c.execute('SELECT InitSpatialMetadata(1)')

        # Add geometry columns for tables that have point geometries
        def add_geometry_column(table, geom_column, geometry_type):
            c.execute(f'SELECT AddGeometryColumn("{table}", "{geom_column}", 4269, "{geometry_type}", "XY")')
            if args.build_spatial_index:
                c.execute(f'SELECT CreateSpatialIndex("{table}", "{geom_column}")')

        def add_point_geometry(table, geom_column, latitude_column, longitude_column):
            c.execute(f'UPDATE {table} SET {geom_column} = MakePoint({longitude_column}, {latitude_column}, 4269)')

        tables = [
            ['APT_BASE',    'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['APT_RWY_END', 'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['APT_RWY_END', 'GEOMETRY_DISPLACED_THR', 'LAT_DISPLACED_THR_DECIMAL', 'LONG_DISPLACED_THR_DECIMAL'],
            ['APT_RWY_END', 'GEOMETRY_LAHSO',         'LAT_LAHSO_DECIMAL',         'LONG_LAHSO_DECIMAL'],
            ['ARB_BASE',    'GEOMETRY_REFERENCE',     'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['ARB_SEG',     'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['AWOS',        'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['AWY_SEG_ALT', 'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['COM',         'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['DP_RTE',      'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['FIX_BASE',    'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['FRQ',         'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['FSS_BASE',    'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['ILS_BASE',    'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['ILS_DME',     'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['ILS_GS',      'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['ILS_MKR',     'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['MAA_BASE',    'GEOMETRY_REFERENCE',     'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['MAA_SHP',     'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['MTR_PT',      'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['NAV_BASE',    'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['NAV_BASE',    'GEOMETRY_TACAN_DME',     'TACAN_DME_LAT_DECIMAL',     'TACAN_DME_LONG_DECIMAL'],
            ['PJA_BASE',    'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['STAR_RTE',    'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL'],
            ['WXL_BASE',    'GEOMETRY',               'LAT_DECIMAL',               'LONG_DECIMAL']
        ]

        for table, geom_column, lat_column, long_column in tables:
            add_geometry_column(table, geom_column, 'POINT')
            add_point_geometry(table, geom_column, lat_column, long_column)
            conn.commit()

        # Add multipoint geometries for AWY, DP, MTR, STAR
        def add_multipoint_geometry(table, geom_column, point_table, point_geom_column, identifying_columns):
            where_clause = ' AND '.join([f'{table}.{col} = {point_table}.{col}' for col in identifying_columns])
            c.execute(f'UPDATE {table} SET {geom_column} = (SELECT CastToMultipoint(Collect({point_geom_column})) FROM {point_table} WHERE {where_clause})')

        tables = [
            ['AWY_LINES', 'GEOMETRY', 'AWY_SEG_ALT', 'GEOMETRY', ['AWY_LOCATION', 'AWY_ID', 'LINE_SEQ']],
            ['DP_LINES',  'GEOMETRY', 'DP_RTE',      'GEOMETRY', ['DP_COMPUTER_CODE', 'ROUTE_NAME', 'BODY_SEQ']],
            ['MTR_LINES', 'GEOMETRY', 'MTR_PT',      'GEOMETRY', ['ROUTE_TYPE_CODE', 'ROUTE_ID']],
            ['STAR_LINES','GEOMETRY', 'STAR_RTE',    'GEOMETRY', ['STAR_COMPUTER_CODE', 'ROUTE_NAME', 'BODY_SEQ']]
        ]

        for table, geom_column, point_table, point_geom_column, identifying_columns in tables:
            add_geometry_column(table, geom_column, 'MULTIPOINT')
            add_multipoint_geometry(table, geom_column, point_table, point_geom_column, identifying_columns)
            conn.commit()

        # TODO: Add multipoint geometries for PFRs. These are complicated in that they can be comprised of:
        # NAVAID, FIX, DP, STAR, AIRWAY, a RADIAL from a NAVAID, or a FRD (FIX RADIAL DISTANCE)

        # TODO: Add multipoint geometries for CDRs. These are poorly represented in the data, and require
        # more parsing logic.

        # Add polygon geometries for: MAA_SHP
        def add_polygon_geometry(table, geom_column, point_table, point_geom_column, identifying_columns):
            where_clause = ' AND '.join([f'{table}.{col} = {point_table}.{col}' for col in identifying_columns])
            c.execute(f'UPDATE {table} SET {geom_column} = (SELECT MakePolygon({point_geom_column}) FROM {point_table} WHERE {where_clause})')

        add_geometry_column('MAA_BASE', 'GEOMETRY', 'POLYGON')
        add_polygon_geometry('MAA_BASE', 'GEOMETRY', 'MAA_SHP', 'GEOMETRY', ['MAA_ID'])
        conn.commit()

        # TODO: Add polygon geometries for ARB_SEG. These are complicated, too.
        #    Some of the ARTCC boundaries defined by the ARTCC facility are composed of
        #    more than a single closed shape. Due to the format constraints and naming
        #    conventions of the legacy ARB file it is not possible to publish each
        #    shape separately. In these cases it is necessary to read the point
        #    description text for the key phrase "TO POINT OF BEGINNING" to identify
        #    where the shape returns to the beginning and forms a closed shape.

if __name__ == '__main__':
    main()
