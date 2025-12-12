#!/usr/bin/env python3

"""
This module provides functions to interact with the FAA NASR Subscription page
and processes NASR data into msgpack or sqlite databases for flight planning.

CSV files processed:
    - APT_BASE.csv: Contains airport waypoint data.
    - FIX_BASE.csv: Contains fix waypoint data.
    - NAV_BASE.csv: Contains navigation waypoint data.
    - AWY_BASE.csv: Contains airway data.
    - AWY_SEG_ALT.csv: Contains airway segment data.

Command Line Arguments:
    --current: Downloads the Current data.
    --preview: Downloads the Preview data.
    --name: Downloads archived data by name.
    --list: Lists the available NASR data in the Archive section.
    --filename: Specifies the NASR data filename. Uses basename of URL if not provided.
    --msgpack [FILE]: Output msgpack format (default: platform-specific cached file).
    --sqlite FILE: Output sqlite format (filename required).
    --with-geometry: Include spatialite geometry (only valid with --sqlite).

Usage:
    python nasr.py --current
    python nasr.py --current --msgpack custom.msgpack
    python nasr.py --current --sqlite nasr.db
    python nasr.py --current --sqlite nasr.db --with-geometry
    python nasr.py --current --msgpack --sqlite nasr.db --with-geometry
    python nasr.py --list
        (then)
    python nasr.py --name <name>

        (to skip downloading)
    python nasr.py --filename <filename> --sqlite nasr.db

Functions:
    list_archives() -> dict:
        Extracts and returns a dictionary of archive links from the NASR page.

    current_or_preview(which: str) -> dict:
        Extracts the NASR zip link from the specified section ('Preview' or 'Current').

    download(url: str, filename: str = None) -> str:
        Downloads a file from the given URL to the cache directory.
"""

import argparse
import collections
import csv
import io
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from typing import Any, Optional, Union

try:
    import bs4
except ImportError:
    print("Error: beautifulsoup4 is required. Install with: pip install 'g3xtools[nasr]'", file=sys.stderr)
    sys.exit(1)

try:
    import msgpack
except ImportError:
    print("Error: msgpack is required. Install with: pip install 'g3xtools[nasr]'", file=sys.stderr)
    sys.exit(1)

import cache

# Public API
__all__ = [
    'load_nasr_database',
]

_NASR_URL = 'https://www.faa.gov/air_traffic/flight_info/aeronav/aero_data/NASR_Subscription/'
_DEFAULT_FILENAME = 'downloaded_file'
_CACHE_PATH = cache.user_cache_path("g3xtools", "g3xtools")
_NASR_MSGPACK_DATABASE_PATH = _CACHE_PATH / 'nasr.msgpack'

def load_nasr_database() -> dict[str, Any]:
    """
    Load the NASR database from cache.

    Returns:
        Dictionary with keys 'waypoints', 'airways', and 'connections'

    Raises:
        FileNotFoundError: If the database file doesn't exist
        RuntimeError: If the database cannot be loaded

    Example:
        >>> database = load_nasr_database()
        >>> waypoints = database['waypoints']
        >>> airways = database['airways']
        >>> connections = database['connections']
    """
    if not _NASR_MSGPACK_DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"NASR database not found at {_NASR_MSGPACK_DATABASE_PATH}\n"
            f"Run 'python3 nasr.py --current' to download and build the database"
        )

    try:
        with open(_NASR_MSGPACK_DATABASE_PATH, 'rb') as f:
            database: dict[str, Any] = msgpack.unpackb(f.read(), strict_map_key=False)
        return database
    except Exception as e:
        raise RuntimeError(f"Failed to load NASR database: {e}") from e

def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """Sanitize a filename to prevent path traversal and other security issues."""
    if not filename:
        raise ValueError("Filename cannot be empty")

    # Extract just the filename part, handling URLs properly
    if '/' in filename:
        filename = filename.split('/')[-1]
    if '\\' in filename:
        filename = filename.split('\\')[-1]

    # Remove or replace dangerous characters
    # Keep only alphanumeric, dots, dashes, underscores
    filename = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)

    # Remove leading/trailing dots and spaces
    filename = filename.strip('. ')

    # Prevent empty filename
    if not filename or filename in ('.', '..'):
        filename = _DEFAULT_FILENAME

    # Ensure filename has reasonable length
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        filename = name[:max_length - len(ext)] + ext if ext else filename[:max_length]

    return filename

def _article() -> bs4.element.Tag:
    # Get the main NASR page and find the article element
    url = _NASR_URL
    with urllib.request.urlopen(url) as response:
        html = response.read().decode('utf-8')
    soup = bs4.BeautifulSoup(html, 'html.parser')
    article = soup.find('article', id='content')
    if article is None:
        raise ValueError("NASR page article content not found")
    return article

