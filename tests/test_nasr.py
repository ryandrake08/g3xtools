"""
Tests for nasr.py - NASR database functions.

Tests cover filename sanitization and database loading.
Web scraping and CSV processing functions are better suited for integration tests.
"""

import sys
from pathlib import Path

import msgpack
import pytest

# Import the nasr module
sys.path.insert(0, str(Path(__file__).parent.parent))
import nasr


def test_sanitize_filename_simple():
    """Sanitize simple valid filename."""
    result = nasr.sanitize_filename("test.txt")
    assert result == "test.txt"


def test_sanitize_filename_with_spaces():
    """Replace spaces with underscores."""
    result = nasr.sanitize_filename("my file.txt")
    assert result == "my_file.txt"


def test_sanitize_filename_special_chars():
    """Remove special characters."""
    result = nasr.sanitize_filename("file@#$%name!.txt")
    assert result == "file____name_.txt"


def test_sanitize_filename_path_traversal():
    """Prevent path traversal attacks."""
    result = nasr.sanitize_filename("../../etc/passwd")
    assert ".." not in result
    assert "/" not in result
    # Extracts just the filename part
    assert result == "passwd"


def test_sanitize_filename_from_url():
    """Extract filename from URL path."""
    result = nasr.sanitize_filename("https://example.com/path/to/file.zip")
    assert result == "file.zip"


def test_sanitize_filename_windows_path():
    """Extract filename from Windows path."""
    result = nasr.sanitize_filename("C:\\Users\\test\\file.dat")
    assert result == "file.dat"


def test_sanitize_filename_leading_dots():
    """Remove leading dots."""
    result = nasr.sanitize_filename("...test.txt")
    assert not result.startswith(".")


def test_sanitize_filename_trailing_dots():
    """Remove trailing dots."""
    result = nasr.sanitize_filename("test.txt...")
    assert not result.endswith(".")


def test_sanitize_filename_empty():
    """Handle empty filename."""
    with pytest.raises(ValueError, match="cannot be empty"):
        nasr.sanitize_filename("")


def test_sanitize_filename_dot():
    """Replace single dot with default."""
    result = nasr.sanitize_filename(".")
    assert result == "downloaded_file"


def test_sanitize_filename_dotdot():
    """Replace double dot with default."""
    result = nasr.sanitize_filename("..")
    assert result == "downloaded_file"


def test_sanitize_filename_max_length():
    """Truncate long filenames."""
    long_name = "a" * 300 + ".txt"
    result = nasr.sanitize_filename(long_name)
    assert len(result) <= 255
    assert result.endswith(".txt")


def test_sanitize_filename_max_length_no_extension():
    """Truncate long filename without extension."""
    long_name = "a" * 300
    result = nasr.sanitize_filename(long_name)
    assert len(result) <= 255
    assert len(result) == 255


def test_sanitize_filename_preserves_valid_chars():
    """Preserve valid characters."""
    result = nasr.sanitize_filename("test-file_123.v2.dat")
    assert result == "test-file_123.v2.dat"


def test_sanitize_filename_unicode():
    """Handle unicode characters."""
    result = nasr.sanitize_filename("файл.txt")
    assert result == "____.txt"


def test_sanitize_filename_multiple_dots():
    """Handle multiple dots in filename."""
    result = nasr.sanitize_filename("archive.tar.gz")
    assert result == "archive.tar.gz"


def test_load_nasr_database_not_found(tmp_path, monkeypatch):
    """Handle missing database file."""
    # Point to empty directory
    monkeypatch.setattr(nasr, '_NASR_MSGPACK_DATABASE_PATH', tmp_path / 'nasr.msgpack')

    with pytest.raises(FileNotFoundError, match="NASR database not found"):
        nasr.load_nasr_database()


def test_load_nasr_database_valid(tmp_path, monkeypatch):
    """Load valid NASR database."""
    # Create test database
    db_path = tmp_path / 'nasr.msgpack'
    test_data = {
        'waypoints': [
            ['KHAF', 'airport', 37.513, -122.501, 'US', 'KHAF'],
            ['VPMIN', 'fix', 37.5, -122.5, 'US', ''],
        ],
        'airways': [
            ['V25', 'V25', 'Victor'],
        ],
        'connections': {
            0: [(1, 0)],
            1: [(0, 0)],
        },
    }

    with open(db_path, 'wb') as f:
        buffer = msgpack.packb(test_data)
        assert buffer
        f.write(buffer)

    # Point to test database
    monkeypatch.setattr(nasr, '_NASR_MSGPACK_DATABASE_PATH', db_path)

    # Load and verify
    database = nasr.load_nasr_database()

    assert 'waypoints' in database
    assert 'airways' in database
    assert 'connections' in database
    assert len(database['waypoints']) == 2
    assert len(database['airways']) == 1
    assert database['waypoints'][0][0] == 'KHAF'


