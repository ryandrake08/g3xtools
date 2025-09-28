# G3X Tools

A Python toolset for processing and analyzing Garmin G3X aircraft systems, including data logs, aviation checklists, and navigation database updates.

**NOTE:**
Navigation database functionality heavily based on the work done in https://github.com/dimaryaz/jdmtool

## Tools Overview

### g3xlog.py - Flight Data Log Processor
Processes and categorizes Garmin G3X aircraft data logs into flight types based on operational characteristics.

**Features:**
- Automatically discovers CSV log files from mounted volumes
- Analyzes flight data (oil pressure, ground speed) to categorize sessions
- Organizes logs into subdirectories: `config`, `taxi`, and `flight`
- Preserves file modification times during copying

**Usage:**
```bash
# Activate virtual environment
source env/bin/activate

# Process logs with verbose output
python3 g3xlog.py /path/to/search -o /output/path -v

# Using environment variables
export G3X_SEARCH_PATH=/path/to/search
export G3X_LOG_PATH=/output/path
python3 g3xlog.py -v
```

**Classification Logic:**
- **config**: No oil pressure detected (< 1 PSI) - ground testing/configuration
- **taxi**: Ground operations only (max ground speed < 50kt)
- **flight**: Normal flight operations

### g3xheaders.py - Log Structure Analyzer
Analyzes Garmin G3X data log files to detect structural changes across different software versions.

**Features:**
- Compares column headers and stable keys between consecutive log files
- Identifies new columns, removed columns, and renamed columns
- Reports changes with software version information
- Processes files in chronological order (sorted by basename)

**Usage:**
```bash
# Analyze log structure changes
python3 g3xheaders.py /path/to/logs

# Using environment variable
export G3X_LOG_PATH=/path/to/logs
python3 g3xheaders.py
```

### g3xchecklist.py - Aviation Checklist Converter
Converts Garmin G3X aviation checklist files between binary (.ace) and human-readable YAML formats.

**Features:**
- Bidirectional conversion: ACE ↔ YAML
- Full support for all ACE item types (challenges, responses, warnings, etc.)
- CRC32 validation for file integrity
- Enables version control and collaborative editing of aviation checklists
- Maintains full compatibility with Garmin G3X displays

**Usage:**
```bash
# Extract binary checklist to editable YAML
python3 g3xchecklist.py -x checklist.ace -o checklist.yaml

# Compile edited YAML back to binary for G3X
python3 g3xchecklist.py -c checklist.yaml -o checklist.ace
```

### g3xdata.py - Aviation Database Downloader and SD Card Creator
Downloads current aviation database updates from Garmin's fly.garmin.com service and creates complete SD card images for G3X systems.

**Features:**
- Automatic SD card detection (FAT32, 8-32GB) when output path not specified
- Modular design with separate authentication and API modules
- OAuth authentication with automatic token caching using platformdirs
- URL-based file caching with organized directory structure
- Conditional downloads (skip if file already cached)
- TAW archive extraction for navigation databases
- Cross-platform volume serial number reading and SD card auto-detection
- Device-specific unlock code generation
- Supports all aviation database types (obstacles, terrain, navigation, charts)

**Usage:**
```bash
# List all aircraft and their device IDs
python3 g3xdata.py -l

# Download databases for all devices (to cache)
python3 g3xdata.py

# Create SD card image with automatic SD card detection
python3 g3xdata.py -d DEVICE_ID

# Create SD card image with specified output path
python3 g3xdata.py -d DEVICE_ID -o /path/to/sdcard

# Create SD card image with automatic volume serial number detection
python3 g3xdata.py -d DEVICE_ID -s /dev/rdisk2s1

# Create SD card image with manual volume serial number (no root required)
python3 g3xdata.py -d DEVICE_ID -N A1B2C3D4

# Include specific series/issue combinations
python3 g3xdata.py -d DEVICE_ID -I 2054 2509 -I 2056 25D4

# Include custom TAW files
python3 g3xdata.py -d DEVICE_ID -W /path/to/custom.taw -W /path/to/other.taw

# Force refresh of cached data
python3 g3xdata.py -A -D -F  # Force refresh aircraft, datasets, and file downloads

# Enable CRC checking during feature unlock generation (slower but more reliable)
python3 g3xdata.py -c -d DEVICE_ID

# Verbose output for debugging
python3 g3xdata.py -v -d DEVICE_ID

# Show detailed series information
python3 g3xdata.py -i 2054  # Show details for series ID 2054
```