def list_archives() -> dict[str, str]:
    """
    Extracts and returns a dictionary of archive links from a web page.
    The function searches for an 'Archives' section in the HTML content of an article,
    extracts the subscription effective date and corresponding link, and stores them
    in a dictionary.

    Returns:
        dict: A dictionary where the keys are subscription effective dates (as strings)
              and the values are the corresponding URLs (as strings).
    """

    # Initialize a dictionary to store the structured data
    dataurl = {}

    # Extract the fullzip link from the Archives section
    article = _article()
    archives_h2 = article.find('h2', string='Archives')  # type: ignore
    if archives_h2 is None:
        raise ValueError("Archives section not found")
    archives_section = archives_h2.find_next('ul')
    if archives_section is None:
        raise ValueError("Archives list not found")

    for li in archives_section.find_all('li'):
        text = li.contents[0].strip()
        # Remove prefix if present
        if text.startswith('Subscription effective '):
            text = text[len('Subscription effective '):]
        # Remove suffix if present
        if text.endswith(' -'):
            text = text[:-len(' -')]
        link = li.find('a')
        if link:
            dataurl[text] = link['href']

    return dataurl

def current_or_preview(which: str) -> dict[str, str]:
    """
    Extracts the nasr zip link from the selected section.

    Args:
        which (str): The section to extract the link from. Can be 'Preview' or 'Current'.

    Returns:
        dict: A dictionary where the key is the subscription effective date (string)
              and the value is the corresponding URLs (string).
    """

    # Extract the fullzip link from the selected section
    article = _article()
    section_h2 = article.find('h2', string=which)  # type: ignore
    if section_h2 is None:
        raise ValueError(f"{which} section not found")
    section_ul = section_h2.find_next('ul')
    if section_ul is None:
        raise ValueError(f"{which} list not found")

    effective_date = None
    fullzip_link = None

    for li in section_ul.find_all('li'):
        link = li.find('a')
        if link is None:
            continue
        effective_date = link.text
        if effective_date.startswith('Subscription effective '):
            effective_date = effective_date[len('Subscription effective '):]

        # Follow the link to get the fullzip and aptzip URLs
        subpage_url = urllib.parse.urljoin(_NASR_URL, link['href'])
        subpage_response = urllib.request.urlopen(subpage_url)
        subpage_html = subpage_response.read().decode('utf-8')
        subpage_soup = bs4.BeautifulSoup(subpage_html, 'html.parser')
        subpage_article = subpage_soup.find('article', id='content')
        if subpage_article is None:
            continue
        download_link = subpage_article.find('a', string='Download')  # type: ignore
        if download_link:
            fullzip_link = download_link['href']

    if effective_date is None or fullzip_link is None:
        raise ValueError(f"Could not find download link in {which} section")

    return {effective_date: fullzip_link}

def download(url: str, filename: Optional[str] = None) -> str:
    """
    Downloads a file from the given URL and saves it to the specified filename.
    If the filename is not provided, the file will be saved with the basename of the URL.
    If the file already exists, the function will add an 'If-Modified-Since' header to the request
    to avoid downloading the file again if it has not been modified.

    Args:
        url (str): The URL of the file to download.
        filename (str, optional): The name of the file to save. Defaults to None.

    Returns:
        str: The filename of the downloaded file.

    Raises:
        urllib.error.HTTPError: If an HTTP error occurs other than a 304 Not Modified response.
    """

    # Create a request to retrieve the file
    request = urllib.request.Request(url)

    # Set filename with proper sanitization
    if filename:
        filename = sanitize_filename(filename)
    else:
        url_basename = os.path.basename(url)
        filename = sanitize_filename(url_basename) if url_basename else _DEFAULT_FILENAME

    # Ensure we're writing to cache directory
    filename = os.path.basename(filename)  # Extra safety measure
    filepath = _CACHE_PATH / filename

    # Check if the file already exists on the filesystem and add the If-Modified-Since header to the request
    if filepath.exists():
        last_modified_time = filepath.stat().st_mtime
        last_modified_time_str = time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(last_modified_time))
        request.add_header('If-Modified-Since', last_modified_time_str)

    # Download the file
    try:
        with urllib.request.urlopen(request) as response:
            if response.status == 200:
                with open(filepath, 'wb') as f:
                    f.write(response.read())

    except urllib.error.HTTPError as e:
        # Check if the server returned a 304 Not Modified response, if so, just skip the download
        if e.code != 304:
            raise

    return str(filepath)