def test_load_nasr_database_corrupted(tmp_path, monkeypatch):
    """Handle corrupted database file."""
    # Create corrupted file
    db_path = tmp_path / 'nasr.msgpack'
    db_path.write_bytes(b'not valid msgpack data')

    # Point to test database
    monkeypatch.setattr(nasr, '_NASR_MSGPACK_DATABASE_PATH', db_path)

    with pytest.raises(RuntimeError, match="Failed to load NASR database"):
        nasr.load_nasr_database()


def test_load_nasr_database_empty(tmp_path, monkeypatch):
    """Handle empty database file."""
    # Create empty file
    db_path = tmp_path / 'nasr.msgpack'
    db_path.write_bytes(b'')

    # Point to test database
    monkeypatch.setattr(nasr, '_NASR_MSGPACK_DATABASE_PATH', db_path)

    with pytest.raises(RuntimeError, match="Failed to load NASR database"):
        nasr.load_nasr_database()


def test_load_nasr_database_wrong_structure(tmp_path, monkeypatch):
    """Load database with unexpected structure."""
    # Create database with wrong structure
    db_path = tmp_path / 'nasr.msgpack'
    test_data = {'wrong': 'structure'}

    with open(db_path, 'wb') as f:
        buffer = msgpack.packb(test_data)
        assert buffer
        f.write(buffer)

    # Point to test database
    monkeypatch.setattr(nasr, '_NASR_MSGPACK_DATABASE_PATH', db_path)

    # Should load but won't have expected keys
    database = nasr.load_nasr_database()
    assert 'wrong' in database
    assert 'waypoints' not in database


def test_sanitize_filename_null_bytes():
    """Remove null bytes from filename."""
    result = nasr.sanitize_filename("file\x00name.txt")
    assert "\x00" not in result
    assert result == "file_name.txt"


def test_sanitize_filename_newlines():
    """Remove newlines from filename."""
    result = nasr.sanitize_filename("file\nname\r.txt")
    assert "\n" not in result
    assert "\r" not in result
    assert result == "file_name_.txt"


def test_sanitize_filename_only_invalid_chars():
    """Handle filename with only invalid characters."""
    result = nasr.sanitize_filename("@#$%^&*()")
    # Invalid chars become underscores, then get stripped
    assert result == "_________"


def test_sanitize_filename_mixed_slashes():
    """Handle mixed forward and back slashes."""
    result = nasr.sanitize_filename("path/to\\file.txt")
    assert result == "file.txt"


def test_sanitize_filename_custom_max_length():
    """Respect custom max length parameter."""
    long_name = "a" * 50 + ".txt"
    result = nasr.sanitize_filename(long_name, max_length=20)
    assert len(result) <= 20
    assert result.endswith(".txt")


# Tests for validate_sql_identifier


def test_validate_sql_identifier_valid():
    """Valid SQL identifier passes validation."""
    result = nasr.validate_sql_identifier("table_name")
    assert result == "table_name"


def test_validate_sql_identifier_with_numbers():
    """Identifier with numbers is valid."""
    result = nasr.validate_sql_identifier("table123")
    assert result == "table123"


def test_validate_sql_identifier_starts_with_underscore():
    """Identifier starting with underscore is valid."""
    result = nasr.validate_sql_identifier("_private_table")
    assert result == "_private_table"


def test_validate_sql_identifier_uppercase():
    """Uppercase identifier is valid."""
    result = nasr.validate_sql_identifier("TABLE_NAME")
    assert result == "TABLE_NAME"


def test_validate_sql_identifier_mixed_case():
    """Mixed case identifier is valid."""
    result = nasr.validate_sql_identifier("TableName")
    assert result == "TableName"


def test_validate_sql_identifier_empty():
    """Empty identifier raises ValueError."""
    with pytest.raises(ValueError, match="cannot be empty"):
        nasr.validate_sql_identifier("")


