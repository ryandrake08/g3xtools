#!/usr/bin/env python3
"""
jdmtool Table Snapshot

Writes tests/fixtures/jdmtool_tables.json from a local jdmtool checkout. The snapshot holds
the format constants and tables that featunlk.py and taw.py derive from jdmtool, and the
jdmtool commit they were read from. tests/test_jdmtool_parity.py compares them with ours.

The jdmtool sources are parsed, not imported.

Usage:
    git clone https://github.com/dimaryaz/jdmtool.git /path/to/jdmtool
    python3 tests/update_jdmtool_fixture.py /path/to/jdmtool
"""

import argparse
import ast
import json
import pathlib
import subprocess
from typing import Any

FIXTURE_PATH = pathlib.Path(__file__).parent / 'fixtures' / 'jdmtool_tables.json'

# jdmtool source file -> constant names to snapshot
CONSTANTS = {
    'featunlk.py': [
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
    'checksum.py': ['FEAT_UNLK_POLYNOMIAL_1', 'FEAT_UNLK_POLYNOMIAL_2'],
    'taw.py': ['TAW_SEPARATOR', 'TAW_MAGIC', 'TAW_DATABASE_TYPES', 'TAW_REGION_PATHS'],
}


def _to_json(value: Any) -> Any:
    """Converts a literal to JSON: bytes as hex strings, dict keys as hex strings."""
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {hex(k) if isinstance(k, int) else k: _to_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json(v) for v in value]
    return value


def _module_constants(source: pathlib.Path, names: list[str]) -> dict[str, Any]:
    """Returns the literal values of the named module-level assignments."""
    found = {}
    for node in ast.parse(source.read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            target, value = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value:
            target, value = node.target.id, node.value
        else:
            continue
        if target in names:
            found[target] = _to_json(ast.literal_eval(value))

    missing = set(names) - found.keys()
    if missing:
        raise ValueError(f"{source}: constants not found: {sorted(missing)}")
    return found


def _features(source: pathlib.Path) -> dict[str, Any]:
    """Returns the Feature enum members as name -> [offset, bit, filenames]."""
    for node in ast.parse(source.read_text()).body:
        if isinstance(node, ast.ClassDef) and node.name == 'Feature':
            return {
                stmt.targets[0].id: _to_json(ast.literal_eval(stmt.value))
                for stmt in node.body
                if isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Name)
            }
    raise ValueError(f"{source}: class Feature not found")


def main() -> None:
    parser = argparse.ArgumentParser(description='Snapshot jdmtool format tables for parity tests')
    parser.add_argument('jdmtool_path', type=pathlib.Path, help='Path to a jdmtool git checkout')
    args = parser.parse_args()

    src = args.jdmtool_path / 'src' / 'jdmtool'
    commit = subprocess.run(
        ['git', '-C', str(args.jdmtool_path), 'rev-parse', 'HEAD'], capture_output=True, text=True, check=True
    ).stdout.strip()

    snapshot: dict[str, Any] = {'commit': commit}
    for filename, names in CONSTANTS.items():
        snapshot[filename] = _module_constants(src / filename, names)
    snapshot['featunlk.py']['Feature'] = _features(src / 'featunlk.py')

    FIXTURE_PATH.write_text(json.dumps(snapshot, indent=2) + '\n')
    print(f"Wrote {FIXTURE_PATH} for jdmtool commit {commit}")


if __name__ == '__main__':
    main()
