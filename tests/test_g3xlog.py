"""
Tests for g3xlog.py - G3X log processing and flight classification.

Tests cover metadata parsing, data analysis, flight type classification,
and log file discovery.
"""

import sys
from pathlib import Path

import pytest

# Import the g3xlog module
sys.path.insert(0, str(Path(__file__).parent.parent))
import g3xlog


def test_parse_log_metadata_valid(tmp_path):
    """Parse metadata from valid G3X log file."""
    log_file = tmp_path / "log_test.csv"
    log_file.write_text(
        '#airframe_info,log_version="1",log_content_version="2",product="G3X Touch",'
        'aircraft_ident="N12345",unit_software_part_number="006-B1234-00",'
        'software_version="10.20",system_id="ABC123",unit="1",'
        'airframe_hours="123.4",engine_hours="100.2"\n'
        'Lcl Date,Lcl Time,UTCOfst,AtvWpt,Latitude,Longitude\n'
        'Date,Time,Offset,Active Waypoint,Lat,Lon\n'
        '01/15/2024,10:30:00,-08:00,KHAF,37.513,-122.501\n'
    )

    metadata = g3xlog._parse_log_metadata(log_file)

    assert metadata['log_version'] == '1'
    assert metadata['log_content_version'] == '2'
    assert metadata['product'] == 'G3X Touch'
    assert metadata['aircraft_ident'] == 'N12345'
    assert metadata['software_version'] == '10.20'
    assert metadata['system_id'] == 'ABC123'
    assert metadata['airframe_hours'] == '123.4'
    assert metadata['engine_hours'] == '100.2'


def test_parse_log_metadata_missing_required_keys(tmp_path):
    """Reject log file missing required metadata keys."""
    log_file = tmp_path / "log_test.csv"
    log_file.write_text(
        '#airframe_info,log_version="1",product="G3X Touch"\n'
        'Lcl Date,Lcl Time\n'
        'Date,Time\n'
    )

    with pytest.raises(ValueError, match="Missing required metadata"):
        g3xlog._parse_log_metadata(log_file)


def test_parse_log_metadata_not_g3x_file(tmp_path):
    """Reject file that is not a G3X log."""
    log_file = tmp_path / "not_g3x.csv"
    log_file.write_text("Some,Random,CSV\n1,2,3\n")

    with pytest.raises(ValueError, match="Not a Garmin G3X log file"):
        g3xlog._parse_log_metadata(log_file)


def test_analyze_log_data_flight(tmp_path):
    """Analyze log data with flight characteristics."""
    log_file = tmp_path / "log_flight.csv"
    log_file.write_text(
        '#airframe_info,log_version="1",log_content_version="2",product="G3X",'
        'aircraft_ident="N12345",unit_software_part_number="006-B1234-00",'
        'software_version="10.20",system_id="ABC123",unit="1",'
        'airframe_hours="123.4",engine_hours="100.2"\n'
        'Display Headers,Oil Pressure,Ground Speed\n'
        'Lcl Date,E1 OilP,GndSpd\n'
        '01/15/2024,25,0\n'
        '01/15/2024,45,15\n'
        '01/15/2024,50,55\n'
        '01/15/2024,48,78\n'
        '01/15/2024,45,12\n'
    )

    oil_press_max, ground_speed_max = g3xlog._analyze_log_data(log_file)

    assert oil_press_max == 50
    assert ground_speed_max == 78.0


def test_analyze_log_data_taxi_only(tmp_path):
    """Analyze log data with taxi-only characteristics."""
    log_file = tmp_path / "log_taxi.csv"
    log_file.write_text(
        '#airframe_info,log_version="1",log_content_version="2",product="G3X",'
        'aircraft_ident="N12345",unit_software_part_number="006-B1234-00",'
        'software_version="10.20",system_id="ABC123",unit="1",'
        'airframe_hours="123.4",engine_hours="100.2"\n'
        'Display Headers,Oil Pressure,Ground Speed\n'
        'Lcl Date,E1 OilP,GndSpd\n'
        '01/15/2024,25,0\n'
        '01/15/2024,45,5\n'
        '01/15/2024,50,12\n'
        '01/15/2024,48,8\n'
    )

    oil_press_max, ground_speed_max = g3xlog._analyze_log_data(log_file)

    assert oil_press_max == 50
    assert ground_speed_max == 12.0