def test_validate_sql_identifier_starts_with_number():
    """Identifier starting with number is invalid."""
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        nasr.validate_sql_identifier("123table")


def test_validate_sql_identifier_special_chars():
    """Identifier with special characters is invalid."""
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        nasr.validate_sql_identifier("table-name")


def test_validate_sql_identifier_spaces():
    """Identifier with spaces is invalid."""
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        nasr.validate_sql_identifier("table name")


def test_validate_sql_identifier_reserved_select():
    """Reserved word SELECT is rejected."""
    with pytest.raises(ValueError, match="Reserved word"):
        nasr.validate_sql_identifier("SELECT")


def test_validate_sql_identifier_reserved_insert():
    """Reserved word INSERT is rejected."""
    with pytest.raises(ValueError, match="Reserved word"):
        nasr.validate_sql_identifier("INSERT")


def test_validate_sql_identifier_reserved_delete():
    """Reserved word DELETE is rejected."""
    with pytest.raises(ValueError, match="Reserved word"):
        nasr.validate_sql_identifier("DELETE")


def test_validate_sql_identifier_reserved_lowercase():
    """Reserved word in lowercase is also rejected."""
    with pytest.raises(ValueError, match="Reserved word"):
        nasr.validate_sql_identifier("select")


def test_validate_sql_identifier_sql_injection_attempt():
    """SQL injection attempt is rejected."""
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        nasr.validate_sql_identifier("table; DROP TABLE users;")


def test_validate_sql_identifier_dots():
    """Identifier with dots is invalid."""
    with pytest.raises(ValueError, match="Invalid SQL identifier"):
        nasr.validate_sql_identifier("schema.table")


# Tests for write_msgpack_file


def test_write_msgpack_file_creates_database(tmp_path, monkeypatch):
    """Write msgpack database from CSV data."""
    # Create a minimal mock CSV ZIP structure
    import io
    import zipfile

    # Create outer ZIP with CSV_Data folder containing inner ZIP
    outer_zip_path = tmp_path / 'nasr.zip'
    with zipfile.ZipFile(outer_zip_path, 'w') as outer_zip:
        # Create inner ZIP in memory
        inner_zip_buffer = io.BytesIO()
        with zipfile.ZipFile(inner_zip_buffer, 'w') as inner_zip:
            # Add minimal CSV files
            apt_csv = (
                'ARPT_ID,SITE_TYPE_CODE,LAT_DECIMAL,LONG_DECIMAL,COUNTRY_CODE,ICAO_ID\nKTEST,A,40.0,-120.0,US,KTEST\n'
            )
            fix_csv = 'FIX_ID,FIX_USE_CODE,LAT_DECIMAL,LONG_DECIMAL,COUNTRY_CODE\nFXTEST,RNAV,40.5,-120.5,US\n'
            nav_csv = 'NAV_ID,NAV_TYPE,LAT_DECIMAL,LONG_DECIMAL,COUNTRY_CODE\nVTEST,VOR,41.0,-121.0,US\n'
            awy_csv = 'AWY_ID,AWY_LOCATION,AWY_DESIGNATION\nV999,US,V\n'
            awy_seg_csv = 'AWY_ID,AWY_LOCATION,FROM_POINT,FROM_PT_TYPE,TO_POINT,COUNTRY_CODE,AWY_SEG_GAP_FLAG\nV999,US,KTEST,A,FXTEST,US,N\n'

            inner_zip.writestr('APT_BASE.csv', apt_csv)
            inner_zip.writestr('FIX_BASE.csv', fix_csv)
            inner_zip.writestr('NAV_BASE.csv', nav_csv)
            inner_zip.writestr('AWY_BASE.csv', awy_csv)
            inner_zip.writestr('AWY_SEG_ALT.csv', awy_seg_csv)

        # Write inner ZIP to outer ZIP
        outer_zip.writestr('CSV_Data/nasr.zip', inner_zip_buffer.getvalue())

    # Write msgpack file
    msgpack_path = tmp_path / 'test.msgpack'
    nasr.write_msgpack_file(outer_zip_path, msgpack_path)

    # Verify file was created
    assert msgpack_path.exists()

    # Verify database structure
    with open(msgpack_path, 'rb') as f:
        database = msgpack.unpackb(f.read(), strict_map_key=False)

    assert 'waypoints' in database
    assert 'airways' in database
    assert 'connections' in database

    # Verify waypoints were loaded
    waypoints = database['waypoints']
    assert len(waypoints) >= 3  # At least APT, FIX, NAV

    # Verify one of each type exists
    apt_ids = [w[0] for w in waypoints if w[1] == 'A']
    fix_ids = [w[0] for w in waypoints if w[1] == 'RNAV']
    nav_ids = [w[0] for w in waypoints if w[1] == 'VOR']

    assert 'KTEST' in apt_ids
    assert 'FXTEST' in fix_ids
    assert 'VTEST' in nav_ids

    # Verify airways were loaded
    airways = database['airways']
    assert len(airways) == 1
    assert airways[0][0] == 'V999'


