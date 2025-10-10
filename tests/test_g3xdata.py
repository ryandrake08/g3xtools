"""
Tests for g3xdata.py - Data manipulation and lookup functions.

Tests cover device lookup, data structure navigation, and path generation.
Network I/O and caching functions are better suited for integration tests.
"""

import sys
from pathlib import Path

import pytest

# Import the g3xdata module
sys.path.insert(0, str(Path(__file__).parent.parent))
import g3xdata

# Test data fixtures
MOCK_AIRCRAFT_DATA = [
    {
        'id': 1,
        'make': 'Vans',
        'model': 'RV-10',
        'year': 2020,
        'serialNumber': 'ABC123',
        'devices': [
            {
                'id': 101,
                'displaySerial': '60001A2345BC0',
                'serial': 123456789,
                'name': 'GDU 460 #1',
                'aircraftID': 'N12345',
                'nextExpectedAvdbAvailability': '2025-11-15T00:00:00Z',
                'avdbTypes': [
                    {
                        'name': 'Navigation Data',
                        'series': [
                            {
                                'id': 2054,
                                'region': {'name': 'USA-VFR'},
                                'installableIssues': [
                                    {
                                        'name': '2510',
                                        'availableAt': '2025-10-01T00:00:00Z',
                                        'effectiveAt': '2025-10-10T00:00:00Z',
                                        'invalidAt': '2025-11-07T00:00:00Z'
                                    }
                                ]
                            }
                        ]
                    }
                ]
            },
            {
                'id': 102,
                'displaySerial': '60001A9876ZYX',
                'serial': 987654321,
                'name': 'GDU 460 #2',
                'aircraftID': 'N12345',
                'avdbTypes': []
            }
        ]
    },
    {
        'id': 2,
        'make': 'Cessna',
        'model': '172',
        'year': 2018,
        'serialNumber': 'XYZ789',
        'devices': [
            {
                'id': 201,
                'displaySerial': '60001B1111AAA',
                'serial': 111111111,
                'name': 'G3X Touch',
                'aircraftID': 'N67890',
                'avdbTypes': []
            }
        ]
    }
]


def test_get_default_device_system_serial():
    """Get display serial of first device."""
    result = g3xdata._get_default_device_system_serial(MOCK_AIRCRAFT_DATA)
    assert result == '60001A2345BC0'


def test_get_default_device_system_serial_empty_aircraft():
    """Raise error when no devices exist."""
    with pytest.raises(ValueError, match="No devices found"):
        g3xdata._get_default_device_system_serial([])


def test_get_default_device_system_serial_no_devices():
    """Raise error when aircraft have no devices."""
    aircraft_no_devices = [
        {'id': 1, 'devices': []}
    ]
    with pytest.raises(ValueError, match="No devices found"):
        g3xdata._get_default_device_system_serial(aircraft_no_devices)


def test_get_device_found():
    """Find device by display serial."""
    device = g3xdata._get_device(MOCK_AIRCRAFT_DATA, '60001A9876ZYX')

    assert device['id'] == 102
    assert device['displaySerial'] == '60001A9876ZYX'
    assert device['serial'] == 987654321
    assert device['name'] == 'GDU 460 #2'


def test_get_device_first_aircraft():
    """Find device in first aircraft."""
    device = g3xdata._get_device(MOCK_AIRCRAFT_DATA, '60001A2345BC0')
    assert device['id'] == 101


def test_get_device_second_aircraft():
    """Find device in second aircraft."""
    device = g3xdata._get_device(MOCK_AIRCRAFT_DATA, '60001B1111AAA')
    assert device['id'] == 201


def test_get_device_not_found():
    """Raise error when display serial not found."""
    with pytest.raises(ValueError, match="Display serial NOTFOUND not found"):
        g3xdata._get_device(MOCK_AIRCRAFT_DATA, 'NOTFOUND')


def test_get_device_empty_aircraft():
    """Raise error when no aircraft."""
    with pytest.raises(ValueError, match="not found"):
        g3xdata._get_device([], '60001A2345BC0')


def test_get_device_info():
    """Get device ID and serial tuple."""
    device_id, system_serial = g3xdata._get_device_info(MOCK_AIRCRAFT_DATA, '60001A2345BC0')

    assert device_id == 101
    assert system_serial == 123456789


def test_get_device_info_second_device():
    """Get info for second device."""
    device_id, system_serial = g3xdata._get_device_info(MOCK_AIRCRAFT_DATA, '60001A9876ZYX')

    assert device_id == 102
    assert system_serial == 987654321


def test_get_device_info_not_found():
    """Raise error when device not found."""
    with pytest.raises(ValueError, match="not found"):
        g3xdata._get_device_info(MOCK_AIRCRAFT_DATA, 'BADSERIAL')


def test_get_cached_file_path_for_url_simple():
    """Generate cache path for simple URL."""
    url = "https://avdb.garmin.com/path/to/file.taw"
    path = g3xdata._get_cached_file_path_for_url(url)

    assert "avdb.garmin.com" in str(path)
    assert "path" in str(path)
    assert "to" in str(path)
    assert path.name == "file.taw"


def test_get_cached_file_path_for_url_nested():
    """Generate cache path for deeply nested URL."""
    url = "https://example.com/a/b/c/d/file.dat"
    path = g3xdata._get_cached_file_path_for_url(url)

    assert "example.com" in str(path)
    assert path.name == "file.dat"
    parts = path.parts
    assert "a" in parts
    assert "b" in parts
    assert "c" in parts
    assert "d" in parts