def test_analyze_log_data_config_only(tmp_path):
    """Analyze log data with no engine running (config/testing)."""
    log_file = tmp_path / "log_config.csv"
    log_file.write_text(
        '#airframe_info,log_version="1",log_content_version="2",product="G3X",'
        'aircraft_ident="N12345",unit_software_part_number="006-B1234-00",'
        'software_version="10.20",system_id="ABC123",unit="1",'
        'airframe_hours="123.4",engine_hours="100.2"\n'
        'Display Headers,Oil Pressure,Ground Speed\n'
        'Lcl Date,E1 OilP,GndSpd\n'
        '01/15/2024,0,0\n'
        '01/15/2024,0,0\n'
    )

    oil_press_max, ground_speed_max = g3xlog._analyze_log_data(log_file)

    assert oil_press_max == 0
    assert ground_speed_max == 0.0


def test_analyze_log_data_missing_columns(tmp_path):
    """Reject log file missing required columns."""
    log_file = tmp_path / "log_missing.csv"
    log_file.write_text(
        '#airframe_info,log_version="1",log_content_version="2",product="G3X",'
        'aircraft_ident="N12345",unit_software_part_number="006-B1234-00",'
        'software_version="10.20",system_id="ABC123",unit="1",'
        'airframe_hours="123.4",engine_hours="100.2"\n'
        'Display Headers\n'
        'Lcl Date\n'
        '01/15/2024\n'
    )

    with pytest.raises(ValueError, match="Missing required column"):
        g3xlog._analyze_log_data(log_file)


def test_classify_flight_type_config():
    """Classify as config when no oil pressure."""
    result = g3xlog._classify_flight_type(oil_press_max=0, ground_speed_max=0.0)
    assert result == "config"


def test_classify_flight_type_taxi():
    """Classify as taxi when oil pressure but low speed."""
    result = g3xlog._classify_flight_type(oil_press_max=50, ground_speed_max=25.0)
    assert result == "taxi"


def test_classify_flight_type_taxi_boundary():
    """Classify as taxi at exactly the threshold."""
    result = g3xlog._classify_flight_type(oil_press_max=50, ground_speed_max=49.9)
    assert result == "taxi"


def test_classify_flight_type_flight():
    """Classify as flight when speed exceeds threshold."""
    result = g3xlog._classify_flight_type(oil_press_max=50, ground_speed_max=55.0)
    assert result == "flight"


def test_classify_flight_type_flight_boundary():
    """Classify as flight at exactly the threshold."""
    result = g3xlog._classify_flight_type(oil_press_max=50, ground_speed_max=50.0)
    assert result == "flight"


def test_find_log_files_valid_directory(tmp_path):
    """Find log files in valid directory."""
    # Create test log files
    (tmp_path / "log_001.csv").write_text("test")
    (tmp_path / "log_002.csv").write_text("test")
    (tmp_path / "not_a_log.csv").write_text("test")
    (tmp_path / "log_003.txt").write_text("test")

    # Create subdirectory with log file
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "log_004.csv").write_text("test")

    logs = g3xlog._find_log_files(tmp_path)

    # Should find 3 log_*.csv files (log_001, log_002, log_004)
    assert len(logs) == 3
    assert all(log.name.startswith("log_") and log.suffix == ".csv" for log in logs)
    # Should be sorted
    assert logs[0].name == "log_001.csv"
    assert logs[1].name == "log_002.csv"
    assert logs[2].name == "log_004.csv"


def test_find_log_files_nonexistent_directory(tmp_path):
    """Reject nonexistent directory."""
    bad_path = tmp_path / "does_not_exist"

    with pytest.raises(ValueError, match="Search path does not exist"):
        g3xlog._find_log_files(bad_path)


def test_find_log_files_not_directory(tmp_path):
    """Reject file path instead of directory."""
    file_path = tmp_path / "file.txt"
    file_path.write_text("test")

    with pytest.raises(ValueError, match="not a directory"):
        g3xlog._find_log_files(file_path)