def test_write_msgpack_file_empty_data(tmp_path):
    """Handle empty CSV data gracefully."""
    import io
    import zipfile

    # Create ZIP with empty CSV files
    outer_zip_path = tmp_path / 'nasr_empty.zip'
    with zipfile.ZipFile(outer_zip_path, 'w') as outer_zip:
        inner_zip_buffer = io.BytesIO()
        with zipfile.ZipFile(inner_zip_buffer, 'w') as inner_zip:
            # Add CSV files with headers only
            inner_zip.writestr('APT_BASE.csv', 'ARPT_ID,SITE_TYPE_CODE,LAT_DECIMAL,LONG_DECIMAL,COUNTRY_CODE,ICAO_ID\n')
            inner_zip.writestr('FIX_BASE.csv', 'FIX_ID,FIX_USE_CODE,LAT_DECIMAL,LONG_DECIMAL,COUNTRY_CODE\n')
            inner_zip.writestr('NAV_BASE.csv', 'NAV_ID,NAV_TYPE,LAT_DECIMAL,LONG_DECIMAL,COUNTRY_CODE\n')
            inner_zip.writestr('AWY_BASE.csv', 'AWY_ID,AWY_LOCATION,AWY_DESIGNATION\n')
            inner_zip.writestr(
                'AWY_SEG_ALT.csv',
                'AWY_ID,AWY_LOCATION,FROM_POINT,FROM_PT_TYPE,TO_POINT,COUNTRY_CODE,AWY_SEG_GAP_FLAG\n',
            )

        outer_zip.writestr('CSV_Data/nasr.zip', inner_zip_buffer.getvalue())

    # Write msgpack file
    msgpack_path = tmp_path / 'test_empty.msgpack'
    nasr.write_msgpack_file(outer_zip_path, msgpack_path)

    # Verify file was created with empty data
    assert msgpack_path.exists()

    with open(msgpack_path, 'rb') as f:
        database = msgpack.unpackb(f.read(), strict_map_key=False)

    assert len(database['waypoints']) == 0
    assert len(database['airways']) == 0
    assert len(database['connections']) == 0


# Tests for write_sqlite_file


def test_write_sqlite_file_creates_database(tmp_path):
    """Write sqlite database from CSV data."""
    import io
    import sqlite3
    import zipfile

    # Create a minimal mock CSV ZIP with structure files
    outer_zip_path = tmp_path / 'nasr.zip'
    with zipfile.ZipFile(outer_zip_path, 'w') as outer_zip:
        inner_zip_buffer = io.BytesIO()
        with zipfile.ZipFile(inner_zip_buffer, 'w') as inner_zip:
            # Add structure file
            structure_csv = 'CSV File,Column Name,Max Length,Data Type,Nullable\n'
            structure_csv += 'TEST_BASE,TEST_ID,10,VARCHAR,N\n'
            structure_csv += 'TEST_BASE,TEST_VALUE,20,VARCHAR,Y\n'
            inner_zip.writestr('TEST_BASE_CSV_DATA_STRUCTURE.csv', structure_csv)

            # Add data file
            data_csv = 'TEST_ID,TEST_VALUE\nID1,Value1\nID2,Value2\n'
            inner_zip.writestr('TEST_BASE.csv', data_csv)

        outer_zip.writestr('CSV_Data/nasr.zip', inner_zip_buffer.getvalue())

    # Create post_process_nasr.sql in same directory as nasr.py
    sql_path = Path(nasr.__file__).parent / 'post_process_nasr.sql'
    original_sql_exists = sql_path.exists()
    original_sql_content = sql_path.read_text() if original_sql_exists else ''

    # Write minimal test SQL file
    sql_path.write_text('-- Test SQL file\n')

    try:
        # Write sqlite file
        sqlite_path = tmp_path / 'test.db'
        nasr.write_sqlite_file(outer_zip_path, sqlite_path, spatialite=False)

        # Verify database was created
        assert sqlite_path.exists()

        # Verify table structure and data
        conn = sqlite3.connect(sqlite_path)
        try:
            c = conn.cursor()

            # Check table exists
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='TEST_BASE'")
            assert c.fetchone() is not None

            # Check data was inserted
            c.execute("SELECT COUNT(*) FROM TEST_BASE")
            assert c.fetchone()[0] == 2

            # Check specific values
            c.execute("SELECT TEST_ID, TEST_VALUE FROM TEST_BASE ORDER BY TEST_ID")
            rows = c.fetchall()
            assert rows[0] == ('ID1', 'Value1')
            assert rows[1] == ('ID2', 'Value2')
        finally:
            conn.close()
    finally:
        # Restore original SQL file
        if original_sql_exists:
            sql_path.write_text(original_sql_content)
        else:
            sql_path.unlink()