class CsvZip:
    """
    A context manager class to handle the nested CSV ZIP file contained in the main ZIP archive.

    Attributes:
        filename (str): The path to the outer ZIP file.
        archive (zipfile.ZipFile): The outer ZIP file object.
        csv_archive (zipfile.ZipFile): The inner ZIP file object containing CSV data.

    Methods:
        __enter__(): Opens the outer ZIP file and the inner CSV ZIP file.
        __exit__(exc_type, exc_value, traceback): Closes the inner and outer ZIP files.
        namelist(): Returns a list of file names in the inner CSV ZIP file.
        open(name): Opens a file in the inner CSV ZIP file.
    """

    def __init__(self, filename):
        """
        Initializes the NASR object with the given filename.

        Args:
            filename (str): The name of the file to be processed.

        Attributes:
            filename (str): The name of the file to be processed.
            archive (None): Placeholder for the archive data.
            csv_archive (None): Placeholder for the CSV archive data.
        """
        self.filename = filename
        self.archive = None
        self.csv_archive = None

    def __enter__(self):
        """
        Enter the runtime context related to this object.
        This method is called when the execution flow enters the context of the
        `with` statement. It opens the main archive file specified by `self.filename`
        and then finds and opens the CSV data file within the archive.

        Returns:
            self: The instance of the class.
        """
        self.archive = zipfile.ZipFile(self.filename)

        # Find the CSV data file the archive
        csv_data_name = next(name for name in self.archive.namelist() if name.startswith('CSV_Data/') and name.endswith('.zip'))

        # Open the single file inside the CSV_Data folder as a new ZipFile
        self.csv_archive = zipfile.ZipFile(self.archive.open(csv_data_name))
        return self

    def __exit__(self, exc_type, exc_value, traceback):  # type: ignore
        """
        Exit the runtime context related to this object.
        This method is called when the 'with' statement is used. It closes the
        csv_archive and archive resources.
        """
        if self.csv_archive is not None:
            self.csv_archive.close()
        if self.archive is not None:
            self.archive.close()

    def namelist(self):
        """
        Retrieve the list of filenames from the CSV archive.
        Returns:
            list: A list of names contained in the CSV archive.
        """
        if self.csv_archive is None:
            raise RuntimeError("CSV archive not opened")
        return self.csv_archive.namelist()

    def open(self, name):
        """
        Open a file from the CSV archive.

        Parameters:
            name (str): The name of the file to open.

        Returns:
            file object: The opened file object from the CSV archive.
        """
        if self.csv_archive is None:
            raise RuntimeError("CSV archive not opened")
        return self.csv_archive.open(name)

def read_csv_file(csv_archive: 'CsvZip', file_name: str, columns: list[str], rowdata: Union[list[list[str]], list[dict[str, Any]]]) -> None:
    """
    Reads a CSV file from a given archive and extracts specified columns into a list.

    Args:
        csv_archive (zipfile.ZipFile): The archive containing the CSV file.
        file_name (str): The name of the CSV file within the archive.
        columns (list of str): The list of column headers to extract from the CSV file.
        rowdata (list of list): The list to append the extracted row data to.

    Returns:
        None: This function modifies the rowdata list in place.

    Notes:
        - The function strips whitespace from all column values.
        - If the column header is 'LAT_DECIMAL' or 'LONG_DECIMAL', the value is converted to a float.
    """

    with csv_archive.open(file_name) as csv_file:
        csv_reader = csv.DictReader(io.TextIOWrapper(csv_file, encoding='iso-8859-1', errors='strict'))
        for row in csv_reader:
            values: list[Union[float, str]] = [
                # Handling CSV rows: Strip whitespace and convert to float if necessary
                float(row[csv_header]) if csv_header in ['LAT_DECIMAL', 'LONG_DECIMAL'] else
                row[csv_header].strip()
                    for csv_header in columns]
            rowdata.append(values)  # type: ignore[arg-type]

