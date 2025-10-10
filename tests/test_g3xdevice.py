"""
Tests for g3xdevice.py - Garmin device XML parsing.

Tests cover XML parsing, dataclass creation, and device information extraction.
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

# Import the g3xdevice module
sys.path.insert(0, str(Path(__file__).parent.parent))
import g3xdevice


def create_minimal_device_xml() -> str:
    """Create minimal valid GarminDevice.xml content."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<Device xmlns="http://www.garmin.com/xmlschemas/GarminDevice/v2">
    <Model>
        <PartNumber>006-B1234-00</PartNumber>
        <SoftwareVersion>10.20</SoftwareVersion>
        <Description>GDU 460</Description>
    </Model>
    <Id>ABC123DEF456</Id>
</Device>
"""


def create_full_device_xml() -> str:
    """Create complete GarminDevice.xml with all features."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<Device xmlns="http://www.garmin.com/xmlschemas/GarminDevice/v2">
    <Model>
        <PartNumber>006-B1727-3B</PartNumber>
        <SoftwareVersion>952</SoftwareVersion>
        <Description>GDU 460</Description>
    </Model>
    <Id>60001A2345BC0</Id>
    <MassStorageMode>
        <DataType>
            <Name>GPSData</Name>
            <File>
                <Specification>
                    <Identifier>http://www.topografix.com/GPX/1/1</Identifier>
                    <Documentation>http://www.topografix.com/GPX/1/1/gpx.xsd</Documentation>
                </Specification>
                <Location>
                    <Path>GPX</Path>
                    <FileExtension>gpx</FileExtension>
                </Location>
                <TransferDirection>InputToUnit</TransferDirection>
            </File>
        </DataType>
        <DataType>
            <Name>BaseMaps</Name>
            <File>
                <Specification>
                    <Identifier>IMG</Identifier>
                </Specification>
                <Location>
                    <Path>.System</Path>
                    <BaseName>gmapbmap</BaseName>
                    <FileExtension>img</FileExtension>
                </Location>
                <TransferDirection>InputToUnit</TransferDirection>
            </File>
        </DataType>
        <UpdateFile>
            <PartNumber>006-D3123-10</PartNumber>
            <Version>
                <Major>25</Major>
                <Minor>10</Minor>
            </Version>
            <Description>USA-VFR Navigation Data 2510</Description>
            <Path>.System/AVTN</Path>
            <FileName>nav_dir.gca</FileName>
        </UpdateFile>
        <UpdateFile>
            <PartNumber>006-D4123-00</PartNumber>
            <Version>
                <Major>1</Major>
                <Minor>0</Minor>
            </Version>
            <Description>Terrain Database</Description>
            <Path>.System/AVTN</Path>
            <FileName>terrain.gca</FileName>
        </UpdateFile>
    </MassStorageMode>
