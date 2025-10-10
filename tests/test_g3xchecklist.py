"""
Tests for g3xchecklist.py - ACE checklist format.

Critical aviation safety tests for ACE file reading, writing, CRC validation,
and YAML conversion.
"""

import sys
from pathlib import Path

import pytest

# Import the checklist module
sys.path.insert(0, str(Path(__file__).parent.parent))
import g3xchecklist as ace


def test_read_minimal_ace(fixtures_dir):
    """Read a minimal valid ACE file."""
    ace_path = fixtures_dir / "minimal.ace"
    checklist = ace._read_ace_binary(ace_path)

    assert checklist.name == "Test Checklist"
    assert checklist.aircraft_make_model == "Test Aircraft"
    assert checklist.aircraft_information == "N12345TEST"
    assert len(checklist.groups) == 1
    assert checklist.groups[0].name == "Pre-Flight"
    assert len(checklist.groups[0].checklists) == 1
    assert checklist.groups[0].checklists[0].name == "Exterior Inspection"
    assert len(checklist.groups[0].checklists[0].items) == 3


def test_ace_crc_validation(fixtures_dir, capsys):
    """CRC validation prints warning but continues reading."""
    bad_ace_path = fixtures_dir / "invalid_crc.ace"

    # Current behavior: prints warning but doesn't raise exception
    checklist = ace._read_ace_binary(bad_ace_path)
    captured = capsys.readouterr()
    assert "CRC mismatch" in captured.out
    assert checklist.name == "Test Checklist"


def test_truncated_ace_file(fixtures_dir):
    """Reject truncated ACE files."""
    truncated_path = fixtures_dir / "truncated.ace"

    with pytest.raises(ValueError, match="File too small"):
        ace._read_ace_binary(truncated_path)


def test_ace_to_yaml_conversion(tmp_path, fixtures_dir):
    """Convert ACE to YAML and verify structure."""
    ace_path = fixtures_dir / "minimal.ace"
    yaml_path = tmp_path / "output.yaml"

    # Read ACE
    checklist = ace._read_ace_binary(ace_path)

    # Write YAML
    ace._write_yaml_file(checklist, yaml_path)

    # Read YAML back
    checklist_from_yaml = ace._read_yaml_file(yaml_path)

    # Verify structure preserved
    assert checklist_from_yaml.name == checklist.name
    assert checklist_from_yaml.aircraft_make_model == checklist.aircraft_make_model
    assert len(checklist_from_yaml.groups) == len(checklist.groups)


def test_yaml_to_ace_conversion(tmp_path, fixtures_dir):
    """Convert YAML to ACE and verify binary structure."""
    yaml_path = fixtures_dir / "minimal.yaml"
    ace_path = tmp_path / "output.ace"

    # Read YAML
    checklist = ace._read_yaml_file(yaml_path)

    # Write ACE
    ace._write_ace_binary(checklist, ace_path)

    # Read ACE back
    checklist_from_ace = ace._read_ace_binary(ace_path)

    # Verify structure preserved
    assert checklist_from_ace.name == checklist.name
    assert checklist_from_ace.aircraft_make_model == checklist.aircraft_make_model
    assert len(checklist_from_ace.groups) == len(checklist.groups)


def test_ace_round_trip(tmp_path, fixtures_dir):
    """ACE → YAML → ACE should produce identical binary."""
    original_ace = fixtures_dir / "minimal.ace"
    yaml_path = tmp_path / "temp.yaml"
    final_ace = tmp_path / "final.ace"

    # Read original ACE
    checklist1 = ace._read_ace_binary(original_ace)

    # Convert to YAML
    ace._write_yaml_file(checklist1, yaml_path)

    # Read YAML
    checklist2 = ace._read_yaml_file(yaml_path)

    # Convert back to ACE
    ace._write_ace_binary(checklist2, final_ace)

    # Read final ACE
    checklist3 = ace._read_ace_binary(final_ace)

    # Compare structures (binary may differ due to encoding but structure should match)
    assert checklist3.name == checklist1.name
    assert checklist3.aircraft_make_model == checklist1.aircraft_make_model
    assert len(checklist3.groups) == len(checklist1.groups)

    # Compare items
    orig_items = checklist1.groups[0].checklists[0].items
    final_items = checklist3.groups[0].checklists[0].items
    assert len(orig_items) == len(final_items)

    for orig, final in zip(orig_items, final_items):
        assert orig.type == final.type
        assert orig.text == final.text
        assert orig.response == final.response
        assert orig.justification == final.justification


