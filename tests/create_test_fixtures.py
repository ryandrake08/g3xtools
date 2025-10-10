#!/usr/bin/env python3
"""
Generate all synthetic test fixtures.

This is the master script to regenerate ALL test fixtures. Run this when:
- Setting up tests for the first time
- Test data formats change
- Fixtures get corrupted

Usage:
    python tests/create_test_fixtures.py

All fixtures are 100% synthetic and safe to commit to source control.
"""

import sys
from pathlib import Path
from typing import Union

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import msgpack

import fpl
import g3xchecklist as ace


def create_fpl_fixtures(fixtures_dir: Path):
    """Create FPL (Flight Plan) test fixtures."""

    print("\n=== Creating FPL fixtures ===")

    # 1. simple_route.fpl - Basic 2-waypoint route
    waypoints = [
        fpl.create_waypoint("KAAA", 40.0, -120.0, fpl.WAYPOINT_TYPE_AIRPORT, "US", "SYNTHETIC AIRPORT A"),
        fpl.create_waypoint("KBBB", 40.5, -120.5, fpl.WAYPOINT_TYPE_AIRPORT, "US", "SYNTHETIC AIRPORT B"),
    ]
    route = fpl.create_route(
        "TEST ROUTE",
        [
            ("KAAA", fpl.WAYPOINT_TYPE_AIRPORT, "US"),
            ("KBBB", fpl.WAYPOINT_TYPE_AIRPORT, "US"),
        ],
        flight_plan_index=1,
    )
    flight_plan = fpl.create_flight_plan(waypoints, route)
    fpl.write_fpl(flight_plan, fixtures_dir / "simple_route.fpl")
    print("  Created simple_route.fpl")

    # 2. user_waypoint.fpl - Route with user waypoint
    waypoints = [
        fpl.create_waypoint("KAAA", 40.0, -120.0, fpl.WAYPOINT_TYPE_AIRPORT, "US", "SYNTHETIC AIRPORT A"),
        fpl.create_waypoint("USR001", 40.25, -120.25, fpl.WAYPOINT_TYPE_USER, "", "USER WAYPOINT 1"),
        fpl.create_waypoint("KBBB", 40.5, -120.5, fpl.WAYPOINT_TYPE_AIRPORT, "US", "SYNTHETIC AIRPORT B"),
    ]
    route = fpl.create_route(
        "USER WPT TEST",
        [
            ("KAAA", fpl.WAYPOINT_TYPE_AIRPORT, "US"),
            ("USR001", fpl.WAYPOINT_TYPE_USER, ""),
            ("KBBB", fpl.WAYPOINT_TYPE_AIRPORT, "US"),
        ],
        flight_plan_index=2,
    )
    flight_plan = fpl.create_flight_plan(waypoints, route)
    fpl.write_fpl(flight_plan, fixtures_dir / "user_waypoint.fpl")
    print("  Created user_waypoint.fpl")

    # 3. invalid_route.fpl - Route with invalid waypoint reference
    waypoints = [
        fpl.create_waypoint("KAAA", 40.0, -120.0, fpl.WAYPOINT_TYPE_AIRPORT, "US", "SYNTHETIC AIRPORT A"),
    ]
    route = fpl.create_route(
        "INVALID TEST",
        [
            ("KAAA", fpl.WAYPOINT_TYPE_AIRPORT, "US"),
            ("NONEXISTENT", fpl.WAYPOINT_TYPE_AIRPORT, "US"),  # References non-existent waypoint
        ],
        flight_plan_index=3,
    )
    flight_plan = fpl.create_flight_plan(waypoints, route)
    fpl.write_fpl(flight_plan, fixtures_dir / "invalid_route.fpl")
    print("  Created invalid_route.fpl")


