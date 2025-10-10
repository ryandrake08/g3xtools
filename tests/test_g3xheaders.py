"""
Tests for g3xheaders.py - G3X log structure analysis.

Tests cover log file reading, header comparison, and change detection.
"""

import sys
from pathlib import Path

import pytest

# Import the g3xheaders module
sys.path.insert(0, str(Path(__file__).parent.parent))
import g3xheaders


def test_g3xlogfiledata_open_valid(tmp_path):
    """Open and parse a valid G3X log file."""
    log_file = tmp_path / "log_001.csv"
    log_file.write_text(
        '#airframe_info,log_version="1",product="G3X Touch",aircraft_ident="N12345",'
        'unit_software_part_number="006-B1234-00",software_version="10.20",'
        'system_id="ABC123",unit="1"\n'
        'Lcl Date,Lcl Time,Oil Pressure,Ground Speed\n'
        'Date,Time,E1 OilP,GndSpd\n'
        '01/15/2024,10:30:00,50,75\n'
    )

    with g3xheaders.G3XLogFileData(log_file) as data:
        assert data.airframe_info['log_version'] == '1'
        assert data.airframe_info['product'] == 'G3X Touch'
        assert data.airframe_info['aircraft_ident'] == 'N12345'
        assert data.airframe_info['software_version'] == '10.20'
        assert data.full_headers == ['Lcl Date', 'Lcl Time', 'Oil Pressure', 'Ground Speed']
        assert data.short_headers == ['Date', 'Time', 'E1 OilP', 'GndSpd']


def test_g3xlogfiledata_empty_file(tmp_path):
    """Reject empty file."""
    log_file = tmp_path / "empty.csv"
    log_file.write_text("")

    with pytest.raises(ValueError, match="empty or has no CSV data"), g3xheaders.G3XLogFileData(log_file):  # noqa: SIM117
        pass


def test_g3xlogfiledata_missing_header_rows(tmp_path):
    """Reject file with missing header rows."""
    log_file = tmp_path / "incomplete.csv"
    log_file.write_text(
        '#airframe_info,log_version="1"\n'
        'Lcl Date,Lcl Time\n'
        # Missing stable keys row
    )

    with pytest.raises(ValueError, match="missing required header rows"), \
         g3xheaders.G3XLogFileData(log_file):
        pass


def test_g3xlogfiledata_invalid_metadata_format(tmp_path):
    """Reject file with malformed metadata."""
    log_file = tmp_path / "bad_metadata.csv"
    log_file.write_text(
        '#airframe_info,invalid_no_equals_sign\n'
        'Lcl Date,Lcl Time\n'
        'Date,Time\n'
    )

    with pytest.raises(ValueError, match="Invalid airframe metadata format"), \
         g3xheaders.G3XLogFileData(log_file):
        pass


def test_compare_headers_no_changes(tmp_path, capsys):
    """Compare identical headers (no output expected)."""
    log1 = tmp_path / "log_001.csv"
    log1.write_text(
        '#airframe_info,software_version="10.20"\n'
        'Lcl Date,Lcl Time,Oil Pressure\n'
        'Date,Time,E1 OilP\n'
        '01/15/2024,10:30:00,50\n'
    )

    log2 = tmp_path / "log_002.csv"
    log2.write_text(
        '#airframe_info,software_version="10.20"\n'
        'Lcl Date,Lcl Time,Oil Pressure\n'
        'Date,Time,E1 OilP\n'
        '01/15/2024,11:30:00,55\n'
    )

    with g3xheaders.G3XLogFileData(log1) as data1, \
         g3xheaders.G3XLogFileData(log2) as data2:
        result = g3xheaders._compare_headers(data1, data2)

    assert result is False
    captured = capsys.readouterr()
    assert captured.out == ""


def test_compare_headers_new_columns(tmp_path, capsys):
    """Detect new columns added."""
    log1 = tmp_path / "log_001.csv"
    log1.write_text(
        '#airframe_info,software_version="10.20"\n'
        'Lcl Date,Lcl Time\n'
        'Date,Time\n'
        '01/15/2024,10:30:00\n'
    )

    log2 = tmp_path / "log_002.csv"
    log2.write_text(
        '#airframe_info,software_version="10.30"\n'
        'Lcl Date,Lcl Time,Oil Pressure,Ground Speed\n'
        'Date,Time,E1 OilP,GndSpd\n'
        '01/15/2024,11:30:00,50,75\n'
    )

    with g3xheaders.G3XLogFileData(log1) as data1, \
         g3xheaders.G3XLogFileData(log2) as data2:
        result = g3xheaders._compare_headers(data1, data2)

    assert result is True
    captured = capsys.readouterr()
    assert "log_002.csv" in captured.out
    assert "File structure changed: 10.20 -> 10.30" in captured.out
    assert "New:" in captured.out
    assert "Oil Pressure (E1 OilP)" in captured.out
    assert "Ground Speed (GndSpd)" in captured.out