</Device>
"""


def test_read_device_minimal(tmp_path):
    """Read minimal valid device XML."""
    xml_file = tmp_path / "GarminDevice.xml"
    xml_file.write_text(create_minimal_device_xml())

    device = g3xdevice.read_device(xml_file)

    assert device.model.part_number == "006-B1234-00"
    assert device.model.software_version == "10.20"
    assert device.model.description == "GDU 460"
    assert device.device_id == "ABC123DEF456"
    assert device.data_types == []
    assert device.update_files == []


def test_read_device_full(tmp_path):
    """Read complete device XML with all features."""
    xml_file = tmp_path / "GarminDevice.xml"
    xml_file.write_text(create_full_device_xml())

    device = g3xdevice.read_device(xml_file)

    # Model
    assert device.model.part_number == "006-B1727-3B"
    assert device.model.software_version == "952"
    assert device.model.description == "GDU 460"

    # Device ID
    assert device.device_id == "60001A2345BC0"

    # Data types
    assert len(device.data_types) == 2

    gps_data = device.data_types[0]
    assert gps_data.name == "GPSData"
    assert len(gps_data.files) == 1
    assert gps_data.files[0].specification.identifier == "http://www.topografix.com/GPX/1/1"
    assert gps_data.files[0].location.path == "GPX"
    assert gps_data.files[0].location.file_extension == "gpx"
    assert gps_data.files[0].transfer_direction == "InputToUnit"

    base_maps = device.data_types[1]
    assert base_maps.name == "BaseMaps"
    assert base_maps.files[0].location.base_name == "gmapbmap"

    # Update files
    assert len(device.update_files) == 2

    nav_data = device.update_files[0]
    assert nav_data.part_number == "006-D3123-10"
    assert nav_data.version_major == 25
    assert nav_data.version_minor == 10
    assert nav_data.description == "USA-VFR Navigation Data 2510"
    assert nav_data.path == ".System/AVTN"
    assert nav_data.file_name == "nav_dir.gca"

    terrain = device.update_files[1]
    assert terrain.part_number == "006-D4123-00"
    assert terrain.version_major == 1
    assert terrain.version_minor == 0


def test_read_device_missing_model(tmp_path):
    """Reject device XML missing required Model element."""
    xml_file = tmp_path / "bad.xml"
    xml_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<Device xmlns="http://www.garmin.com/xmlschemas/GarminDevice/v2">
    <Id>ABC123</Id>
</Device>
""")

    with pytest.raises(ValueError, match="missing required Model element"):
        g3xdevice.read_device(xml_file)


def test_read_device_missing_id(tmp_path):
    """Reject device XML missing required Id element."""
    xml_file = tmp_path / "bad.xml"
    xml_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<Device xmlns="http://www.garmin.com/xmlschemas/GarminDevice/v2">
    <Model>
        <PartNumber>006-B1234-00</PartNumber>
        <SoftwareVersion>10.20</SoftwareVersion>
        <Description>GDU 460</Description>
    </Model>
