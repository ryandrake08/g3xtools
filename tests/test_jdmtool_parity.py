"""
Tests that featunlk.py and taw.py match the jdmtool tables they are derived from.

tests/fixtures/jdmtool_tables.json is a snapshot of jdmtool's format constants and tables,
written by tests/update_jdmtool_fixture.py. Intentional differences are listed below; any
other difference means the snapshot was refreshed and our tables need reviewing.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import featunlk
import taw

FIXTURE = json.loads((Path(__file__).parent / 'fixtures' / 'jdmtool_tables.json').read_text())

# TAW region paths where g3xtools intentionally differs from jdmtool: region -> (jdmtool, g3xtools)
REGION_PATH_DIFFERENCES = {
    0x24: ('FCharts.dat', 'fc_tpc/fc_tpc.dat'),
    0x25: ('Fcharts.fca', 'fc_tpc/fc_tpc.fca'),
}


def _int_keys(table: dict[str, str]) -> dict[int, str]:
    return {int(k, 16): v for k, v in table.items()}


def test_region_path_differences_are_current():
    """Each listed difference still matches jdmtool's value, so none is stale."""
    jdmtool_paths = _int_keys(FIXTURE['taw.py']['TAW_REGION_PATHS'])
    for region, (jdmtool_path, g3xtools_path) in REGION_PATH_DIFFERENCES.items():
        assert jdmtool_paths[region] == jdmtool_path
        assert taw._TAW_REGION_PATHS[region] == g3xtools_path


def test_taw_region_paths_match():
    """TAW region paths match jdmtool apart from the listed differences."""
    expected = _int_keys(FIXTURE['taw.py']['TAW_REGION_PATHS'])
    expected.update({region: ours for region, (_, ours) in REGION_PATH_DIFFERENCES.items()})
    assert expected == taw._TAW_REGION_PATHS


@pytest.mark.parametrize('table', [taw._TAW_DATABASE_TYPES, featunlk._DATABASE_TYPES])
def test_database_types_match(table):
    """Both copies of the device type table match jdmtool."""
    assert table == _int_keys(FIXTURE['taw.py']['TAW_DATABASE_TYPES'])


def test_taw_constants_match():
    """TAW separator and magic match jdmtool."""
    assert taw._TAW_SEPARATOR.hex() == FIXTURE['taw.py']['TAW_SEPARATOR']
    assert taw._TAW_MAGIC.hex() == FIXTURE['taw.py']['TAW_MAGIC']


def test_features_match():
    """Feature offsets, bits, and filenames match jdmtool."""
    ours = {f.name: [f.offset, f.bit, f.filenames] for f in featunlk._Feature}
    assert ours == FIXTURE['featunlk.py']['Feature']


@pytest.mark.parametrize(
    'name',
    [
        'FEAT_UNLK',
        'CONTENT1_LEN',
        'CONTENT2_LEN',
        'SEC_ID_OFFSET',
        'MAGIC1',
        'MAGIC2',
        'MAGIC3',
        'NAVIGATION_PREVIEW_START',
        'NAVIGATION_PREVIEW_END',
        'CHUNK_SIZE',
        'DB_MAGIC',
        'DB_MAGIC2',
    ],
)
def test_featunlk_constants_match(name):
    """feat_unlk format constants match jdmtool."""
    assert getattr(featunlk, f'_{name}') == FIXTURE['featunlk.py'][name]


@pytest.mark.parametrize('name', ['FEAT_UNLK_POLYNOMIAL_1', 'FEAT_UNLK_POLYNOMIAL_2'])
def test_checksum_constants_match(name):
    """feat_unlk checksum polynomials match jdmtool."""
    assert getattr(featunlk, f'_{name}') == FIXTURE['checksum.py'][name]


@pytest.mark.parametrize('module', [featunlk, taw])
def test_module_docstring_names_snapshot_commit(module):
    """Each derived module's docstring names the jdmtool commit of the snapshot."""
    assert f"jdmtool commit {FIXTURE['commit'][:7]}" in module.__doc__