### Supporting Modules

#### garmin_login.py - OAuth Authentication
Handles authentication with Garmin's flight services using browser-based OAuth flow with automatic token caching.

**Usage:**
```bash
# Get access token (opens browser for login if not cached)
python3 garmin_login.py
```

#### garmin_api.py - REST API Client
Provides clean interface to Garmin's aviation database APIs with comprehensive testing capabilities.

**Usage:**
```bash
# Test aircraft API
python3 garmin_api.py -t aircraft

# Test series API
python3 garmin_api.py -t series --series-id 12345

# Test files API
python3 garmin_api.py -t files --series-id 12345 --issue-name "2024-01"
```

#### taw.py - TAW Archive Extractor
Extracts and analyzes Garmin TAW (navigation database) archive files. Primarily used by g3xdata.py but can be used standalone.

**Features:**
- TAW file analysis and content listing
- Full extraction to directory structures ready for SD card deployment
- Support for multiple Garmin device types (G3X, G500, GPSMAP series)
- Binary archive format parsing with embedded file directory

**Usage:**
```bash
# Extract TAW archive to directory
python3 taw.py archive.taw /output/path

# Show archive contents only (no extraction)
python3 taw.py -i archive.taw

# Verbose extraction with detailed output
python3 taw.py -v archive.taw /output/path
```

#### featunlk.py - Feature Unlock File Generator
Generates feature unlock files (feat_unlk.dat) for Garmin aviation systems. Primarily used by g3xdata.py but can be used standalone.

**Features:**
- Cross-platform CLI with short argument support
- Optional CRC checking during processing
- Supports all Garmin aviation database file types
- Generates device-specific unlock codes

**Usage:**
```bash
# Generate unlock file for navigation data
python3 featunlk.py -o /sdcard -f /sdcard/ldr_sys/avtn_db.bin -r "ldr_sys/avtn_db.bin" -N A1B2C3D4 -S 12345678

# Generate with CRC checking (slower but more reliable)
python3 featunlk.py -c -o /sdcard -f /sdcard/terrain_9as.tdb -r "terrain_9as.tdb" -N A1B2C3D4 -S 12345678

# Show help for all options
python3 featunlk.py --help
```

#### sdcard.py - SD Card Detection and Volume Serial Number Reader
Cross-platform utility for reading volume serial numbers from storage devices and detecting SD card mount points, supporting both Unix-style raw devices and Windows drive letters.

**Features:**
- Automatic SD card detection filtering by FAT32 filesystem and 8-32GB size range
- Cross-platform volume serial number reading (Unix/Windows)
- Platform-specific device path examples
- Used by g3xdata.py for automatic SD card discovery

**Usage:**
```bash
# Unix/Mac (requires sudo for raw device access)
sudo python3 sdcard.py /dev/rdisk2s1

# Windows (no special privileges required)
python3 sdcard.py D:

# Output format: 8-character uppercase hexadecimal (e.g., A1B2C3D4)
```

## Installation

1. **Python Environment:**
   ```bash
   source env/bin/activate
   pip install pyyaml requests platformdirs
   ```

2. **Dependencies:**
   - Python 3.13 (virtual environment in `./env/`)
   - PyYAML (for g3xchecklist.py)
   - requests (for g3xdata.py)
   - platformdirs (for cross-platform cache directories)
   - pywin32 (for sdcard.py on Windows - optional)
   - Standard library modules: csv, struct, zlib, argparse, pathlib, datetime, json

## YAML Checklist Format Specification

The YAML format provides a hierarchical structure for aviation checklists that maps directly to the ACE binary format.

### Structure Overview
```yaml
metadata:          # File metadata
defaults:          # Default display settings
groups:            # Array of checklist groups
  - name: "..."    # Group name
    checklists:    # Array of checklists within group
      - name: "..." # Checklist name
        items:     # Array of checklist items
          - type: "..." # Item type and properties
```

### Complete YAML Schema