</Device>
""")

    with pytest.raises(ValueError, match="missing required Id element"):
        g3xdevice.read_device(xml_file)


def test_read_device_malformed_xml(tmp_path):
    """Reject malformed XML."""
    xml_file = tmp_path / "bad.xml"
    xml_file.write_text("<Device><unclosed>")

    with pytest.raises(ET.ParseError):
        g3xdevice.read_device(xml_file)


def test_read_device_nonexistent_file(tmp_path):
    """Handle nonexistent file."""
    xml_file = tmp_path / "does_not_exist.xml"

    with pytest.raises(FileNotFoundError):
        g3xdevice.read_device(xml_file)


def test_model_dataclass():
    """Verify Model dataclass structure."""
    model = g3xdevice.Model(
        part_number="006-B1234-00",
        software_version="10.20",
        description="Test Device"
    )

    assert model.part_number == "006-B1234-00"
    assert model.software_version == "10.20"
    assert model.description == "Test Device"


def test_update_file_dataclass():
    """Verify UpdateFile dataclass structure."""
    update = g3xdevice.UpdateFile(
        part_number="006-D1234-10",
        version_major=25,
        version_minor=10,
        description="Test Database",
        path=".System",
        file_name="test.dat"
    )

    assert update.part_number == "006-D1234-10"
    assert update.version_major == 25
    assert update.version_minor == 10
    assert update.description == "Test Database"
    assert update.path == ".System"
    assert update.file_name == "test.dat"


def test_update_file_optional_fields():
    """Verify UpdateFile optional fields default to None."""
    update = g3xdevice.UpdateFile(
        part_number="006-D1234-10",
        version_major=1,
        version_minor=0
    )

    assert update.description is None
    assert update.path is None
    assert update.file_name is None


def test_specification_dataclass():
    """Verify Specification dataclass structure."""
    spec = g3xdevice.Specification(
        identifier="http://example.com/spec",
        documentation="http://example.com/docs"
    )

    assert spec.identifier == "http://example.com/spec"
    assert spec.documentation == "http://example.com/docs"


def test_location_dataclass():
    """Verify Location dataclass structure."""
    location = g3xdevice.Location(
        path="GPX",
        base_name="waypoints",
        file_extension="gpx"
    )

    assert location.path == "GPX"
    assert location.base_name == "waypoints"
    assert location.file_extension == "gpx"


def test_file_spec_dataclass():
    """Verify FileSpec dataclass structure."""
    spec = g3xdevice.Specification(identifier="GPX")
    location = g3xdevice.Location(path="GPX", file_extension="gpx")

    file_spec = g3xdevice.FileSpec(
        specification=spec,
        location=location,
        transfer_direction="InputToUnit"
    )

    assert file_spec.specification.identifier == "GPX"
    assert file_spec.location.path == "GPX"
    assert file_spec.transfer_direction == "InputToUnit"


def test_data_type_dataclass():
    """Verify DataType dataclass structure."""
    spec = g3xdevice.Specification(identifier="GPX")
    location = g3xdevice.Location(path="GPX")
    file_spec = g3xdevice.FileSpec(spec, location, "InputToUnit")

    data_type = g3xdevice.DataType(
        name="GPSData",
        files=[file_spec]
    )

    assert data_type.name == "GPSData"
    assert len(data_type.files) == 1
    assert data_type.files[0].specification.identifier == "GPX"


def test_device_dataclass():
    """Verify Device dataclass structure."""
    model = g3xdevice.Model("006-B1234-00", "10.20", "Test")
    device = g3xdevice.Device(
        model=model,
        device_id="ABC123",
        data_types=[],
        update_files=[]
    )

    assert device.model.part_number == "006-B1234-00"
    assert device.device_id == "ABC123"
    assert device.data_types == []
    assert device.update_files == []


def test_parse_update_file_without_version(tmp_path):
    """Handle UpdateFile without version element."""
    xml_file = tmp_path / "device.xml"
    xml_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<Device xmlns="http://www.garmin.com/xmlschemas/GarminDevice/v2">
    <Model>
        <PartNumber>006-B1234-00</PartNumber>
        <SoftwareVersion>10.20</SoftwareVersion>
        <Description>Test</Description>
    </Model>
    <Id>ABC123</Id>
    <MassStorageMode>
        <UpdateFile>
            <PartNumber>006-D1234-10</PartNumber>
            <Description>Test File</Description>
        </UpdateFile>
    </MassStorageMode>
</Device>
""")

    device = g3xdevice.read_device(xml_file)

    # Should default to 0.0
    assert len(device.update_files) == 1
    assert device.update_files[0].version_major == 0
    assert device.update_files[0].version_minor == 0


def test_parse_empty_text_elements(tmp_path):
    """Handle empty text elements gracefully."""
    xml_file = tmp_path / "device.xml"
    xml_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<Device xmlns="http://www.garmin.com/xmlschemas/GarminDevice/v2">
    <Model>
        <PartNumber></PartNumber>
        <SoftwareVersion></SoftwareVersion>
        <Description></Description>
    </Model>
    <Id>ABC123</Id>
</Device>
""")

    device = g3xdevice.read_device(xml_file)

    # Empty elements should result in empty strings
    assert device.model.part_number == ""
    assert device.model.software_version == ""
    assert device.model.description == ""


def test_parse_multiple_data_types(tmp_path):
    """Parse device with multiple data types."""
    xml_file = tmp_path / "device.xml"
    xml_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<Device xmlns="http://www.garmin.com/xmlschemas/GarminDevice/v2">
    <Model>
        <PartNumber>006-B1234-00</PartNumber>
        <SoftwareVersion>10.20</SoftwareVersion>
        <Description>Test</Description>
    </Model>
    <Id>ABC123</Id>
    <MassStorageMode>
        <DataType>
            <Name>GPSData</Name>
            <File>
                <Specification><Identifier>GPX</Identifier></Specification>
                <Location><Path>GPX</Path></Location>
                <TransferDirection>InputToUnit</TransferDirection>
            </File>
        </DataType>
        <DataType>
            <Name>Waypoints</Name>
            <File>
                <Specification><Identifier>GPI</Identifier></Specification>
                <Location><Path>POI</Path></Location>
                <TransferDirection>InputToUnit</TransferDirection>
            </File>
        </DataType>
        <DataType>
            <Name>Tracks</Name>
            <File>
                <Specification><Identifier>FIT</Identifier></Specification>
                <Location><Path>Activity</Path></Location>
                <TransferDirection>OutputFromUnit</TransferDirection>
            </File>
        </DataType>
    </MassStorageMode>
</Device>
""")

    device = g3xdevice.read_device(xml_file)

    assert len(device.data_types) == 3
    assert device.data_types[0].name == "GPSData"
    assert device.data_types[1].name == "Waypoints"
    assert device.data_types[2].name == "Tracks"


