#!/usr/bin/env python3
"""
Garmin Device XML File Reader

This module provides support for reading GarminDevice.xml files that describe
Garmin avionics device capabilities and installed software/databases.

Quick Start - Reading:
    >>> from garmin_device import read_device
    >>> device = read_device("GarminDevice.xml")
    >>> print(f"Device: {device.model.description}")
    >>> print(f"Part Number: {device.model.part_number}")
    >>> print(f"Software Version: v{device.model.software_version // 100}.{device.model.software_version % 100}")
    >>> print(f"Device ID: {device.device_id}")

Quick Start - Listing Updates:
    >>> for update in device.update_files:
    ...     print(f"{update.part_number} v{update.version.major}.{update.version.minor}: {update.description}")

Data Model:
    Device
    ├── model: Model (device hardware/software info)
    ├── device_id: int (unique device identifier)
    ├── data_types: List[DataType] (supported file types)
    ├── update_files: List[UpdateFile] (installed databases/software)
    └── extensions: Any (optional extension data)

    Model
    ├── part_number: str (e.g., "006-B1727-3B")
    ├── software_version: int (e.g., 952 displays as v9.52)
    └── description: str (e.g., "GDU 460")

    UpdateFile
    ├── part_number: str
    ├── version: Version (major and minor components)
    ├── description: str (optional, human-readable name)
    ├── path: str (optional, installation path)
    └── file_name: str (optional, file name)

    DataType
    ├── name: str (e.g., "GPSData", "BaseMaps")
    └── files: List[FileSpec] (supported file specifications)

Usage:
    python3 garmin_device.py                               # Auto-detect SD card and read GarminDevice.xml
    python3 garmin_device.py GarminDevice.xml              # Show device summary
    python3 garmin_device.py GarminDevice.xml --updates    # List installed updates
    python3 garmin_device.py GarminDevice.xml --data-types # List supported data types
    python3 garmin_device.py GarminDevice.xml --verbose    # Show all details
"""

import argparse
import pathlib
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Optional

import sdcard

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
    # Functions
    'read_device',
    'get_system_serial',
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
        software_version: Software version as integer (e.g., 952 displays as v9.52)
        description: Human-readable device description (e.g., "GDU 460")
    """
    part_number: str
    software_version: int
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
        version: Version number with major and minor components
        description: Human-readable description (e.g., "USA-VFR Navigation Data 2510")
        path: Installation path on device (e.g., ".System")
        file_name: File name (e.g., "gmapbmap.img")
    """
    part_number: str
    version: Version
    description: Optional[str] = None
    path: Optional[str] = None
    file_name: Optional[str] = None


@dataclass
class Specification:
    """
    File format specification.

    Attributes:
        identifier: Format identifier (optional, e.g., "http://www.topografix.com/GPX/1/1" or "IMG")
        documentation: URL to format documentation (optional)
    """
    identifier: Optional[str] = None
    documentation: Optional[str] = None