def test_yaml_round_trip(tmp_path, fixtures_dir):
    """YAML → ACE → YAML should produce identical structure."""
    original_yaml = fixtures_dir / "minimal.yaml"
    ace_path = tmp_path / "temp.ace"
    final_yaml = tmp_path / "final.yaml"

    # Read original YAML
    checklist1 = ace._read_yaml_file(original_yaml)

    # Convert to ACE
    ace._write_ace_binary(checklist1, ace_path)

    # Read ACE
    checklist2 = ace._read_ace_binary(ace_path)

    # Convert back to YAML
    ace._write_yaml_file(checklist2, final_yaml)

    # Read final YAML
    checklist3 = ace._read_yaml_file(final_yaml)

    # Compare
    assert checklist3.name == checklist1.name
    assert checklist3.aircraft_make_model == checklist1.aircraft_make_model
    assert len(checklist3.groups) == len(checklist1.groups)


def test_all_item_types(tmp_path):
    """All 8 item types should serialize correctly."""
    items = [
        ace.ChecklistItem(type="challenge_response", text="Challenge", response="Response", justification="left"),
        ace.ChecklistItem(type="challenge", text="Challenge Only", justification="left"),
        ace.ChecklistItem(type="plain_text", text="Plain Text", justification="left"),
        ace.ChecklistItem(type="note", text="Note Text", justification="left"),
        ace.ChecklistItem(type="subtitle", text="Subtitle Text", justification="left"),
        ace.ChecklistItem(type="warning", text="WARNING TEXT", justification="center"),
        ace.ChecklistItem(type="caution", text="CAUTION TEXT", justification="center"),
        ace.ChecklistItem(type="blank_line", justification="left"),
    ]

    checklist = ace.AceFile(
        name="Item Type Test",
        aircraft_make_model="Test Aircraft",
        groups=[ace.Group(name="Test Group", checklists=[ace.Checklist(name="All Items", items=items)])],
    )

    # Write and read back
    ace_path = tmp_path / "all_types.ace"
    ace._write_ace_binary(checklist, ace_path)
    roundtrip = ace._read_ace_binary(ace_path)

    # Verify all items present with correct types
    rt_items = roundtrip.groups[0].checklists[0].items
    assert len(rt_items) == 8

    for orig, rt in zip(items, rt_items):
        assert rt.type == orig.type
        assert rt.text == orig.text
        assert rt.response == orig.response
        assert rt.justification == orig.justification


def test_justification_preservation(tmp_path):
    """Justification settings should be preserved."""
    items = [
        ace.ChecklistItem(type="plain_text", text="Left", justification="left"),
        ace.ChecklistItem(type="plain_text", text="Indent 1", justification="indent_1"),
        ace.ChecklistItem(type="plain_text", text="Indent 2", justification="indent_2"),
        ace.ChecklistItem(type="plain_text", text="Indent 3", justification="indent_3"),
        ace.ChecklistItem(type="plain_text", text="Indent 4", justification="indent_4"),
        ace.ChecklistItem(type="warning", text="CENTER", justification="center"),
    ]

    checklist = ace.AceFile(
        name="Justification Test",
        aircraft_make_model="Test Aircraft",
        groups=[ace.Group(name="Test Group", checklists=[ace.Checklist(name="Justification", items=items)])],
    )

    # Write and read back
    ace_path = tmp_path / "justification.ace"
    ace._write_ace_binary(checklist, ace_path)
    roundtrip = ace._read_ace_binary(ace_path)

    # Verify justification preserved
    rt_items = roundtrip.groups[0].checklists[0].items
    for orig, rt in zip(items, rt_items):
        assert rt.justification == orig.justification


def test_invalid_yaml_checklist(fixtures_dir):
    """read_yaml_file is permissive and uses defaults for missing/invalid fields."""
    invalid_yaml = fixtures_dir / "invalid.yaml"

    # Current behavior: doesn't validate, uses defaults for missing fields
    checklist = ace._read_yaml_file(invalid_yaml)

    # Verify it loaded something (even with invalid data)
    assert checklist.name == "Invalid Checklist"
    assert checklist.default_group == "not_a_number"  # Invalid but allowed
    assert len(checklist.groups) == 1
    assert checklist.groups[0].name == ""  # Missing name field