```yaml
metadata:
  name: "string"                           # Checklist file name
  aircraft_make_model: "string"            # Aircraft make and model
  aircraft_information: "string"           # Aircraft-specific identification
  manufacturer_identification: "string"    # Manufacturer information
  copyright_information: "string"          # Copyright notice

defaults:
  group: integer                           # Default group index (0-based)
  checklist: integer                       # Default checklist index (0-based)

groups:
  - name: "string"                         # Group display name
    checklists:
      - name: "string"                     # Checklist display name
        items:
          # Blank line item
          - type: blank_line

          # Challenge/Response item (pilot action with expected response)
          - type: challenge_response
            text: "string"                 # Challenge text
            response: "string"             # Expected response text
            justification: "left|indent_1|indent_2|indent_3|indent_4"

          # Challenge only item (pilot action, no specific response)
          - type: challenge
            text: "string"                 # Challenge text
            justification: "left|indent_1|indent_2|indent_3|indent_4"

          # Plain text item
          - type: plain_text
            text: "string"                 # Display text
            justification: "left|indent_1|indent_2|indent_3|indent_4|center"

          # Note item (informational)
          - type: note
            text: "string"                 # Note text
            justification: "left|indent_1|indent_2|indent_3|indent_4|center"

          # Subtitle item (section header)
          - type: subtitle
            text: "string"                 # Subtitle text
            justification: "left|indent_1|indent_2|indent_3|indent_4|center"

          # Warning item (important safety information)
          - type: warning
            text: "string"                 # Warning text
            justification: "left|indent_1|indent_2|indent_3|indent_4|center"

          # Caution item (important operational information)
          - type: caution
            text: "string"                 # Caution text
            justification: "left|indent_1|indent_2|indent_3|indent_4|center"
```

### Item Types

| Type | Description | Text Required | Response | Justification Options |
|------|-------------|---------------|----------|----------------------|
| `blank_line` | Empty line for spacing | No | No | N/A |
| `challenge_response` | Pilot action with expected response | Yes | Yes | left, indent_1-4 |
| `challenge` | Pilot action without specific response | Yes | No | left, indent_1-4 |
| `plain_text` | General text display | Yes | No | left, indent_1-4, center |
| `note` | Informational note | Yes | No | left, indent_1-4, center |
| `subtitle` | Section heading | Yes | No | left, indent_1-4, center |
| `warning` | Safety warning | Yes | No | left, indent_1-4, center |
| `caution` | Operational caution | Yes | No | left, indent_1-4, center |

### Justification Values

- `left` - Left-aligned text
- `indent_1` - Indented 1 level
- `indent_2` - Indented 2 levels
- `indent_3` - Indented 3 levels
- `indent_4` - Indented 4 levels
- `center` - Center-aligned text (not available for challenge types)

### Example YAML File

```yaml
metadata:
  name: "Pre-Flight Checklist"
  aircraft_make_model: "Cessna 172"
  aircraft_information: "N12345"
  manufacturer_identification: "Cessna Aircraft Company"
  copyright_information: "Copyright 2024"

defaults:
  group: 0
  checklist: 0

groups:
  - name: "Pre-Flight"
    checklists:
      - name: "Exterior Inspection"
        items:
          - type: subtitle
            text: "EXTERIOR INSPECTION"
            justification: center

          - type: challenge_response
            text: "Aircraft Documents"
            response: "ABOARD AND CURRENT"
            justification: left

          - type: challenge
            text: "Fuel Quantity"
            justification: left

          - type: warning
            text: "ENSURE PROP AREA CLEAR"
            justification: center

          - type: blank_line

          - type: note
            text: "Check for fuel contamination"
            justification: indent_1

      - name: "Interior Setup"
        items:
          - type: challenge_response
            text: "Master Switch"
            response: "ON"
            justification: left

          - type: caution
            text: "Check all circuit breakers"
            justification: left
```

## ACE Binary Format Specification

The ACE format is Garmin's proprietary binary format for aviation checklists used by G3X and G3X Touch displays.

### File Structure Overview

```
┌─────────────────┐
│     Header      │ 10 bytes: File signature, format version, defaults
├─────────────────┤
│    Metadata     │ 5 strings: File properties (CRLF terminated)
├─────────────────┤
│    Content      │ Variable: Checklist structure and items
├─────────────────┤
│   END Marker    │ 5 bytes: "END" + CRLF
├─────────────────┤
│     Footer      │ 4 bytes: CRC32 checksum
└─────────────────┘
```