def write_msgpack_file(csvzip_path: pathlib.Path, msgpack_path: pathlib.Path):
    waypoints: list[list[str]] = []
    airways: list[list[str]] = []
    airway_seg: list[dict[str, Any]] = []

    # Open archive
    with CsvZip(csvzip_path) as csv_archive:
        # Read waypoint data
        read_csv_file(csv_archive, 'APT_BASE.csv', ['ARPT_ID', 'SITE_TYPE_CODE', 'LAT_DECIMAL', 'LONG_DECIMAL', 'COUNTRY_CODE', 'ICAO_ID'], waypoints)
        read_csv_file(csv_archive, 'FIX_BASE.csv', ['FIX_ID', 'FIX_USE_CODE', 'LAT_DECIMAL', 'LONG_DECIMAL', 'COUNTRY_CODE'], waypoints)
        read_csv_file(csv_archive, 'NAV_BASE.csv', ['NAV_ID', 'NAV_TYPE', 'LAT_DECIMAL', 'LONG_DECIMAL', 'COUNTRY_CODE'], waypoints)

        # Read airway data
        read_csv_file(csv_archive, 'AWY_BASE.csv', ['AWY_ID', 'AWY_LOCATION', 'AWY_DESIGNATION'], airways)
        read_csv_file(csv_archive, 'AWY_SEG_ALT.csv', ['AWY_ID', 'AWY_LOCATION', 'FROM_POINT', 'FROM_PT_TYPE', 'TO_POINT', 'COUNTRY_CODE', 'AWY_SEG_GAP_FLAG'], airway_seg)

    # Build a temporary reverse lookup dictionary of waypoint_id to [list of waypoint index]
    # Unfortunately waypoint_id are not unique
    waypoint_lookup = collections.defaultdict(list)
    for i, waypoint in enumerate(waypoints):
        waypoint_lookup[waypoint[0]].append(i)

    # Build a temporary dictionary of (airway_id, airway_location) to airway_index
    # Also, airway_id are not unique, but (airway_id, airway_location) are
    airway_lookup = {(row[0], row[1]): i for i, row in enumerate(airways)}

    # Build a temporary list of airway_index, [list of waypoint index]
    # An airway_index can be associated with multiple lists of waypoints if the airway has gaps
    airway_lists = []
    current_waypoint_index_list = []
    for airway_id, airway_location, from_point, from_point_type, to_point, country_code, gap in airway_seg:
        # Look up airway index
        airway_index = airway_lookup[airway_id, airway_location]

        # Look up the waypoint indices from our temporary reverse lookup dictionary
        waypoint_indices = waypoint_lookup.get(from_point, [])

        # Find the waypoint index that matches the type and country code
        matching_waypoint_indices = [i for i in waypoint_indices if waypoints[i][1] == from_point_type and waypoints[i][4] == country_code]

        # Error if multiple waypoints found, this should not happen
        if len(matching_waypoint_indices) > 1:
            raise ValueError(f'Multiple waypoints found for {from_point} with type {from_point_type} and country {country_code}. Indices: {waypoint_indices}')

        if matching_waypoint_indices:
            # Add the waypoint index to the current waypoint index list
            current_waypoint_index_list.append(matching_waypoint_indices[0])

        # If there is a gap, or if we are at the end of the airway, start a new list
        if gap == 'Y' or not to_point:
            airway_lists.append((airway_index, current_waypoint_index_list))
            current_waypoint_index_list = []

    # Go through each list pairwise and build a dictionary of airway connections: waypoint_index to (neighbor waypoint_index, airway_index)
    connections = collections.defaultdict(list)
    for airway_index, waypoint_indices in airway_lists:
        for i1, i2 in zip(waypoint_indices, waypoint_indices[1:]):
            connections[i1].append((i2, airway_index))
            connections[i2].append((i1, airway_index))

    # Serialize all data into a single database file
    database = {
        'waypoints': waypoints,
        'airways': airways,
        'connections': connections
    }
    packed_data: Optional[bytes] = msgpack.packb(database)
    if packed_data:
        with open(msgpack_path, 'wb') as f:
            f.write(packed_data)

def validate_sql_identifier(identifier):
    """Validate that an identifier is safe for SQL use."""
    if not identifier:
        raise ValueError("Identifier cannot be empty")

    # Allow only alphanumeric characters and underscores, starting with letter or underscore
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier}")

    # Prevent SQL reserved words (add more as needed)
    reserved_words = {'SELECT', 'INSERT', 'DELETE', 'UPDATE', 'DROP', 'CREATE', 'TABLE', 'FROM', 'WHERE'}
    if identifier.upper() in reserved_words:
        raise ValueError(f"Reserved word not allowed as identifier: {identifier}")

    return identifier