def test_get_cached_file_path_for_url_no_hostname():
    """Handle URL with no hostname (defaults to avdb.garmin.com)."""
    # This shouldn't happen in practice, but tests defensive coding
    url = "https:///path/to/file.bin"
    path = g3xdata._get_cached_file_path_for_url(url)

    # Should use default hostname
    assert "avdb.garmin.com" in str(path)


def test_get_cached_file_path_for_url_path_traversal():
    """Reject URL with path traversal attempt."""
    url = "https://evil.com/../../etc/passwd"

    with pytest.raises(ValueError, match="directory traversal"):
        g3xdata._get_cached_file_path_for_url(url)


def test_get_cached_file_path_for_url_leading_slash_stripped():
    """Strip leading slash from URL path."""
    url = "https://example.com/file.dat"
    path = g3xdata._get_cached_file_path_for_url(url)

    # Path should not have double slashes
    assert "//" not in str(path)


def test_get_cached_file_path_for_url_query_parameters():
    """Handle URL with query parameters."""
    url = "https://example.com/file.dat?token=abc123&version=2"
    path = g3xdata._get_cached_file_path_for_url(url)

    # Query parameters should not be in path
    assert "?" not in str(path)
    assert "token" not in str(path)
    assert path.name == "file.dat"


def test_get_cached_file_path_for_url_special_chars():
    """Handle URL with special characters."""
    url = "https://example.com/my%20file.dat"
    path = g3xdata._get_cached_file_path_for_url(url)

    # URL encoding should be preserved in path
    assert "my%20file.dat" in str(path)


def test_get_cached_file_path_for_url_creates_parent_dirs(tmp_path, monkeypatch):
    """Verify parent directories are created."""
    # Use tmp_path for testing
    monkeypatch.setattr(g3xdata, '_CACHE_PATH', tmp_path)

    url = "https://example.com/a/b/c/file.dat"
    path = g3xdata._get_cached_file_path_for_url(url)

    # Parent directory should exist
    assert path.parent.exists()
    assert path.parent.is_dir()


def test_get_cached_file_path_for_url_existing_file(tmp_path, monkeypatch):
    """Return existing file path when file exists."""
    monkeypatch.setattr(g3xdata, '_CACHE_PATH', tmp_path)

    url = "https://example.com/test.dat"
    path = g3xdata._get_cached_file_path_for_url(url)

    # Create the file
    path.write_bytes(b'test data')

    # Call again, should return same path
    path2 = g3xdata._get_cached_file_path_for_url(url)
    assert path == path2
    assert path2.exists()


def test_get_cached_file_path_for_url_resolves_within_cache(tmp_path, monkeypatch):
    """Verify resolved path stays within cache directory."""
    monkeypatch.setattr(g3xdata, '_CACHE_PATH', tmp_path)

    url = "https://example.com/path/to/file.dat"
    path = g3xdata._get_cached_file_path_for_url(url)

    # Resolved path should be within cache
    assert tmp_path in path.parents or path.parent == tmp_path


def test_get_device_with_missing_fields():
    """Handle device with missing optional fields gracefully."""
    minimal_aircraft = [
        {
            'id': 1,
            'devices': [
                {
                    'id': 101,
                    'displaySerial': 'TEST123',
                    'serial': 12345,
                    # Missing: name, aircraftID, etc.
                }
            ]
        }
    ]

    device = g3xdata._get_device(minimal_aircraft, 'TEST123')
    assert device['id'] == 101
    assert device['displaySerial'] == 'TEST123'


def test_get_device_info_returns_correct_types():
    """Verify get_device_info returns correct types."""
    device_id, system_serial = g3xdata._get_device_info(MOCK_AIRCRAFT_DATA, '60001A2345BC0')

    assert isinstance(device_id, int)
    assert isinstance(system_serial, int)


def test_get_cached_file_path_for_url_different_hosts():
    """Different hostnames create different cache paths."""
    url1 = "https://host1.example.com/file.dat"
    url2 = "https://host2.example.com/file.dat"

    path1 = g3xdata._get_cached_file_path_for_url(url1)
    path2 = g3xdata._get_cached_file_path_for_url(url2)

    # Paths should be different due to different hosts
    assert path1 != path2
    assert "host1.example.com" in str(path1)
    assert "host2.example.com" in str(path2)


def test_get_cached_file_path_for_url_same_filename_different_paths():
    """Same filename in different paths creates different cache entries."""
    url1 = "https://example.com/path1/file.dat"
    url2 = "https://example.com/path2/file.dat"

    path1 = g3xdata._get_cached_file_path_for_url(url1)
    path2 = g3xdata._get_cached_file_path_for_url(url2)

    # Paths should be different
    assert path1 != path2
    assert "path1" in str(path1)
    assert "path2" in str(path2)


def test_get_device_case_sensitive():
    """Display serial lookup is case-sensitive."""
    # Try with wrong case
    with pytest.raises(ValueError, match="not found"):
        g3xdata._get_device(MOCK_AIRCRAFT_DATA, '60001a2345bc0')  # lowercase


def test_get_cached_file_path_for_url_fragment():
    """Handle URL with fragment identifier."""
    url = "https://example.com/file.dat#section1"
    path = g3xdata._get_cached_file_path_for_url(url)

    # Fragment should not be in path
    assert "#" not in str(path)
    assert "section1" not in str(path)
    assert path.name == "file.dat"