### Header Format (10 bytes)

| Offset | Size | Description | Value |
|--------|------|-------------|-------|
| 0x00 | 4 bytes | File signature | `f0 f0 f0 f0` (fixed) |
| 0x04 | 1 byte | File format revision | `00` (always 0) |
| 0x05 | 1 byte | Unknown field | `01` (always 1) |
| 0x06 | 1 byte | Default group index | `0x00-0xFF` |
| 0x07 | 1 byte | Default checklist index | `0x00-0xFF` |
| 0x08 | 2 bytes | Field separator | `0d 0a` (CRLF) |

### Metadata Section (5 strings)

Each string is ISO-8859-1 encoded and terminated with CRLF (`0d 0a`):

1. Checklist file name
2. Aircraft make and model
3. Aircraft information
4. Manufacturer identification
5. Copyright information

### Content Section Format

Content uses ISO-8859-1 encoding with CRLF line terminators. Each line represents either a structural element or checklist item.

#### Structural Elements

| Code | Format | Description |
|------|--------|-------------|
| `<` | `3c just string 0d 0a` | Begin Group |
| `>` | `3e 0d 0a` | End Group |
| `(` | `28 just string 0d 0a` | Begin Checklist |
| `)` | `29 0d 0a` | End Checklist |

#### Item Types

| Code | ASCII | Format | Description |
|------|-------|--------|-------------|
| `r` | 0x72 | `72 just cstring 7e rstring 0d 0a` | Challenge/Response |
| `c` | 0x63 | `63 just string 0d 0a` | Challenge |
| `p` | 0x70 | `70 just string 0d 0a` | Plain Text |
| `n` | 0x6e | `6e just string 0d 0a` | Note |
| `t` | 0x74 | `74 just string 0d 0a` | Subtitle |
| `w` | 0x77 | `77 just string 0d 0a` | Warning |
| `a` | 0x61 | `61 just string 0d 0a` | Caution |
| (empty) | | `0d 0a` | Blank Line |

#### Justification Codes

| Code | ASCII | Description |
|------|-------|-------------|
| `0` | 0x30 | Left Justified |
| `1` | 0x31 | Indent 1 Level |
| `2` | 0x32 | Indent 2 Levels |
| `3` | 0x33 | Indent 3 Levels |
| `4` | 0x34 | Indent 4 Levels |
| `c` | 0x63 | Center (text types only) |

#### Challenge/Response Format

For challenge/response items, the format is:
```
r{just}{challenge_text}~{response_text}
```

The tilde (`~`, 0x7e) separates challenge and response text.

### Footer Section

#### END Marker (5 bytes)
```
45 4e 44 0d 0a  ("END" + CRLF)
```

#### CRC32 Checksum (4 bytes)
- 32-bit CRC32 of entire payload (header + content)
- Ones complement of calculated CRC
- Little-endian byte order
- Calculated using standard CRC32 polynomial (0xEDB88320)

### Example Binary Structure

```
f0 f0 f0 f0 00 01 00 00 0d 0a          # Header
54 65 73 74 20 43 68 65 63 6b 6c 69    # "Test Checklist" + CRLF
73 74 0d 0a
43 65 73 73 6e 61 20 31 37 32 0d 0a    # "Cessna 172" + CRLF
...                                     # Other metadata strings
3c 30 50 72 65 2d 46 6c 69 67 68 74    # "<0Pre-Flight" + CRLF
0d 0a
28 30 45 78 74 65 72 69 6f 72 0d 0a    # "(0Exterior" + CRLF
72 30 46 75 65 6c 20 51 75 61 6e 74    # "r0Fuel Quantity~CHECK" + CRLF
69 74 79 7e 43 48 45 43 4b 0d 0a
29 0d 0a                               # ")" + CRLF (end checklist)
3e 0d 0a                               # ">" + CRLF (end group)
45 4e 44 0d 0a                         # "END" + CRLF
xx xx xx xx                            # CRC32 (4 bytes, little-endian)
```

### File Validation

1. **Signature Check**: First 4 bytes must be `f0 f0 f0 f0`
2. **Format Version**: Byte 4 should be `00`
3. **END Marker**: Must appear before CRC footer
4. **CRC Validation**: Calculate CRC32 of header+content, compare with footer
5. **Structure Validation**: Groups and checklists must be properly nested