def write_sqlite_file(csvzip_path: pathlib.Path, db_path: pathlib.Path, spatialite: bool):
    import sqlite3

    # Delete old database if it already exists
    if db_path.exists():
        db_path.unlink()

    # Create a connection to the SQLite database
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Open archive
    with CsvZip(csvzip_path) as csv_archive:
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
                        sqlite_type = 'INTEGER' if ',0)' in max_length else 'REAL'
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

            # Validate table name for SQL injection prevention
            safe_table_name = validate_sql_identifier(csv_table_name)

            # Create the table
            c.execute(f'CREATE TABLE IF NOT EXISTS {safe_table_name} ({", ".join(column_definition)})')

            # File encoding is usually iso-8859-1
            file_encodings = { 'CDR': 'utf-8' }
            file_encoding = file_encodings.get(csv_table_name, 'iso-8859-1')

            # Open the data file
            with csv_archive.open(csv_filename) as csv_file:
                csv_reader = csv.DictReader(io.TextIOWrapper(csv_file, encoding=file_encoding, errors='strict'))
                for row in csv_reader:
                    # Insert the data
                    placeholders = ', '.join(['?'] * len(row))
                    c.execute(f'INSERT INTO {safe_table_name} VALUES ({placeholders})', tuple(row.values()))

    # Run post-processing SQL to add helpful columns not included in the NASR data
    sql_path = pathlib.Path(__file__).parent / 'post_process_nasr.sql'
    with open(sql_path, encoding='us-ascii') as f:
        c.executescript(f.read())

    conn.commit()

    if spatialite:
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

        multipoint_tables: list[tuple[str, str, str, str, list[str]]] = [
            ('AWY_LINES', 'GEOMETRY', 'AWY_SEG_ALT', 'GEOMETRY', ['AWY_LOCATION', 'AWY_ID', 'LINE_SEQ']),
            ('DP_LINES',  'GEOMETRY', 'DP_RTE',      'GEOMETRY', ['DP_COMPUTER_CODE', 'ROUTE_NAME', 'BODY_SEQ']),
            ('MTR_LINES', 'GEOMETRY', 'MTR_PT',      'GEOMETRY', ['ROUTE_TYPE_CODE', 'ROUTE_ID']),
            ('STAR_LINES','GEOMETRY', 'STAR_RTE',    'GEOMETRY', ['STAR_COMPUTER_CODE', 'ROUTE_NAME', 'BODY_SEQ'])
        ]

        for table, geom_column, point_table, point_geom_column, identifying_columns in multipoint_tables:
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

def main():
    """
    Main function to download NASR data and store it in data structures useful for flight planning.
    """

    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Download NASR data and store it in data structures useful for flight planning.')
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument('--current', action='store_true', help='Download the Current data.')
    mode_group.add_argument('--preview', action='store_true', help='Download the Preview data.')
    mode_group.add_argument('--name', help='Download archived data by name.')
    mode_group.add_argument('--list', action='store_true', help='List of NASR data in the Archive section.')
    parser.add_argument('--filename', help='Specify the NASR data filename. Uses basename of URL if not provided.')

    # Output format arguments
    parser.add_argument('--msgpack', nargs='?', const=_NASR_MSGPACK_DATABASE_PATH, metavar='FILE',
                        help=f'Output msgpack format (default: {_NASR_MSGPACK_DATABASE_PATH})')
    parser.add_argument('--sqlite', metavar='FILE',
                        help='Output sqlite format (filename required)')
    parser.add_argument('--with-geometry', action='store_true',
                        help='Include spatialite geometry (only valid with --sqlite)')

    args = parser.parse_args()

    # Validation
    if args.with_geometry and not args.sqlite:
        parser.error('--with-geometry requires --sqlite')

    # Process the archive section
    if args.list:
        # List available NASR data if --list is passed, then exit
        print('\n'.join(list_archives().keys()))
        return

    elif args.name:
        # Look up fullzip link by name
        fullzip_link = list_archives().get(args.name)
        if not fullzip_link:
            raise ValueError(f"Archive '{args.name}' not found")

        # Download the file
        filename = download(fullzip_link, args.filename)

    elif args.preview or args.current:
        # Process the Preview or Current section
        fullzip_link = list(current_or_preview('Preview' if args.preview else 'Current').values())[0]

        # Download the file
        filename = download(fullzip_link, args.filename)

    elif args.filename:
        filename = args.filename

    else:
        raise FileNotFoundError('nasr: No data found or specified.')

    # Default behavior: if no output format specified, use msgpack
    if not args.msgpack and not args.sqlite:
        args.msgpack = _NASR_MSGPACK_DATABASE_PATH

    # Process output formats
    csvzip_path = pathlib.Path(filename)

    if args.msgpack:
        msgpack_path = pathlib.Path(args.msgpack) if isinstance(args.msgpack, str) else args.msgpack
        write_msgpack_file(csvzip_path, msgpack_path)

    if args.sqlite:
        sqlite_path = pathlib.Path(args.sqlite)
        write_sqlite_file(csvzip_path, sqlite_path, args.with_geometry)

if __name__ == '__main__':
    main()