def test_write_sqlite_file_removes_existing(tmp_path):
    """Existing database file is removed before creating new one."""
    import io
    import sqlite3
    import zipfile

    # Create existing database
    sqlite_path = tmp_path / 'test.db'
    sqlite_path.write_text('old database content')
    assert sqlite_path.exists()

    # Create minimal test data
    outer_zip_path = tmp_path / 'nasr.zip'
    with zipfile.ZipFile(outer_zip_path, 'w') as outer_zip:
        inner_zip_buffer = io.BytesIO()
        with zipfile.ZipFile(inner_zip_buffer, 'w') as inner_zip:
            structure_csv = 'CSV File,Column Name,Max Length,Data Type,Nullable\nTEST,ID,10,VARCHAR,N\n'
            inner_zip.writestr('TEST_CSV_DATA_STRUCTURE.csv', structure_csv)
            inner_zip.writestr('TEST.csv', 'ID\nA\n')
        outer_zip.writestr('CSV_Data/nasr.zip', inner_zip_buffer.getvalue())

    # Temporarily create SQL file
    sql_path = Path(nasr.__file__).parent / 'post_process_nasr.sql'
    original_sql_exists = sql_path.exists()
    original_sql_content = sql_path.read_text() if original_sql_exists else ''
    sql_path.write_text('-- Test\n')

    try:
        # Write sqlite file
        nasr.write_sqlite_file(outer_zip_path, sqlite_path, spatialite=False)

        # Verify new database was created (not old content)
        conn = sqlite3.connect(sqlite_path)
        try:
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = c.fetchall()

            # Should have at least the TEST table
            table_names = [t[0] for t in tables]
            assert 'TEST' in table_names
        finally:
            conn.close()
    finally:
        if original_sql_exists:
            sql_path.write_text(original_sql_content)
        else:
            sql_path.unlink()


def test_write_sqlite_file_validates_table_names(tmp_path):
    """SQL injection in table names is prevented."""
    import io
    import zipfile

    # Create ZIP with malicious table name
    outer_zip_path = tmp_path / 'nasr.zip'
    with zipfile.ZipFile(outer_zip_path, 'w') as outer_zip:
        inner_zip_buffer = io.BytesIO()
        with zipfile.ZipFile(inner_zip_buffer, 'w') as inner_zip:
            # Try to inject SQL via table name
            structure_csv = 'CSV File,Column Name,Max Length,Data Type,Nullable\n'
            structure_csv += 'bad;DROP TABLE users;--,ID,10,VARCHAR,N\n'
            inner_zip.writestr('bad;DROP TABLE users;--_CSV_DATA_STRUCTURE.csv', structure_csv)
            inner_zip.writestr('bad;DROP TABLE users;--.csv', 'ID\nA\n')
        outer_zip.writestr('CSV_Data/nasr.zip', inner_zip_buffer.getvalue())

    # Temporarily create SQL file
    sql_path = Path(nasr.__file__).parent / 'post_process_nasr.sql'
    original_sql_exists = sql_path.exists()
    original_sql_content = sql_path.read_text() if original_sql_exists else ''
    sql_path.write_text('-- Test\n')

    sqlite_path = tmp_path / 'test.db'

    try:
        # Should raise ValueError due to invalid identifier
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            nasr.write_sqlite_file(outer_zip_path, sqlite_path, spatialite=False)
    finally:
        if original_sql_exists:
            sql_path.write_text(original_sql_content)
        else:
            sql_path.unlink()