@dataclass
class Location:
    """
    File location on device.

    Attributes:
        file_extension: File extension without dot (required, e.g., "gpx", "img")
        path: Directory path (optional, e.g., "GPX", ".System")
        base_name: Base file name without extension (optional)
    """
    file_extension: str
    path: Optional[str] = None
    base_name: Optional[str] = None


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
        device_id: Unique device identifier (integer, displayed as hex)
        data_types: List of supported data types
        update_files: List of installed update files
        extensions: Extension data (optional)
    """
    model: Model
    device_id: int
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
    if not part_number:
        raise ValueError("Model XML missing required PartNumber element")

    software_version_str = _get_text(model_elem.find(f"{ns}SoftwareVersion"))
    if not software_version_str:
        raise ValueError("Model XML missing required SoftwareVersion element")

    try:
        software_version = int(software_version_str)
    except ValueError as e:
        raise ValueError(f"SoftwareVersion must be a valid integer, got: {software_version_str}") from e

    description = _get_text(model_elem.find(f"{ns}Description"))
    if not description:
        raise ValueError("Model XML missing required Description element")

    return Model(
        part_number=part_number,
        software_version=software_version,
        description=description
    )


def _parse_version(version_elem: ET.Element, ns: str) -> Version:
    """
    Parse Version element.

    Args:
        version_elem: Version XML element
        ns: Namespace prefix

    Returns:
        Version dataclass instance
    """
    major_str = _get_text(version_elem.find(f"{ns}Major"))
    if not major_str:
        raise ValueError("Version XML missing required Major element")

    minor_str = _get_text(version_elem.find(f"{ns}Minor"))
    if not minor_str:
        raise ValueError("Version XML missing required Minor element")

    try:
        major = int(major_str)
        minor = int(minor_str)
    except ValueError as e:
        raise ValueError(f"Version Major/Minor must be valid integers: {e}") from e

    return Version(
        major=major,
        minor=minor
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
    file_extension = _get_text(loc_elem.find(f"{ns}FileExtension"))
    if not file_extension:
        raise ValueError("Location XML missing required FileExtension element")

    path = _get_text(loc_elem.find(f"{ns}Path")) or None
    base_name = _get_text(loc_elem.find(f"{ns}BaseName")) or None

    return Location(
        file_extension=file_extension,
        path=path,
        base_name=base_name
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
    if spec_elem is None:
        raise ValueError("File XML missing required Specification element")
    specification = _parse_specification(spec_elem, ns)

    loc_elem = file_elem.find(f"{ns}Location")
    if loc_elem is None:
        raise ValueError("File XML missing required Location element")
    location = _parse_location(loc_elem, ns)

    transfer_direction = _get_text(file_elem.find(f"{ns}TransferDirection"))
    if not transfer_direction:
        raise ValueError("File XML missing required TransferDirection element")

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
    if not name:
        raise ValueError("DataType XML missing required Name element")

    files = [_parse_file_spec(f, ns) for f in dt_elem.findall(f"{ns}File")]
    if not files:
        raise ValueError(f"DataType '{name}' must have at least one File element")

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
    if not part_number:
        raise ValueError("UpdateFile XML missing required PartNumber element")

    version_elem = uf_elem.find(f"{ns}Version")
    if version_elem is None:
        raise ValueError(f"UpdateFile '{part_number}' missing required Version element")
    version = _parse_version(version_elem, ns)

    description = _get_text(uf_elem.find(f"{ns}Description")) or None
    path = _get_text(uf_elem.find(f"{ns}Path")) or None
    file_name = _get_text(uf_elem.find(f"{ns}FileName")) or None

    return UpdateFile(
        part_number=part_number,
        version=version,
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

    # Parse Id (required) - stored as decimal integer in XML
    device_id_str = _get_text(root.find(f"{ns}Id"))
    if not device_id_str:
        raise ValueError("Device XML missing required Id element")
    try:
        device_id = int(device_id_str)
    except ValueError as e:
        raise ValueError(f"Device Id must be a valid integer, got: {device_id_str}") from e

    # Parse MassStorageMode (optional)
    data_types = []
    update_files = []
    msm_elem = root.find(f"{ns}MassStorageMode")
    if msm_elem is not None:
        # Parse DataType elements (optional)
        data_types = [_parse_data_type(dt, ns) for dt in msm_elem.findall(f"{ns}DataType")]

        # Parse UpdateFile elements (at least one required if MassStorageMode present)
        update_files = [_parse_update_file(uf, ns) for uf in msm_elem.findall(f"{ns}UpdateFile")]
        if not update_files:
            raise ValueError("MassStorageMode must contain at least one UpdateFile element")

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


def read_device(file_path: pathlib.Path) -> Device:
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
    tree = ET.parse(file_path)
    root = tree.getroot()
    return _parse_device(root)


def get_system_serial(file_path: pathlib.Path) -> Optional[int]:
    """
    Get system serial (device ID) from GarminDevice.xml file.

    Extracts the device ID (system serial number) from a GarminDevice.xml file.

    Args:
        file_path: Path to GarminDevice.xml file

    Returns:
        Device ID as integer, or None if file can't be parsed

    Example:
        >>> serial = get_system_serial(pathlib.Path("/Volumes/GARMIN/Garmin/GarminDevice.xml"))
        >>> if serial:
        ...     print(f"System Serial: {serial:#x}")
    """
    try:
        device = read_device(file_path)
        return device.device_id
    except (ET.ParseError, ValueError, OSError):
        # Silently fail if file cannot be read or parsed
        return None


def main() -> None:
    """Command-line interface for reading GarminDevice.xml files."""
    parser = argparse.ArgumentParser(description='Read and display information from GarminDevice.xml files')
    parser.add_argument('file', nargs='?', help='Path to GarminDevice.xml file. If not specified, attempts to auto-detect SD card and use Garmin/GarminDevice.xml')
    parser.add_argument('-s', '--system-serial', action='store_true', help='Extract and display system serial number only')
    parser.add_argument('-u', '--updates', action='store_true', help='List installed update files (databases, software)')
    parser.add_argument('-d', '--data-types', action='store_true', help='List supported data types and file formats')
    parser.add_argument('-v', '--verbose', action='store_true', help='Show all available information')
    args = parser.parse_args()

    # Determine file path: explicit argument or auto-detect SD card
    if args.file:
        file_path = pathlib.Path(args.file)
    else:
        # Try to auto-detect SD card
        sd_mount = sdcard.detect_sd_card()
        if not sd_mount:
            print("Error: No file specified and SD card could not be auto-detected", file=sys.stderr)
            sys.exit(1)
        file_path = pathlib.Path(sd_mount) / "Garmin" / "GarminDevice.xml"

    # Check that file exists
    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    # Read device file
    try:
        device = read_device(file_path)
    except (ET.ParseError, ValueError) as e:
        print(f"Error parsing device file: {e}", file=sys.stderr)
        sys.exit(1)

    # Show system serial only
    if args.system_serial:
        print(f"{device.device_id:#x}")
        sys.exit(0)

    # Default: Show device summary
    if not args.updates and not args.data_types:
        print(f"Device: {device.model.description}")
        print(f"Part Number: {device.model.part_number}")
        print(f"Software Version: v{device.model.software_version // 100}.{device.model.software_version % 100}")
        print(f"Device ID: {device.device_id:#x}")
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
                    version = f"{update.version.major}.{update.version.minor}"
                    print(f"    {update.part_number:20s} v{version:6s} - {update.description}")

            if software:
                print("\n  Software/Firmware:")
                for update in software:
                    version = f"{update.version.major}.{update.version.minor}"
                    desc = update.file_name or update.part_number
                    print(f"    {update.part_number:20s} v{version:6s} - {desc}")

            if other:
                print("\n  Other:")
                for update in other:
                    version = f"{update.version.major}.{update.version.minor}"
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
                    if spec_id:
                        spec_short = spec_id.split('/')[-1] if spec_id.startswith("http") else spec_id
                    else:
                        spec_short = "(no format)"

                    print(f"    {direction:15s} {file_path_str:40s} [{spec_short}]")


if __name__ == '__main__':
    main()
