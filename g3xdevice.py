#!/usr/bin/env python3
"""
Garmin Device XML File Reader

This module provides support for reading GarminDevice.xml files that describe
Garmin avionics device capabilities and installed software/databases.

Quick Start - Reading:
    >>> from g3xdevice import read_device
    >>> device = read_device("GarminDevice.xml")
    >>> print(f"Device: {device.model.description}")
    >>> print(f"Part Number: {device.model.part_number}")
    >>> print(f"Software Version: {device.model.software_version}")
    >>> print(f"Device ID: {device.device_id}")

Quick Start - Listing Updates:
    >>> for update in device.update_files:
    ...     print(f"{update.part_number} v{update.version_major}.{update.version_minor}: {update.description}")

Data Model:
    Device
    ├── model: Model (device hardware/software info)
    ├── device_id: str (unique device identifier)
    ├── data_types: List[DataType] (supported file types)
    ├── update_files: List[UpdateFile] (installed databases/software)
    └── extensions: Any (optional extension data)

    Model
    ├── part_number: str (e.g., "006-B1727-3B")
    ├── software_version: str (e.g., "952")
    └── description: str (e.g., "GDU 460")

    UpdateFile
    ├── part_number: str
    ├── version_major: int
    ├── version_minor: int
    ├── description: str (optional, human-readable name)
    ├── path: str (optional, installation path)
    └── file_name: str (optional, file name)

    DataType
    ├── name: str (e.g., "GPSData", "BaseMaps")
    └── files: List[FileSpec] (supported file specifications)

Usage:
    python3 g3xdevice.py GarminDevice.xml              # Show device summary
    python3 g3xdevice.py GarminDevice.xml --updates    # List installed updates
    python3 g3xdevice.py GarminDevice.xml --data-types # List supported data types
    python3 g3xdevice.py GarminDevice.xml --verbose    # Show all details
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

# Public API
__all__ = [
    # Dataclasses
    'Model',
    'Version',
    'UpdateFile',
    'FileSpec',
    'Location',
    'Specification',
    'DataType',
    'Device',
    # Primary function
    'read_device',
]

# Constants (private - implementation details)
_DEVICE_NAMESPACE = "http://www.garmin.com/xmlschemas/GarminDevice/v2"
_DEVICE_EXT_NAMESPACE = "http://www.garmin.com/xmlschemas/GarminDeviceExtensions/v1"

# Dataclasses
@dataclass
class Model:
    """
    Device model information.

    Attributes:
        part_number: Device part number (e.g., "006-B1727-3B")
        software_version: Software/firmware version (e.g., "952")
        description: Human-readable device description (e.g., "GDU 460")
    """
    part_number: str
    software_version: str
    description: str


@dataclass
class Version:
    """
    Version number with major and minor components.

    Attributes:
        major: Major version number
        minor: Minor version number
    """
    major: int
    minor: int


@dataclass
class UpdateFile:
    """
    Installed software or database update file.

    Attributes:
        part_number: Update part number
        version_major: Major version number
        version_minor: Minor version number
        description: Human-readable description (e.g., "USA-VFR Navigation Data 2510")
        path: Installation path on device (e.g., ".System")
        file_name: File name (e.g., "gmapbmap.img")
    """
    part_number: str
    version_major: int
    version_minor: int
    description: Optional[str] = None
    path: Optional[str] = None
    file_name: Optional[str] = None


@dataclass
class Specification:
    """
    File format specification.

    Attributes:
        identifier: Format identifier (e.g., "http://www.topografix.com/GPX/1/1" or "IMG")
        documentation: URL to format documentation (optional)
    """
    identifier: str
    documentation: Optional[str] = None


@dataclass
class Location:
    """
    File location on device.

    Attributes:
        path: Directory path (e.g., "GPX", ".System")
        base_name: Base file name without extension (optional)
        file_extension: File extension without dot (e.g., "gpx", "img")
    """
    path: str
    base_name: Optional[str] = None
    file_extension: Optional[str] = None


@dataclass
class FileSpec:
    """
    File specification for a supported data type.

    Attributes:
        specification: File format specification
        location: File location on device
        transfer_direction: Transfer direction ("InputToUnit", "OutputFromUnit", "InputOutput")
    """
    specification: Specification
    location: Location
    transfer_direction: str


@dataclass
class DataType:
    """
    Supported data type (e.g., GPS data, maps, voices).

    Attributes:
        name: Data type name (e.g., "GPSData", "BaseMaps", "Voices")
        files: List of file specifications for this data type
    """
    name: str
    files: list[FileSpec]


@dataclass
class Device:
    """
    Garmin device description.

    Attributes:
        model: Device model information
        device_id: Unique device identifier
        data_types: List of supported data types
        update_files: List of installed update files
        extensions: Extension data (optional)
    """
    model: Model
    device_id: str
    data_types: list[DataType]
    update_files: list[UpdateFile]
    extensions: Optional[Any] = None


# XML Parsing (Deserialization)

def _get_text(element: Optional[ET.Element], default: str = "") -> str:
    """
    Get text content from element, return default if None.

    Args:
        element: XML element
        default: Default value if element is None or has no text

    Returns:
        Text content or default value
    """
    if element is None:
        return default
    return element.text if element.text is not None else default


def _parse_model(model_elem: ET.Element, ns: str) -> Model:
    """
    Parse Model element.

    Args:
        model_elem: Model XML element
        ns: Namespace prefix

    Returns:
        Model dataclass instance
    """
    part_number = _get_text(model_elem.find(f"{ns}PartNumber"))
    software_version = _get_text(model_elem.find(f"{ns}SoftwareVersion"))
    description = _get_text(model_elem.find(f"{ns}Description"))

    return Model(
        part_number=part_number,
        software_version=software_version,
        description=description
    )


def _parse_specification(spec_elem: ET.Element, ns: str) -> Specification:
    """
    Parse Specification element.

    Args:
        spec_elem: Specification XML element
        ns: Namespace prefix

    Returns:
        Specification dataclass instance
    """
    identifier = _get_text(spec_elem.find(f"{ns}Identifier"))
    documentation = _get_text(spec_elem.find(f"{ns}Documentation")) or None

    return Specification(
        identifier=identifier,
        documentation=documentation
    )


def _parse_location(loc_elem: ET.Element, ns: str) -> Location:
    """
    Parse Location element.

    Args:
        loc_elem: Location XML element
        ns: Namespace prefix

    Returns:
        Location dataclass instance
    """
    path = _get_text(loc_elem.find(f"{ns}Path"))
    base_name = _get_text(loc_elem.find(f"{ns}BaseName")) or None
    file_extension = _get_text(loc_elem.find(f"{ns}FileExtension")) or None

    return Location(
        path=path,
        base_name=base_name,
        file_extension=file_extension
    )


def _parse_file_spec(file_elem: ET.Element, ns: str) -> FileSpec:
    """
    Parse File element.

    Args:
        file_elem: File XML element
        ns: Namespace prefix

    Returns:
        FileSpec dataclass instance
    """
    spec_elem = file_elem.find(f"{ns}Specification")
    loc_elem = file_elem.find(f"{ns}Location")
    transfer_direction = _get_text(file_elem.find(f"{ns}TransferDirection"))

    specification = _parse_specification(spec_elem, ns) if spec_elem is not None else Specification("")
    location = _parse_location(loc_elem, ns) if loc_elem is not None else Location("")

    return FileSpec(
        specification=specification,
        location=location,
        transfer_direction=transfer_direction
    )


def _parse_data_type(dt_elem: ET.Element, ns: str) -> DataType:
    """
    Parse DataType element.

    Args:
        dt_elem: DataType XML element
        ns: Namespace prefix

    Returns:
        DataType dataclass instance
    """
    name = _get_text(dt_elem.find(f"{ns}Name"))
    files = [_parse_file_spec(f, ns) for f in dt_elem.findall(f"{ns}File")]

    return DataType(
        name=name,
        files=files
    )


def _parse_update_file(uf_elem: ET.Element, ns: str) -> UpdateFile:
    """
    Parse UpdateFile element.

    Args:
        uf_elem: UpdateFile XML element
        ns: Namespace prefix

    Returns:
        UpdateFile dataclass instance
    """
    part_number = _get_text(uf_elem.find(f"{ns}PartNumber"))

    version_elem = uf_elem.find(f"{ns}Version")
    if version_elem is not None:
        version_major = int(_get_text(version_elem.find(f"{ns}Major"), "0"))
        version_minor = int(_get_text(version_elem.find(f"{ns}Minor"), "0"))
    else:
        version_major = 0
        version_minor = 0

    description = _get_text(uf_elem.find(f"{ns}Description")) or None
    path = _get_text(uf_elem.find(f"{ns}Path")) or None
    file_name = _get_text(uf_elem.find(f"{ns}FileName")) or None

    return UpdateFile(
        part_number=part_number,
        version_major=version_major,
        version_minor=version_minor,
        description=description,
        path=path,
        file_name=file_name
    )


def _parse_device(root: ET.Element) -> Device:
    """
    Parse Device root element.

    Args:
        root: Device root XML element

    Returns:
        Device dataclass instance
    """
    # Handle namespace
    ns = f"{{{_DEVICE_NAMESPACE}}}"

    # Parse Model (required)
    model_elem = root.find(f"{ns}Model")
    if model_elem is None:
        raise ValueError("Device XML missing required Model element")
    model = _parse_model(model_elem, ns)

    # Parse Id (required)
    device_id = _get_text(root.find(f"{ns}Id"))
    if not device_id:
        raise ValueError("Device XML missing required Id element")

    # Parse MassStorageMode (optional)
    data_types = []
    update_files = []
    msm_elem = root.find(f"{ns}MassStorageMode")
    if msm_elem is not None:
        # Parse DataType elements
        data_types = [_parse_data_type(dt, ns) for dt in msm_elem.findall(f"{ns}DataType")]

        # Parse UpdateFile elements
        update_files = [_parse_update_file(uf, ns) for uf in msm_elem.findall(f"{ns}UpdateFile")]

    # Parse Extensions (optional)
    extensions_elem = root.find(f"{ns}Extensions")
    extensions = extensions_elem if extensions_elem is not None else None

    return Device(
        model=model,
        device_id=device_id,
        data_types=data_types,
        update_files=update_files,
        extensions=extensions
    )


def read_device(file_path: Union[str, Path]) -> Device:
    """
    Read a GarminDevice.xml file and return a Device dataclass.

    Args:
        file_path: Path to the GarminDevice.xml file

    Returns:
        A Device dataclass instance

    Raises:
        FileNotFoundError: If the file doesn't exist
        xml.etree.ElementTree.ParseError: If the XML is malformed
        ValueError: If required elements are missing

    Example:
        >>> device = read_device("GarminDevice.xml")
        >>> print(f"Device: {device.model.description}")
        >>> print(f"Part Number: {device.model.part_number}")
    """
    path = Path(file_path)

    tree = ET.parse(path)
    root = tree.getroot()
    return _parse_device(root)


def main() -> None:
    """Command-line interface for reading GarminDevice.xml files."""
    parser = argparse.ArgumentParser(description='Read and display information from GarminDevice.xml files')
    parser.add_argument('file', help='Path to GarminDevice.xml file')
    parser.add_argument('-u', '--updates', action='store_true', help='List installed update files (databases, software)')
    parser.add_argument('-d', '--data-types', action='store_true', help='List supported data types and file formats')
    parser.add_argument('-v', '--verbose', action='store_true', help='Show all available information')
    args = parser.parse_args()

    # Check that file exists
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    # Read device file
    try:
        device = read_device(file_path)
    except (ET.ParseError, ValueError) as e:
        print(f"Error parsing device file: {e}", file=sys.stderr)
        sys.exit(1)

    # Default: Show device summary
    if not args.updates and not args.data_types:
        print(f"Device: {device.model.description}")
        print(f"Part Number: {device.model.part_number}")
        print(f"Software Version: {device.model.software_version}")
        print(f"Device ID: {device.device_id}")
        print(f"Installed Updates: {len(device.update_files)}")
        print(f"Supported Data Types: {len(device.data_types)}")

    # Show installed updates
    if args.updates or args.verbose:
        if args.verbose and not args.updates:
            print()
        print("Installed Updates:")
        if not device.update_files:
            print("  (none)")
        else:
            # Group updates by type
            databases = []
            software = []
            other = []

            for update in device.update_files:
                if update.description:
                    databases.append(update)
                elif update.file_name and update.file_name.endswith('.GCD'):
                    software.append(update)
                else:
                    other.append(update)

            if databases:
                print("\n  Databases:")
                for update in databases:
                    version = f"{update.version_major}.{update.version_minor}"
                    print(f"    {update.part_number:20s} v{version:6s} - {update.description}")

            if software:
                print("\n  Software/Firmware:")
                for update in software:
                    version = f"{update.version_major}.{update.version_minor}"
                    desc = update.file_name or update.part_number
                    print(f"    {update.part_number:20s} v{version:6s} - {desc}")

            if other:
                print("\n  Other:")
                for update in other:
                    version = f"{update.version_major}.{update.version_minor}"
                    desc = update.file_name or "(no description)"
                    print(f"    {update.part_number:20s} v{version:6s} - {desc}")

    # Show data types
    if args.data_types or args.verbose:
        if args.verbose or args.updates:
            print()
        print("Supported Data Types:")
        if not device.data_types:
            print("  (none)")
        else:
            for dt in device.data_types:
                print(f"\n  {dt.name}:")
                for file_spec in dt.files:
                    direction = file_spec.transfer_direction
                    location = file_spec.location

                    # Build file path string
                    path_parts = []
                    if location.path:
                        path_parts.append(location.path)
                    if location.base_name:
                        path_parts.append(location.base_name)
                    if location.file_extension:
                        if location.base_name:
                            path_parts[-1] += f".{location.file_extension}"
                        else:
                            path_parts.append(f"*.{location.file_extension}")

                    file_path_str = "/".join(path_parts) if path_parts else "(no path)"

                    # Show format
                    spec_id = file_spec.specification.identifier
                    if spec_id.startswith("http"):
                        # URL - show just the last part
                        spec_short = spec_id.split('/')[-1]
                    else:
                        spec_short = spec_id

                    print(f"    {direction:15s} {file_path_str:40s} [{spec_short}]")


if __name__ == '__main__':
    main()