def test_process_logs_no_output(tmp_path):
    """Process logs without copying (analysis only)."""
    # Create a valid log file
    log_file = tmp_path / "log_001.csv"
    log_file.write_text(
        '#airframe_info,log_version="1",log_content_version="2",product="G3X",'
        'aircraft_ident="N12345",unit_software_part_number="006-B1234-00",'
        'software_version="10.20",system_id="ABC123",unit="1",'
        'airframe_hours="123.4",engine_hours="100.2"\n'
        'Display Headers,Oil Pressure,Ground Speed\n'
        'Lcl Date,E1 OilP,GndSpd\n'
        '01/15/2024,50,75\n'
    )

    results = g3xlog._process_logs(tmp_path, output_path=None, verbose=False)

    assert len(results) == 1
    log_path, flight_type, metadata = results[0]
    assert log_path.name == "log_001.csv"
    assert flight_type == "flight"
    assert metadata['aircraft_ident'] == 'N12345'


def test_process_logs_with_output(tmp_path):
    """Process logs and copy to categorized directories."""
    # Create log files with different classifications
    log_flight = tmp_path / "log_flight.csv"
    log_flight.write_text(
        '#airframe_info,log_version="1",log_content_version="2",product="G3X",'
        'aircraft_ident="N12345",unit_software_part_number="006-B1234-00",'
        'software_version="10.20",system_id="ABC123",unit="1",'
        'airframe_hours="123.4",engine_hours="100.2"\n'
        'Display,Oil,Speed\n'
        'Date,E1 OilP,GndSpd\n'
        '01/15/2024,50,75\n'
    )

    log_taxi = tmp_path / "log_taxi.csv"
    log_taxi.write_text(
        '#airframe_info,log_version="1",log_content_version="2",product="G3X",'
        'aircraft_ident="N12345",unit_software_part_number="006-B1234-00",'
        'software_version="10.20",system_id="ABC123",unit="1",'
        'airframe_hours="123.4",engine_hours="100.2"\n'
        'Display,Oil,Speed\n'
        'Date,E1 OilP,GndSpd\n'
        '01/15/2024,50,25\n'
    )

    log_config = tmp_path / "log_config.csv"
    log_config.write_text(
        '#airframe_info,log_version="1",log_content_version="2",product="G3X",'
        'aircraft_ident="N12345",unit_software_part_number="006-B1234-00",'
        'software_version="10.20",system_id="ABC123",unit="1",'
        'airframe_hours="123.4",engine_hours="100.2"\n'
        'Display,Oil,Speed\n'
        'Date,E1 OilP,GndSpd\n'
        '01/15/2024,0,0\n'
    )

    output_path = tmp_path / "output"
    results = g3xlog._process_logs(tmp_path, output_path=output_path, verbose=False)

    assert len(results) == 3

    # Verify output directories created
    assert (output_path / "flight").exists()
    assert (output_path / "taxi").exists()
    assert (output_path / "config").exists()

    # Verify files copied
    assert (output_path / "flight" / "log_flight.csv").exists()
    assert (output_path / "taxi" / "log_taxi.csv").exists()
    assert (output_path / "config" / "log_config.csv").exists()


def test_process_logs_verbose_output(tmp_path, capsys):
    """Process logs with verbose output enabled."""
    log_file = tmp_path / "log_001.csv"
    log_file.write_text(
        '#airframe_info,log_version="1",log_content_version="2",product="G3X Touch",'
        'aircraft_ident="N12345",unit_software_part_number="006-B1234-00",'
        'software_version="10.20",system_id="ABC123",unit="1",'
        'airframe_hours="123.4",engine_hours="100.2"\n'
        'Display,Oil,Speed\n'
        'Date,E1 OilP,GndSpd\n'
        '01/15/2024,50,75\n'
    )

    g3xlog._process_logs(tmp_path, output_path=None, verbose=True)
    captured = capsys.readouterr()

    assert "log_001.csv" in captured.out
    assert "N12345" in captured.out
    assert "G3X Touch" in captured.out
    assert "flight" in captured.out