### Encoding Limitations

- Character encoding: ISO-8859-1 only
- Maximum file size: Limited by 32-bit CRC
- Text length: No explicit limits, but practical limits apply
- Nesting: Groups contain checklists; checklists contain items (no deeper nesting)

## TAW Archive Format Specification

TAW (archive) files contain Garmin navigation database information for aviation systems. The format consists of a header, metadata, and multiple data regions.

### File Structure Overview

```
┌─────────────────┐
│     Header      │ 5 bytes: Magic signature, either "pWa.d" or "wAt.d"
├─────────────────┤
│   Separator     │ 13 bytes: Fixed separator sequence
├─────────────────┤
│    SQA Data     │ 25 bytes: Unknown
├─────────────────┤
│  Metadata Len   │ 4 bytes: Length of metadata section
├─────────────────┤
│   Section 'F'   │ 1 byte: Metadata signifier
├─────────────────┤
│    Metadata     │ Variable: Database type and info
├─────────────────┤
│    Padding      │ 4 bytes: Padding
├─────────────────┤
│   Section 'R'   │ 1 byte: Region section marker
├─────────────────┤
│   TAW Magic     │ 5 bytes: "KpGrd"
├─────────────────┤
│   Separator     │ 13 bytes: Fixed separator sequence
├─────────────────┤
│    SQA Data     │ 25 bytes: Unknown
├─────────────────┤
│    Regions      │ Variable: Multiple data regions
└─────────────────┘
```

### Header Format

| Offset | Size | Description | Values |
|--------|------|-------------|--------|
| 0x00 | 5 bytes | Magic signature | `pWa.d` or `wAt.d` |
| 0x05 | 13 bytes | Separator | `00 02 00 00 00 44 64 00 1b 00 00 00 41 c8 00` |
| 0x12 | 25 bytes | SQA data 1 | Null-terminated strings |
| 0x2B | 4 bytes | Metadata length | Little-endian integer |
| 0x2F | 1 byte | Section marker | `F` (0x46) |
| 0x30 | Variable | Metadata | Database information |
| 0x30+len | 4 bytes | Padding | Unknown/padding bytes |
| Next | 1 byte | Section marker | `R` (0x52) |
| Next+1 | 5 bytes | TAW magic | `KpGrd` |
| Next+6 | 13 bytes | Separator | Same as offset 0x05 |
| Next+19 | 25 bytes | SQA data 2 | Null-terminated strings |

### Metadata Section Format

The metadata section contains database information in a structured format:

| Offset | Size | Description |
|--------|------|-------------|
| 0x00 | 2 bytes | Database type ID (little-endian) |
| 0x02 | 1 byte | Format variant (0x00 or other) |
| 0x03 | Variable | Format-specific data |

#### Format Variant 0x00

| Offset | Size | Description |
|--------|------|-------------|
| 0x03 | 5 bytes | Reserved |
| 0x08 | 1 byte | Year |
| 0x09 | 3 bytes | Reserved |
| 0x0C | 1 byte | Cycle |
| 0x0D | 3 bytes | Reserved |
| 0x10 | Variable | Text data (3 null-terminated strings) |

#### Other Format Variants

| Offset | Size | Description |
|--------|------|-------------|
| 0x03 | 1 byte | Reserved |
| 0x04 | 1 byte | Year |
| 0x05 | 1 byte | Reserved |
| 0x06 | 1 byte | Cycle |
| 0x07 | 1 byte | Reserved |
| 0x08 | Variable | Text data (3 null-terminated strings) |

#### Text Data Format

The text data consists of three null-terminated strings:
1. **Avionics**: Target avionics system
2. **Coverage**: Geographic coverage area
3. **Type**: Database type description

### Region Section Format

Each region contains:

| Offset | Size | Description |
|--------|------|-------------|
| 0x00 | 4 bytes | Section size (little-endian) |
| 0x04 | 1 byte | Section type ('R' = region, 'S' = end) |
| 0x05 | 2 bytes | Region ID (little-endian) |
| 0x07 | 4 bytes | Unknown field |
| 0x0B | 4 bytes | Data size (little-endian) |
| 0x0F | Variable | Region data |

