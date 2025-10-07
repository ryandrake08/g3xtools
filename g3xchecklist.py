#!/usr/bin/env python3
"""
Garmin G3X Checklist Converter

Converts Garmin G3X aviation checklist files (.ace) to and from human-readable
YAML format for easier editing and version control.

Usage:
    # Extract ACE binary to YAML
    python3 g3xchecklist.py -x checklist.ace -o checklist.yaml

    # Compile YAML to ACE binary
    python3 g3xchecklist.py -c checklist.yaml -o checklist.ace

The YAML format provides a hierarchical structure with groups containing
checklists, which contain items of various types (challenges, responses,
warnings, etc.). This allows for easy manual editing while maintaining
full compatibility with Garmin G3X displays.
"""

import argparse
import pathlib
import struct
import sys
import zlib
from dataclasses import dataclass, field
from typing import List, Optional, Union

try:
    import yaml
except ImportError:
    print("Error: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)

# Constants
ACE_HEADER_SIGNATURE = b'\xf0\xf0\xf0\xf0'
ACE_HEADER_SIZE = 10
ACE_FOOTER_SIZE = 4

# Item type mappings
ITEM_TYPE_TO_ACE = {
    'challenge_response': 'r',
    'challenge': 'c',
    'plain_text': 'p',
    'note': 'n',
    'subtitle': 't',
    'warning': 'w',
    'caution': 'a',
    'blank_line': '',
}

ACE_TO_ITEM_TYPE = {v: k for k, v in ITEM_TYPE_TO_ACE.items()}

# Justification mappings
JUSTIFICATION_TO_ACE = {
    'left': '0',
    'indent_1': '1',
    'indent_2': '2',
    'indent_3': '3',
    'indent_4': '4',
    'center': 'c',
}

ACE_TO_JUSTIFICATION = {v: k for k, v in JUSTIFICATION_TO_ACE.items()}

@dataclass
class ChecklistItem:
    """Represents a single checklist item.

    Attributes:
        type: Item type (challenge_response, plain_text, note, title, warning, caution, blank_line)
        text: Main text content of the item
        response: Response text (only for challenge_response type)
        justification: Text alignment (left, center, indent1, indent2, indent3)
    """
    type: str
    text: str = ""
    response: str = ""
    justification: str = "left"

@dataclass
class Checklist:
    """Represents a checklist containing multiple items.

    Attributes:
        name: Name of the checklist
        items: List of checklist items
    """
    name: str
    items: List[ChecklistItem] = field(default_factory=list)

@dataclass
class Group:
    """Represents a group containing multiple checklists.

    Attributes:
        name: Name of the group
        checklists: List of checklists in this group
    """
    name: str
    checklists: List[Checklist] = field(default_factory=list)

@dataclass
class AceFile:
    """Represents the complete ACE file structure.

    Attributes:
        name: Checklist name
        aircraft_make_model: Aircraft make and model information
        aircraft_information: Additional aircraft information
        manufacturer_identification: Manufacturer identification string
        copyright_information: Copyright notice
        file_format_rev: ACE file format revision number
        unknown_field: Unknown field from ACE header (always 1)
        default_group: Default group index
        default_checklist: Default checklist index
        groups: List of checklist groups
    """
    # Metadata
    name: str = ""
    aircraft_make_model: str = ""
    aircraft_information: str = ""
    manufacturer_identification: str = ""
    copyright_information: str = ""

    # File properties
    file_format_rev: int = 0
    unknown_field: int = 1
    default_group: int = 0
    default_checklist: int = 0

    # Content
    groups: List[Group] = field(default_factory=list)

# ================================================================
# ACE BINARY FORMAT FUNCTIONS
# ================================================================

def calculate_crc32(data: bytes, crc: int = 0) -> int:
    """Calculate CRC32 checksum for ACE file validation."""
    return zlib.crc32(data, crc) & 0xffffffff

def read_ace_binary(file_path: pathlib.Path) -> AceFile:
    """Read and parse an ACE binary file."""
    with open(file_path, 'rb') as f:
        data = f.read()

    if len(data) < ACE_HEADER_SIZE + ACE_FOOTER_SIZE:
        raise ValueError("File too small to be a valid ACE file")

    # Parse header
    header = data[:ACE_HEADER_SIZE]
    content = data[ACE_HEADER_SIZE:-ACE_FOOTER_SIZE]
    footer = data[-ACE_FOOTER_SIZE:]

    # Validate signature
    if header[:4] != ACE_HEADER_SIGNATURE:
        raise ValueError("Invalid ACE file signature")

    # Extract header fields
    file_format_rev = header[4]
    unknown_field = header[5]
    default_group = header[6]
    default_checklist = header[7]

    # Validate CRC
    expected_crc = struct.unpack('<I', footer)[0]
    header_crc = calculate_crc32(header)
    calculated_crc = ~calculate_crc32(content, header_crc) & 0xffffffff

    if expected_crc != calculated_crc:
        print(f"WARNING: CRC mismatch. Expected {expected_crc:08x}, got {calculated_crc:08x}")

    # Decode content
    try:
        content_str = content.decode('iso-8859-1')
    except UnicodeDecodeError as e:
        raise ValueError(f"Failed to decode content as ISO-8859-1: {e}")

    lines = content_str.split('\r\n')

    # Validate structure
    if len(lines) < 7:  # 5 metadata lines + END + empty
        raise ValueError("Invalid ACE file structure")

    if lines[-2] != "END":
        print("WARNING: Missing END marker")

    if lines[-1] != "":
        print("WARNING: Content after END marker")

    # Parse metadata
    ace_file = AceFile(
        file_format_rev=file_format_rev,
        unknown_field=unknown_field,
        default_group=default_group,
        default_checklist=default_checklist,
        name=lines[0],
        aircraft_make_model=lines[1],
        aircraft_information=lines[2],
        manufacturer_identification=lines[3],
        copyright_information=lines[4]
    )

    # Parse content structure
    current_group = None
    current_checklist = None

    for line in lines[5:-2]:  # Skip metadata and END marker
        if not line:  # Blank line
            if current_checklist is not None:
                item = ChecklistItem(type='blank_line')
                current_checklist.items.append(item)
            continue

        item_type = line[0]

        if item_type == '<':  # Group start
            just = line[1]
            text = line[2:]
            current_group = Group(name=text)
            ace_file.groups.append(current_group)

        elif item_type == '>':  # Group end
            current_group = None

        elif item_type == '(':  # Checklist start
            if current_group is None:
                raise ValueError("Checklist found outside of group")
            just = line[1]
            text = line[2:]
            current_checklist = Checklist(name=text)
            current_group.checklists.append(current_checklist)

        elif item_type == ')':  # Checklist end
            current_checklist = None

        elif item_type == 'r':  # Challenge/Response
            if current_checklist is None:
                raise ValueError("Item found outside of checklist")
            just = line[1]
            rest = line[2:]
            if '~' in rest:
                challenge, response = rest.split('~', 1)
            else:
                challenge, response = rest, ""

            item = ChecklistItem(
                type='challenge_response',
                text=challenge,
                response=response,
                justification=ACE_TO_JUSTIFICATION.get(just, 'left')
            )
            current_checklist.items.append(item)

        elif item_type in 'cpntwac':  # Other item types
            if current_checklist is None:
                raise ValueError("Item found outside of checklist")
            just = line[1]
            text = line[2:]

            item = ChecklistItem(
                type=ACE_TO_ITEM_TYPE.get(item_type, 'plain_text'),
                text=text,
                justification=ACE_TO_JUSTIFICATION.get(just, 'left')
            )
            current_checklist.items.append(item)

    return ace_file

def write_ace_binary(ace_file: AceFile, file_path: pathlib.Path) -> None:
    """Write an AceFile to binary ACE format."""
    # Build header
    header = bytearray(ACE_HEADER_SIGNATURE)
    header.append(ace_file.file_format_rev)
    header.append(ace_file.unknown_field)
    header.append(ace_file.default_group)
    header.append(ace_file.default_checklist)
    header.extend(b'\r\n')

    # Build content lines
    lines = [
        ace_file.name,
        ace_file.aircraft_make_model,
        ace_file.aircraft_information,
        ace_file.manufacturer_identification,
        ace_file.copyright_information
    ]

    # Convert structure to lines
    for group in ace_file.groups:
        lines.append(f"<0{group.name}")

        for checklist in group.checklists:
            lines.append(f"(0{checklist.name}")

            for item in checklist.items:
                if item.type == 'blank_line':
                    lines.append("")
                elif item.type == 'challenge_response':
                    just = JUSTIFICATION_TO_ACE.get(item.justification, '0')
                    if item.response:
                        lines.append(f"r{just}{item.text}~{item.response}")
                    else:
                        # Convert to challenge if no response
                        lines.append(f"c{just}{item.text}")
                else:
                    ace_type = ITEM_TYPE_TO_ACE.get(item.type, 'p')
                    just = JUSTIFICATION_TO_ACE.get(item.justification, '0')
                    lines.append(f"{ace_type}{just}{item.text}")

            lines.append(")")

        lines.append(">")

    lines.append("END")
    lines.append("")

    # Encode content
    content_str = '\r\n'.join(lines)
    try:
        content = content_str.encode('iso-8859-1')
    except UnicodeEncodeError as e:
        raise ValueError(f"Content contains characters not supported by ISO-8859-1: {e}")

    # Calculate CRC
    header_bytes = bytes(header)
    header_crc = calculate_crc32(header_bytes)
    crc = ~calculate_crc32(content, header_crc) & 0xffffffff
    footer = struct.pack('<I', crc)

    # Write file
    with open(file_path, 'wb') as f:
        f.write(header_bytes)
        f.write(content)
        f.write(footer)

# ================================================================
# YAML FORMAT FUNCTIONS
# ================================================================

def ace_to_yaml_dict(ace_file: AceFile) -> dict:
    """Convert AceFile to YAML-compatible dictionary."""
    yaml_dict = {
        'metadata': {
            'name': ace_file.name,
            'aircraft_make_model': ace_file.aircraft_make_model,
            'aircraft_information': ace_file.aircraft_information,
            'manufacturer_identification': ace_file.manufacturer_identification,
            'copyright_information': ace_file.copyright_information,
        },
        'defaults': {
            'group': ace_file.default_group,
            'checklist': ace_file.default_checklist,
        },
        'groups': []
    }

    for group in ace_file.groups:
        group_dict = {
            'name': group.name,
            'checklists': []
        }

        for checklist in group.checklists:
            checklist_dict = {
                'name': checklist.name,
                'items': []
            }

            for item in checklist.items:
                if item.type == 'blank_line':
                    item_dict = {'type': 'blank_line'}
                else:
                    item_dict = {
                        'type': item.type,
                        'text': item.text,
                        'justification': item.justification,
                    }
                    if item.type == 'challenge_response' and item.response:
                        item_dict['response'] = item.response

                checklist_dict['items'].append(item_dict)

            group_dict['checklists'].append(checklist_dict)

        yaml_dict['groups'].append(group_dict)

    return yaml_dict

def yaml_dict_to_ace(yaml_dict: dict) -> AceFile:
    """Convert YAML dictionary to AceFile."""
    metadata = yaml_dict.get('metadata', {})
    defaults = yaml_dict.get('defaults', {})

    ace_file = AceFile(
        name=metadata.get('name', ''),
        aircraft_make_model=metadata.get('aircraft_make_model', ''),
        aircraft_information=metadata.get('aircraft_information', ''),
        manufacturer_identification=metadata.get('manufacturer_identification', ''),
        copyright_information=metadata.get('copyright_information', ''),
        default_group=defaults.get('group', 0),
        default_checklist=defaults.get('checklist', 0),
    )

    for group_data in yaml_dict.get('groups', []):
        group = Group(name=group_data.get('name', ''))

        for checklist_data in group_data.get('checklists', []):
            checklist = Checklist(name=checklist_data.get('name', ''))

            for item_data in checklist_data.get('items', []):
                item_type = item_data.get('type', 'plain_text')

                if item_type == 'blank_line':
                    item = ChecklistItem(type='blank_line')
                else:
                    item = ChecklistItem(
                        type=item_type,
                        text=item_data.get('text', ''),
                        response=item_data.get('response', ''),
                        justification=item_data.get('justification', 'left')
                    )

                checklist.items.append(item)

            group.checklists.append(checklist)

        ace_file.groups.append(group)

    return ace_file

def write_yaml_file(ace_file: AceFile, file_path: pathlib.Path) -> None:
    """Write AceFile to YAML format."""
    yaml_dict = ace_to_yaml_dict(ace_file)

    with open(file_path, 'w', encoding='utf-8') as f:
        # Add header comment
        f.write("# Garmin G3X Aviation Checklist\n")
        f.write("# Generated by g3xchecklist.py\n")
        f.write("# Edit this file and convert back to .ace format for use with Garmin G3X\n\n")

        yaml.dump(yaml_dict, f, default_flow_style=False, allow_unicode=True,
                 sort_keys=False, indent=2)

def read_yaml_file(file_path: pathlib.Path) -> AceFile:
    """Read YAML file and convert to AceFile."""
    with open(file_path, 'r', encoding='utf-8') as f:
        yaml_dict = yaml.safe_load(f)

    if not isinstance(yaml_dict, dict):
        raise ValueError("YAML file must contain a dictionary at the root level")

    return yaml_dict_to_ace(yaml_dict)

# ================================================================
# CONVERSION FUNCTIONS
# ================================================================

def ace_to_yaml(ace_path: pathlib.Path, yaml_path: pathlib.Path) -> None:
    """Convert ACE binary file to YAML format."""
    try:
        print(f"Reading ACE file: {ace_path}", file=sys.stderr)
        ace_file = read_ace_binary(ace_path)

        print(f"Writing YAML file: {yaml_path}", file=sys.stderr)
        write_yaml_file(ace_file, yaml_path)

        # Print summary to stderr
        total_items = sum(len(checklist.items) for group in ace_file.groups for checklist in group.checklists)
        print(f"Converted successfully:", file=sys.stderr)
        print(f"  Groups: {len(ace_file.groups)}", file=sys.stderr)
        print(f"  Checklists: {sum(len(group.checklists) for group in ace_file.groups)}", file=sys.stderr)
        print(f"  Items: {total_items}", file=sys.stderr)

    except Exception as e:
        print(f"Error converting ACE to YAML: {e}", file=sys.stderr)
        sys.exit(1)

def yaml_to_ace(yaml_path: pathlib.Path, ace_path: pathlib.Path) -> None:
    """Convert YAML file to ACE binary format."""
    try:
        print(f"Reading YAML file: {yaml_path}", file=sys.stderr)
        ace_file = read_yaml_file(yaml_path)

        print(f"Writing ACE file: {ace_path}", file=sys.stderr)
        write_ace_binary(ace_file, ace_path)

        # Print summary to stderr
        total_items = sum(len(checklist.items) for group in ace_file.groups for checklist in group.checklists)
        print(f"Converted successfully:", file=sys.stderr)
        print(f"  Groups: {len(ace_file.groups)}", file=sys.stderr)
        print(f"  Checklists: {sum(len(group.checklists) for group in ace_file.groups)}", file=sys.stderr)
        print(f"  Items: {total_items}", file=sys.stderr)

    except Exception as e:
        print(f"Error converting YAML to ACE: {e}", file=sys.stderr)
        sys.exit(1)

def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Convert Garmin G3X checklist files between binary (.ace) and YAML formats',
        epilog='Examples:\n'
               '  %(prog)s -x checklist.ace -o checklist.yaml    # Extract ACE to YAML\n'
               '  %(prog)s -c checklist.yaml -o checklist.ace   # Compile YAML to ACE',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-x', '--extract', metavar='ACE_FILE', help='Extract ACE binary file to YAML format')
    group.add_argument('-c', '--compile', metavar='YAML_FILE', help='Compile YAML file to ACE binary format')
    parser.add_argument('-o', '--output', required=True, metavar='OUTPUT_FILE', help='Output file path')

    args = parser.parse_args()

    # Validate input file exists
    input_file = pathlib.Path(args.extract or args.compile).resolve()
    if not input_file.exists():
        print(f"Error: Input file does not exist: {input_file}", file=sys.stderr)
        sys.exit(1)
    if not input_file.is_file():
        print(f"Error: Input path is not a file: {input_file}", file=sys.stderr)
        sys.exit(1)

    # Validate output path
    output_file = pathlib.Path(args.output).resolve()
    if not output_file.parent.exists():
        print(f"Error: Output directory does not exist: {output_file.parent}", file=sys.stderr)
        sys.exit(1)

    if args.extract:
        ace_to_yaml(input_file, output_file)
    elif args.compile:
        yaml_to_ace(input_file, output_file)

if __name__ == "__main__":
    main()