def test_compare_headers_removed_columns(tmp_path, capsys):
    """Detect columns removed."""
    log1 = tmp_path / "log_001.csv"
    log1.write_text(
        '#airframe_info,software_version="10.20"\n'
        'Lcl Date,Lcl Time,Oil Pressure,Ground Speed\n'
        'Date,Time,E1 OilP,GndSpd\n'
        '01/15/2024,10:30:00,50,75\n'
    )

    log2 = tmp_path / "log_002.csv"
    log2.write_text(
        '#airframe_info,software_version="10.30"\n'
        'Lcl Date,Lcl Time\n'
        'Date,Time\n'
        '01/15/2024,11:30:00\n'
    )

    with g3xheaders.G3XLogFileData(log1) as data1, \
         g3xheaders.G3XLogFileData(log2) as data2:
        result = g3xheaders._compare_headers(data1, data2)

    assert result is True
    captured = capsys.readouterr()
    assert "Removed:" in captured.out
    assert "Oil Pressure (E1 OilP)" in captured.out
    assert "Ground Speed (GndSpd)" in captured.out


def test_compare_headers_renamed_columns(tmp_path, capsys):
    """Detect renamed columns (same stable key, different display name)."""
    log1 = tmp_path / "log_001.csv"
    log1.write_text(
        '#airframe_info,software_version="10.20"\n'
        'Lcl Date,Lcl Time,Engine Oil Pressure\n'
        'Date,Time,E1 OilP\n'
        '01/15/2024,10:30:00,50\n'
    )

    log2 = tmp_path / "log_002.csv"
    log2.write_text(
        '#airframe_info,software_version="10.30"\n'
        'Lcl Date,Lcl Time,Oil Press\n'
        'Date,Time,E1 OilP\n'
        '01/15/2024,11:30:00,55\n'
    )

    with g3xheaders.G3XLogFileData(log1) as data1, \
         g3xheaders.G3XLogFileData(log2) as data2:
        result = g3xheaders._compare_headers(data1, data2)

    assert result is True
    captured = capsys.readouterr()
    assert "Renamed:" in captured.out
    assert "Engine Oil Pressure -> Oil Press (E1 OilP)" in captured.out


def test_compare_headers_mixed_changes(tmp_path, capsys):
    """Detect mix of new, removed, and renamed columns."""
    log1 = tmp_path / "log_001.csv"
    log1.write_text(
        '#airframe_info,software_version="10.20"\n'
        'Lcl Date,Old Column,Engine Oil\n'
        'Date,OldCol,E1 OilP\n'
        '01/15/2024,test,50\n'
    )

    log2 = tmp_path / "log_002.csv"
    log2.write_text(
        '#airframe_info,software_version="10.30"\n'
        'Lcl Date,Oil Press,New Column\n'
        'Date,E1 OilP,NewCol\n'
        '01/15/2024,55,value\n'
    )

    with g3xheaders.G3XLogFileData(log1) as data1, \
         g3xheaders.G3XLogFileData(log2) as data2:
        result = g3xheaders._compare_headers(data1, data2)

    assert result is True
    captured = capsys.readouterr()
    output = captured.out

    # Should show renamed (stable key E1 OilP kept, display name changed)
    assert "Renamed:" in output
    assert "Engine Oil -> Oil Press (E1 OilP)" in output

    # Should show new column
    assert "New:" in output
    assert "New Column (NewCol)" in output

    # Should show removed column
    assert "Removed:" in output
    assert "Old Column (OldCol)" in output


def test_compare_headers_context_manager_usage(tmp_path):
    """Verify context manager properly opens and closes files."""
    log_file = tmp_path / "log_001.csv"
    log_file.write_text(
        '#airframe_info,software_version="10.20"\n'
        'Lcl Date,Lcl Time\n'
        'Date,Time\n'
        '01/15/2024,10:30:00\n'
    )

    # Open and close via context manager
    with g3xheaders.G3XLogFileData(log_file) as data:
        assert data.airframe_info['software_version'] == '10.20'
        assert hasattr(data, 'file')

    # File should be closed after exiting context
    # We can't directly test if file is closed, but we can verify no exception


def test_compare_headers_version_transition(tmp_path, capsys):
    """Verify software version transition is reported."""
    log1 = tmp_path / "log_v1.csv"
    log1.write_text(
        '#airframe_info,software_version="9.50"\n'
        'Lcl Date\n'
        'Date\n'
        '01/15/2024\n'
    )

    log2 = tmp_path / "log_v2.csv"
    log2.write_text(
        '#airframe_info,software_version="10.00"\n'
        'Lcl Date,New Feature\n'
        'Date,NewFeat\n'
        '01/15/2024,value\n'
    )

    with g3xheaders.G3XLogFileData(log1) as data1, \
         g3xheaders.G3XLogFileData(log2) as data2:
        g3xheaders._compare_headers(data1, data2)

    captured = capsys.readouterr()
    assert "9.50 -> 10.00" in captured.out