### Known Region IDs

| ID | Path |
|----|------|
| 0x01 | `ldr_sys/avtn_db.bin` |
| 0x02 | `ldr_sys/nav_db2.bin` |
| 0x03 | `bmap.bin` |
| 0x04 | `nav.bin` |
| 0x05 | `bmap2.bin` |
| 0x0A | `safetaxi.bin` |
| 0x0B | `safetaxi2.gca` |
| 0x14 | `fc_tpc/fc_tpc.dat` |
| 0x1A | `rasters/rasters.xml` |
| 0x21 | `terrain.tdb` |
| 0x22 | `terrain_9as.tdb` |
| 0x23 | `trn.dat` |
| 0x24 | `FCharts.dat` |
| 0x25 | `Fcharts.fca` |
| 0x26 | `standard.odb` |
| 0x27 | `terrain.odb` |
| 0x28 | `terrain.adb` |
| 0x32 | `.System/AVTN/avtn_db.bin` |
| 0x33 | `Poi/air_sport.gpi` |
| 0x35 | `.System/AVTN/Obstacle.odb` |
| 0x36 | `.System/AVTN/safetaxi.img` |
| 0x39 | `.System/AVTN/FliteCharts/fc_tpc.dat` |
| 0x3A | `.System/AVTN/FliteCharts/fc_tpc.fca` |
| 0x4C | `fbo.gpi` |
| 0x4E | `apt_dir.gca` |
| 0x4F | `air_sport.gpi` |

### Database Types

| ID | Type |
|----|------|
| 0x0091 | GPSMAP 196 |
| 0x00BF | Gx000 |
| 0x0104 | GPSMAP 296 |
| 0x0190 | G500 |
| 0x01F2 | G500H/GPSx75 |
| 0x0253 | GPSMAP 496 |
| 0x0294 | AERA 660 |
| 0x02E9 | GPSMAP 696 |
| 0x02EA | G3X |
| 0x02F0 | GPS175 |
| 0x0402 | GtnXi |
| 0x0465 | GI275 |
| 0x0618 | AERA 760 |
| 0x06BF | G3X Touch |
| 0x0738 | GTR2X5 |
| 0x07DC | GTXi |

## Feature Unlock (feat_unlk.dat) Format Specification

The feat_unlk.dat file activates database features on Garmin aviation systems by providing unlock codes tied to specific SD card serial numbers and aircraft device IDs.

### File Structure Overview

For now, see featunlk.py for this information.

## Development

### Environment Setup
```bash
# Activate virtual environment
source env/binactivate

# Install dependencies
pip install pyyaml requests platformdirs
```

### Environment Variables
- `G3X_SEARCH_PATH`: Default search path for input log files
- `G3X_LOG_PATH`: Default output path for processed logs

### Testing
Basic functionality tests:
```bash
# Test authentication and API access
python3 garmin_login.py                             # Test authentication
python3 garmin_api.py -t aircraft                   # Test API calls

# Test database discovery
python3 g3xdata.py -l                               # List aircraft and devices

# Test volume serial number reading (Unix/Mac)
sudo python3 sdcard.py /dev/rdisk2s1                # Replace with actual device

# Test volume serial number reading (Windows)
python3 sdcard.py D:                                # Replace with actual drive

# Test log processing (requires actual G3X log files)
python3 g3xlog.py /path/to/logs -o /output/path -v

# Test header analysis (requires actual G3X log files)
python3 g3xheaders.py /path/to/logs
```

## File Structure

```
g3xtools/
├── README.md                 # This file
├── g3xlog.py                 # Flight data log processor
├── g3xheaders.py             # Log structure analyzer
├── g3xchecklist.py           # Checklist converter
├── g3xdata.py                # Aviation database downloader and SD card creator
├── featunlk.py               # Feature unlock file generator
├── garmin_login.py           # OAuth authentication module
├── garmin_api.py             # REST API client module
├── taw.py                    # TAW archive extractor
└── sdcard.py                 # SD card detection and volume serial number reader
```

## License

See LICENSE file.

## Disclaimer

This software is not affiliated with Garmin. Always verify function and content in actual devices before flight. Checklists created with these tools are not intended to replace official AFM procedures.
Update cards created with these tools are unofficial, and to be used at the users's own risk.