def test_parse_multiple_files_per_data_type(tmp_path):
    """Parse data type with multiple file specifications."""
    xml_file = tmp_path / "device.xml"
    xml_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<Device xmlns="http://www.garmin.com/xmlschemas/GarminDevice/v2">
    <Model>
        <PartNumber>006-B1234-00</PartNumber>
        <SoftwareVersion>10.20</SoftwareVersion>
        <Description>Test</Description>
    </Model>
    <Id>ABC123</Id>
    <MassStorageMode>
        <DataType>
            <Name>Maps</Name>
            <File>
                <Specification><Identifier>IMG</Identifier></Specification>
                <Location><Path>.System</Path><BaseName>gmapbmap</BaseName><FileExtension>img</FileExtension></Location>
                <TransferDirection>InputToUnit</TransferDirection>
            </File>
            <File>
                <Specification><Identifier>IMG</Identifier></Specification>
                <Location><Path>.System</Path><BaseName>gmapsupp</BaseName><FileExtension>img</FileExtension></Location>
                <TransferDirection>InputToUnit</TransferDirection>
            </File>
        </DataType>
    </MassStorageMode>
</Device>
""")

    device = g3xdevice.read_device(xml_file)

    assert len(device.data_types) == 1
    maps = device.data_types[0]
    assert maps.name == "Maps"
    assert len(maps.files) == 2
    assert maps.files[0].location.base_name == "gmapbmap"
    assert maps.files[1].location.base_name == "gmapsupp"


def test_transfer_directions(tmp_path):
    """Verify different transfer directions are parsed correctly."""
    xml_file = tmp_path / "device.xml"
    xml_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<Device xmlns="http://www.garmin.com/xmlschemas/GarminDevice/v2">
    <Model>
        <PartNumber>006-B1234-00</PartNumber>
        <SoftwareVersion>10.20</SoftwareVersion>
        <Description>Test</Description>
    </Model>
    <Id>ABC123</Id>
    <MassStorageMode>
        <DataType>
            <Name>Input</Name>
            <File>
                <Specification><Identifier>GPX</Identifier></Specification>
                <Location><Path>GPX</Path></Location>
                <TransferDirection>InputToUnit</TransferDirection>
            </File>
        </DataType>
        <DataType>
            <Name>Output</Name>
            <File>
                <Specification><Identifier>FIT</Identifier></Specification>
                <Location><Path>Activity</Path></Location>
                <TransferDirection>OutputFromUnit</TransferDirection>
            </File>
        </DataType>
        <DataType>
            <Name>Bidirectional</Name>
            <File>
                <Specification><Identifier>TCX</Identifier></Specification>
                <Location><Path>Courses</Path></Location>
                <TransferDirection>InputOutput</TransferDirection>
            </File>
        </DataType>
    </MassStorageMode>
</Device>
""")

    device = g3xdevice.read_device(xml_file)

    assert device.data_types[0].files[0].transfer_direction == "InputToUnit"
    assert device.data_types[1].files[0].transfer_direction == "OutputFromUnit"
    assert device.data_types[2].files[0].transfer_direction == "InputOutput"