def create_yaml_fixtures(fixtures_dir: Path):
    """Create YAML checklist test fixtures."""

    print("\n=== Creating YAML fixtures ===")

    # 1. minimal.yaml - Valid minimal checklist
    minimal = {
        "metadata": {
            "name": "Test Checklist",
            "aircraft_make_model": "Test Aircraft",
            "aircraft_information": "N12345TEST",
            "manufacturer_identification": "Test Manufacturer",
            "copyright_information": "Copyright 2024",
            "file_format_rev": 0,
            "unknown_field": 1,
        },
        "defaults": {
            "group": 0,
            "checklist": 0,
        },
        "groups": [
            {
                "name": "Pre-Flight",
                "checklists": [
                    {
                        "name": "Exterior Inspection",
                        "items": [
                            {
                                "type": "challenge_response",
                                "text": "Fuel Quantity",
                                "response": "SUFFICIENT",
                                "justification": "left",
                            },
                            {
                                "type": "warning",
                                "text": "PROPELLER AREA CLEAR",
                                "justification": "center",
                            },
                            {
                                "type": "blank_line",
                                "justification": "left",
                            },
                        ],
                    },
                ],
            },
        ],
    }

    import yaml

    with open(fixtures_dir / "minimal.yaml", "w") as f:
        yaml.dump(minimal, f, default_flow_style=False, sort_keys=False)
    print("  Created minimal.yaml")

    # 2. invalid.yaml - Missing required fields
    invalid = {
        "metadata": {
            "name": "Invalid Checklist",
            # Missing required aircraft_make_model field
            "aircraft_information": "Invalid",
        },
        "defaults": {
            "group": "not_a_number",  # Should be int
            "checklist": 0,
        },
        "groups": [
            {
                "this_is_wrong": "Missing name field",
                "checklists": [
                    {
                        "items": []  # Missing name field
                    }
                ],
            }
        ],
    }

    with open(fixtures_dir / "invalid.yaml", "w") as f:
        yaml.dump(invalid, f, default_flow_style=False, sort_keys=False)
    print("  Created invalid.yaml")


def create_ace_fixtures(fixtures_dir: Path):
    """Create ACE (binary checklist) test fixtures."""

    print("\n=== Creating ACE fixtures ===")

    # 1. minimal.ace - Valid minimal checklist
    minimal = ace.AceFile(
        name="Test Checklist",
        aircraft_make_model="Test Aircraft",
        aircraft_information="N12345TEST",
        manufacturer_identification="Test Manufacturer",
        copyright_information="Copyright 2024",
        file_format_rev=0xF0,
        unknown_field=1,
        default_group=0,
        default_checklist=0,
    )

    group = ace.Group(name="Pre-Flight")
    checklist = ace.Checklist(name="Exterior Inspection")
    checklist.items.append(
        ace.ChecklistItem(type="challenge_response", text="Fuel Quantity", response="SUFFICIENT", justification="left")
    )
    checklist.items.append(ace.ChecklistItem(type="warning", text="PROPELLER AREA CLEAR", justification="center"))
    checklist.items.append(ace.ChecklistItem(type="blank_line"))
    group.checklists.append(checklist)
    minimal.groups.append(group)

    ace.write_ace_binary(minimal, fixtures_dir / "minimal.ace")
    print("  Created minimal.ace")

    # 2. invalid_crc.ace - Corrupted CRC
    ace.write_ace_binary(minimal, fixtures_dir / "invalid_crc.ace")
    with open(fixtures_dir / "invalid_crc.ace", "r+b") as f:
        f.seek(-4, 2)
        f.write(b"\x00\x00\x00\x00")
    print("  Created invalid_crc.ace")

    # 3. truncated.ace - Incomplete file
    with open(fixtures_dir / "truncated.ace", "wb") as f:
        f.write(b"\xf0\xf0\xf0\xf0")
    print("  Created truncated.ace")


def create_nasr_fixtures(fixtures_dir: Path):
    """Create NASR database test fixture."""

    print("\n=== Creating NASR fixture ===")

    database = {
        "waypoints": [
            ["KAAA", "A", 40.0, -120.0, "US", "KAAA"],
            ["KBBB", "A", 40.5, -120.5, "US", "KBBB"],
            ["VPTEST", "VFR", 40.25, -120.25, "US", ""],
            ["KCCC", "A", 41.0, -121.0, "US", "KCCC"],
            ["VORNAV", "V", 40.6, -120.6, "US", ""],
            ["NDBPT", "N", 40.1, -120.1, "US", ""],
        ],
        "airways": [
            ["V999", "TEST", "V"],
            ["J888", "TEST", "J"],
        ],
        "connections": {
            0: [(1, 0), (2, -1), (5, -1)],
            1: [(0, 0), (2, -1), (3, -1), (4, -1)],
            2: [(0, -1), (1, -1)],
            3: [(1, 1)],
            4: [(1, -1)],
            5: [(0, -1)],
        },
    }

    packed_data: Union[bytes, None] = msgpack.packb(database)
    if packed_data:
        with open(fixtures_dir / "nasr_test.msgpack", "wb") as f:
            f.write(packed_data)
    print("  Created nasr_test.msgpack")


if __name__ == "__main__":
    fixtures_dir = Path(__file__).parent / "fixtures"
    fixtures_dir.mkdir(exist_ok=True)

    print("=" * 60)
    print("Generating all test fixtures")
    print("=" * 60)

    create_fpl_fixtures(fixtures_dir)
    create_yaml_fixtures(fixtures_dir)
    create_ace_fixtures(fixtures_dir)
    create_nasr_fixtures(fixtures_dir)

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)
