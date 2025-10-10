"""
Shared pytest fixtures for g3xtools tests.

This module provides common fixtures used across all test modules including:
- Mock Garmin API responses (NEVER makes real HTTP requests)
- Synthetic test data paths
- Temporary directory fixtures
"""

from pathlib import Path
from typing import Any

import pytest

# Test fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to test fixtures directory."""
    return FIXTURES_DIR


@pytest.fixture
def mock_garmin_api(requests_mock):
    """
    Mock all Garmin API endpoints with synthetic data.

    CRITICAL: This fixture prevents ANY real HTTP requests to Garmin servers.
    All data is synthetic and safe to use in tests.
    """
    # Mock aircraft list endpoint
    # Note: Real API returns a list directly (starts with [{), not {"aircraft": [...]}
    requests_mock.get(
        "https://fly.garmin.com/fly-garmin/api/aircraft/",
        json=[
            {
                "id": 1,
                "tailNumber": "N12345TEST",
                "makeModel": "Test Aircraft",
                "year": 2020,
                "devices": [
                    {
                        "id": "000000000",
                        "name": "G3X Touch",
                        "serialNumber": "999999999",
                        "databaseTypes": [
                            {
                                "id": 1,
                                "name": "Navigation",
                                "series": [
                                    {
                                        "id": 9999,
                                        "region": "Americas",
                                        "installableIssues": [
                                            {
                                                "name": "TEST-2024-01",
                                                "effectiveAt": "2024-01-01T00:00:00Z",
                                                "invalidAt": "2024-02-01T00:00:00Z",
                                                "availableAt": "2023-12-15T00:00:00Z",
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
        headers={"Content-Type": "application/json"},
    )

    # Mock series details endpoint (note: /avdb-series/ not /series/)
    requests_mock.get(
        "https://fly.garmin.com/fly-garmin/api/avdb-series/9999/",
        json={"id": 9999, "region": "Americas", "databaseTypeId": 1},
        headers={"Content-Type": "application/json"},
    )

    # Mock files list endpoint
    requests_mock.get(
        "https://fly.garmin.com/fly-garmin/api/avdb-series/9999/TEST-2024-01/files/",
        json={
            "mainFiles": [{"url": "https://example.com/test_nav.taw", "filename": "test_nav.taw"}],
            "auxiliaryFiles": [],
        },
        headers={"Content-Type": "application/json"},
    )

    # Mock unlock endpoint
    requests_mock.get(
        "https://fly.garmin.com/fly-garmin/api/avdb-series/9999/TEST-2024-01/unlock/",
        json={"unlockCode": "SYNTHETIC_UNLOCK_CODE"},
        headers={"Content-Type": "application/json"},
    )

    return requests_mock


@pytest.fixture
def synthetic_aircraft_data() -> dict[str, Any]:
    """
    Synthetic aircraft data for testing.

    Returns dictionary matching the structure returned by flygarmin_list_aircraft.
    All data is synthetic and safe for testing.
    """
    return {
        "aircraft": [
            {
                "id": 1,
                "tailNumber": "N12345TEST",
                "makeModel": "Test Aircraft",
                "year": 2020,
                "devices": [
                    {
                        "id": "000000000",
                        "name": "G3X Touch",
                        "serialNumber": "999999999",
                        "databaseTypes": [
                            {
                                "id": 1,
                                "name": "Navigation",
                                "series": [
                                    {
                                        "id": 9999,
                                        "region": "Americas",
                                        "installableIssues": [
                                            {
                                                "name": "TEST-2024-01",
                                                "effectiveAt": "2024-01-01T00:00:00Z",
                                                "invalidAt": "2024-02-01T00:00:00Z",
                                                "availableAt": "2023-12-15T00:00:00Z",
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


@pytest.fixture
def synthetic_nasr_database() -> dict[str, Any]:
    """
    Minimal synthetic NASR database for flight planning tests.

    Contains 3 waypoints with known distances for testing:
    - KAAA to KBBB: ~60nm (using haversine)
    - KAAA to VPTEST: ~30nm
    - KBBB to VPTEST: ~30nm

    All coordinates are synthetic and do not represent real locations.
    """
    return {
        "waypoints": [
            ["KAAA", "A", 40.0, -120.0, "US", "KAAA"],  # Synthetic airport A
            ["KBBB", "A", 40.5, -120.5, "US", "KBBB"],  # Synthetic airport B
            ["VPTEST", "VFR", 40.25, -120.25, "US", ""],  # Synthetic VFR waypoint
            ["KCCC", "A", 41.0, -121.0, "US", "KCCC"],  # Synthetic airport C
        ],
        "airways": [
            ["V999", "TEST", "V"],  # Synthetic airway
        ],
        "connections": {
            0: [(1, 0), (2, -1)],  # KAAA connects to KBBB via V999, VPTEST direct
            1: [(0, 0), (2, -1), (3, -1)],  # KBBB connects back
            2: [(0, -1), (1, -1)],  # VPTEST connects to both
            3: [(1, -1)],  # KCCC connects to KBBB
        },
    }
