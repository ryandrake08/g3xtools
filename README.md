# G3X Tools

A Python toolset for processing and analyzing Garmin G3X aircraft systems, including data logs, aviation checklists, navigation database updates, and flight planning.

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
- Compatibile with Garmin G3X and G3X Touch displays

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
- Modular design with separate authentication and API modules
- OAuth authentication with automatic token caching using platformdirs
- URL-based file caching with organized directory structure
- Conditional downloads (skip if file already cached)
- Optional progress bars for download and extraction phases
- TAW archive extraction
- Cross-platform volume serial number reading and SD card auto-detection
- Device-specific unlock code generation
- Supports many aviation database types (obstacles, terrain, navigation, charts)
- Automatic SD card detection (FAT32, 8-32GB) when output path not specified
- Automatic device serial number detection from SD card's GarminDevice.xml
- Automatic aircraft data refresh when database updates are available
- Issue selection based on effective date windows

**Usage:**
```bash
# List all G3X systems associated with account and exit. Will print the serial number, product type, and associated aircraft
python3 g3xdata.py -l

# NOTE: The first time g3xdata.py is run, it will launch a web browser to authenticate via Garmin's server and generate an access token.
# NOTE: This access token will expire eventually, and you'll need to re-authenticate in that case:
python3 g3xdata.py -l -L

# List all chart data associated with given G3X system and exit
python3 g3xdata.py -e 60001A2345BC0

# Show detailed chart series information and exit, does not require account login
python3 g3xdata.py -i 2054

# RECOMMENDED: Create SD card image using automatic detection
# This will auto-detect the SD card, read the device serial from GarminDevice.xml, and use cached VSN
python3 g3xdata.py
# Or if you have the cached VSN already:
python3 g3xdata.py -N 1234ABCD

# Show progress bars during download and extraction
python3 g3xdata.py -p
# Combine with verbose output for detailed progress
python3 g3xdata.py -p -v

# Manual mode: Create SD card image for a given G3X system, sdcard at given mount point, using known sdcard serial number
sudo python3 sdcard.py /dev/rdisk2s1 (--> outputs 1234ABCD)
python3 g3xdata.py -s 60001A2345BC0 -o /path/to/sdcard -N 1234ABCD

# Create SD card image for a given G3X system, sdcard at given mount point, using given sdcard block device
sudo python3 g3xdata.py -s 60001A2345BC0 -o /path/to/sdcard -d /dev/sdc1

# Create SD card image for the default (first) G3X system, automatically detecting sdcard path, using known sdcard serial number
python3 g3xdata.py -N 1234ABCD

# Create SD card image for the given G3X system, automatically detecting sdcard path, using known sdcard serial number
python3 g3xdata.py -s 60001A2345BC0 -N 1234ABCD

# Create SD card image for the default (first) G3X system, sdcard at a given mount point, using known sdcard serial number
python3 g3xdata.py -o /path/to/sdcard -N 1234ABCD

# NOTE: Environment variables can be set to specify certain features
export G3X_SYSTEM_SERIAL=60001A2345BC0
export G3X_SDCARD_PATH=/path/to/sdcard
export G3X_SDCARD_SERIAL=1234ABCD
python3 g3xdata.py

# NOTE: Exactly one of: sdcard serial number -N or the sdcard block device -d must be specified. If neither are specified, data will be copied but not installable on G3X device

# Force use of latest issues regardless of effective date (e.g., to get upcoming charts before effective date)
python3 g3xdata.py -U -s 60001A2345BC0 -N 1234ABCD

# (DEBUG only) Include specific series/issue combinations
python3 g3xdata.py -I 2054 2509 -I 2056 25D4

# (DEBUG only) Include custom TAW files
python3 g3xdata.py -W /path/to/custom.taw -W /path/to/other.taw
```

**Automatic Device Detection:**

The tool can automatically detect your G3X system serial number from a mounted SD card:

1. **Auto-detect SD card**: When no output path is specified, the tool searches for mounted FAT32 volumes in the 8-32GB size range
2. **Read device information**: If `Garmin/GarminDevice.xml` exists on the SD card, the tool extracts the system ID (device serial number)
3. **Use cached VSN**: If the SD card's volume serial number (VSN) was previously cached (via `sdcard.py`), it will be used automatically
4. **Select device**: The detected system ID is used to select the appropriate G3X device from your Garmin account

This means in the simplest case, you can just run:
```bash
python3 g3xdata.py
```

The tool will:
- Find your mounted SD card automatically
- Read the device serial from `GarminDevice.xml` on the card
- Use the cached VSN for that card (if available)
- Download and install the appropriate databases for that specific G3X system

**Note**: If you have multiple G3X devices in your account or want to override the auto-detected serial, you can still specify `-s SERIAL` explicitly.

**Issue Selection:**
By default, g3xdata.py selects the most appropriate database issue for each series based on the current date:
- Selects the first issue where today's date falls within the effective window (effectiveAt ≤ now < invalidAt)
- Automatically refreshes aircraft data when any device's `nextExpectedAvdbAvailability` date has passed
- Use `-U/--force-use-latest-issues` to override and always select the latest issue regardless of effective date
- Use `-A/--force-refresh-aircraft` to manually force a refresh of aircraft data from Garmin's servers
```

### g3xfplan.py - Flight Route Planner
Generates flight plans using A* pathfinding with configurable routing preferences.

**Features:**
- VFR and IFR flight planning
- Airway routing support (Victor, RNAV, Jet, Color, Atlantic, etc.)
- Configurable waypoint preferences (airports, VOR, NDB, VFR waypoints, etc.)
- User-defined waypoints with configurable routing preference
- Shortest-path direct routing
- Multi-airport routing with waypoint sequencing
- SkyVector integration for route visualization
- Condensed airway output (entry/exit waypoints only)
- Garmin FPL v1 XML file export for G3X systems

**Usage:**
```bash
# NOTE: Before running g3xfplan.py for the first time, you need fresh airport, navaid, waypoint data.
# This only has to be done once a month to coincide with NASR data availability
python3 nasr.py --current

# Generate VFR plan with default 80NM leg length
python3 g3xfplan.py KHAF KUAO

# Direct routing with multiple via points (shortest path)
# NEW: Multiple waypoints can be specified in one --via flag
python3 g3xfplan.py --direct KLVK KAPC --via KVCB KHAF KCCR

# Old style still works (multiple --via flags)
python3 g3xfplan.py --direct KLVK KAPC --via KVCB --via KHAF --via KCCR

# IFR routing with airways
python3 g3xfplan.py --airway KMOD KPSP

# Custom max leg length
python3 g3xfplan.py KSFO KLAX --max-leg-length 60

# Add user waypoints as routing candidates (PREFER by default)
# NEW: Multiple waypoints can be specified in one --waypoint flag
python3 g3xfplan.py KHAF KUAO --waypoint "USR001,37.5,-122.0" "USR002,38.0,-121.5"

# Old style still works (multiple --waypoint flags)
python3 g3xfplan.py KHAF KUAO --waypoint "USR001,37.5,-122.0" --waypoint "USR002,38.0,-121.5"

# User waypoints with AVOID preference
python3 g3xfplan.py KHAF KUAO --waypoint "USR001,37.5,-122.0" --route-user-waypoint AVOID

# Output to SkyVector
python3 g3xfplan.py KSFO KLAX --output-skyvector

# Condensed airway output (entry/exit only)
python3 g3xfplan.py --airway KMOD KPSP --output-minimal-airway

# Export as Garmin FPL file for G3X
python3 g3xfplan.py KHAF KUAO --output-fpl flight.fpl

# Real-world example: VFR route through Bay Area with multiple waypoints
python3 g3xfplan.py O61 KHAF --via VPMIN VPBCB VPCOY VPBDW VPWFR VPBEB VPCRY VPBBV --output-fpl flight.fpl

# Real-world example: Route with user waypoints
python3 g3xfplan.py KTVL KTRK \
  --waypoint "USR003,39.21,-119.93" "USR004,39.233,-120.032" \
  --via USR003 USR004 \
  --output-fpl flight.fpl
```

**Routing Preferences:**
- **Waypoint Types**: Configure handling for airports, balloonports, seaplane bases, gliderports, heliports, ultralight fields, user waypoints, VFR waypoints, DME, NDB, VOR, VORTAC, VOR/DME
- **Airway Types**: Configure handling for Victor, RNAV (T/Q), Jet, Color, Atlantic, Bahama, Pacific, Puerto Rico airways
- **Preference Levels**: PREFER, INCLUDE (default), AVOID, REJECT

Examples:
```bash
# Prefer VOR waypoints, reject heliports
python3 g3xfplan.py KSFO KLAX --route-vor PREFER --route-heliport REJECT

# Airway routing with preferences
python3 g3xfplan.py --airway KMOD KPSP --route-airway-victor PREFER --route-airway-jet REJECT
```

**User Waypoints:**
User waypoints are custom locations added via `--waypoint ID,LAT,LON` that become available as routing candidates. The route may or may not include them based on the A* pathfinding algorithm. They default to PREFER routing preference but can be configured with `--route-user-waypoint`. In FPL exports, they appear as "USER WAYPOINT" type with empty country code.

## Support Modules

### fpl.py - Flight Plan File Module
Python module for reading and writing Garmin Flight Plan (FPL) v1 XML files with complete XSD schema support.

**Features:**
- Complete implementation of Garmin FPL v1 XML schema
- Type-safe dataclass representation with full type annotations
- Functional API with `read_fpl()`, `write_fpl()`, and helper functions
- Optional validation with descriptive error messages
- Support for all 6 waypoint types (USER WAYPOINT, AIRPORT, NDB, VOR, INT, INT-VRP)
- Round-trip safe (read → write → read produces identical data)
- Zero external dependencies (uses only Python standard library)

**Usage:**
```python
# Read a flight plan file
from fpl import read_fpl, write_fpl
flight_plan = read_fpl("flight.fpl")
print(f"Route: {flight_plan.route.route_name}")
print(f"Waypoints: {len(flight_plan.waypoint_table)}")

# Create a flight plan from scratch
from fpl import *
from datetime import datetime, timezone

waypoints = [
    create_waypoint("KBLU", 39.274964, -120.709748, WAYPOINT_TYPE_AIRPORT, "K2"),
    create_waypoint("USR001", 39.2, -120.8, comment="CUSTOM WAYPOINT"),
    create_waypoint("KAUN", 38.954827, -121.081717, WAYPOINT_TYPE_AIRPORT, "K2"),
]

route = create_route("KBLU/KAUN", [
    ("KBLU", WAYPOINT_TYPE_AIRPORT, "K2"),
    ("USR001", WAYPOINT_TYPE_USER, ""),
    ("KAUN", WAYPOINT_TYPE_AIRPORT, "K2"),
])

flight_plan = create_flight_plan(waypoints, route, created=datetime.now(timezone.utc))

# Validate and write
validate_flight_plan(flight_plan)
write_fpl(flight_plan, "output.fpl")
```

**Public API (29 exports):**
- Primary: `read_fpl()`, `write_fpl()`
- Helpers: `create_waypoint()`, `create_route()`, `create_flight_plan()`, `get_waypoint()`, `validate_flight_plan()`
- Dataclasses: `Email`, `Person`, `Waypoint`, `RoutePoint`, `Route`, `FlightPlan`
- Constants: `WAYPOINT_TYPE_*` (6 types), `WAYPOINT_TYPES`, `FPL_NAMESPACE`
- Validators: 8 validation functions for XSD constraints

**Validation Features:**
- Optional validation (enabled by default, can be disabled)
- String pattern validation (identifiers, country codes, comments, route names)
- Numeric range validation (latitude, longitude, flight plan index)
- Enum validation (waypoint types)
- Collection size validation (1-3000 waypoints, 0-300 route points)
- XSD key/keyref validation (route points must reference existing waypoints)

### garmin_login.py - OAuth Authentication
Handles authentication with Garmin's flight services using browser-based OAuth flow with automatic token caching.

**Usage:**
```bash
# Get access token (opens browser for login if not cached)
python3 garmin_login.py
```

### garmin_api.py - REST API Client
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

### taw.py - TAW Archive Extractor
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

### featunlk.py - Feature Unlock File Generator
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

### sdcard.py - SD Card Detection and Volume Serial Number Reader
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

### nasr.py - NASR Database Generator
Downloads and processes FAA NASR (National Airspace System Resources) data to create optimized databases for flight planning.

**Features:**
- Downloads current or preview NASR data from FAA
- Creates MessagePack database (`nasr.msgpack`) optimized for A* pathfinding
- Optional SQLite/Spatialite database output for GIS tools and external analysis
- Processes waypoints, airways, and navigation data
- Supports specific archive selection by name
- Can output multiple formats in a single run

**Usage:**
```bash
# Download current NASR data and generate default msgpack database
python3 nasr.py --current

# Generate msgpack database with custom filename
python3 nasr.py --current --msgpack custom.msgpack

# Generate SQLite database (all NASR tables)
python3 nasr.py --current --sqlite nasr.db

# Generate SQLite database with spatialite geometry columns
python3 nasr.py --current --sqlite nasr.db --with-geometry

# Generate both msgpack and SQLite in one run
python3 nasr.py --current --msgpack --sqlite nasr.db --with-geometry

# Download preview NASR data
python3 nasr.py --preview

# List available NASR archives
python3 nasr.py --list

# Download specific archive by name
python3 nasr.py --name <name>

# Process existing NASR zip file
python3 nasr.py --filename <file.zip> --sqlite nasr.db
```

**Output Formats:**
- **msgpack** (default): Optimized binary format for g3xfplan.py, contains waypoints, airways, and connections
- **sqlite**: Full NASR database with all tables for external tools and GIS applications
- **spatialite** (--with-geometry): SQLite with geometry columns for spatial queries and GIS integration

**Default msgpack Database Location:**
- **macOS**: `~/Library/Caches/g3xtools/nasr.msgpack`
- **Linux**: `~/.cache/g3xtools/nasr.msgpack`
- **Windows**: `%LOCALAPPDATA%\g3xtools\Cache\nasr.msgpack`

## Installation

The virtual environment is not included in the repository. You must create it yourself:

```bash
# Create virtual environment (first time only)
python3 -m venv env

# Activate the virtual environment
source env/bin/activate  # Unix/Mac
# OR
env\Scripts\activate     # Windows

# Install the project with required dependencies
pip install -e .

# Optional: Install with SD card detection support
pip install -e ".[sdcard]"

# Optional: Install with all optional dependencies for development
pip install -e ".[dev]"
```

### Alternative: Install Dependencies Manually

If you prefer not to install the project as a package, you can install dependencies directly:

```bash
pip install pyyaml requests platformdirs

# Optional: For automatic SD card detection
pip install psutil
```

### Dependencies

- Python 3.9+ required
- **Required:**
  - PyYAML (for g3xchecklist.py)
  - requests (for g3xdata.py)
  - platformdirs (for cross-platform cache directories)
  - beautifulsoup4 (for nasr.py web scraping)
  - astar (for plan.py pathfinding)
  - rtree (for plan.py spatial indexing)
  - msgpack (for nasr.py database serialization)
- **Optional:**
  - **psutil** - Enables automatic SD card detection in g3xdata.py. Without psutil, you must manually specify the output path using `-o` or `G3X_SDCARD_PATH` environment variable.
  - **pywin32** - Required for volume serial number reading on Windows systems
- Standard library modules: csv, struct, zlib, argparse, pathlib, datetime, json, xml

### Using Installed Commands

After installing with `pip install -e .`, the tools are available as commands:

```bash
# Run tools directly by name (no need for "python3 script.py")
g3xlog /path/to/logs -o /output -v
g3xdata -l
g3xchecklist -x checklist.ace -o checklist.yaml
```

Or continue using them as scripts:

```bash
python3 g3xlog.py /path/to/logs -o /output -v
```

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
| 0x24 | `fc_tpc/fc_tpc.dat` |
| 0x25 | `fc_tpc/fc_tpc.fca` |
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

## NASR / g3xfplan.py Waypoint Type Reference

**Airport Types:**
- **A**: Airport
- **B**: Balloonport
- **C**: Seaplane Base
- **G**: Gliderport
- **H**: Heliport
- **U**: Ultralight

**Navigation Fixes:**
- **CN**: Computer Navigation Fix
- **MR**: Military Reporting Point
- **MW**: Military Waypoint
- **NRS**: NRS Waypoint
- **RADAR**: Radar
- **RP**: Reporting Point
- **VFR**: VFR Waypoint
- **WP**: Waypoint

**NAVAID Types:**
- **CONSOLAN**: Low Frequency, Long-Distance NAVAID used principally for transoceanic navigation
- **DME**: Distance Measuring Equipment only
- **FAN MARKER**: EN ROUTE Marker Beacon for positive position identification along airways (includes low powered and Z MARKERS)
- **MARINE NDB**: NON Directional Beacon used primarily for Marine (surface) navigation
- **MARINE NDB/DME**: NON Directional Beacon with associated Distance Measuring Equipment for marine navigation
- **NDB**: NON Directional Beacon
- **NDB/DME**: Non Directional Beacon with associated Distance Measuring Equipment
- **TACAN**: Tactical Air Navigation System providing Azimuth and Slant Range Distance
- **UHF/NDB**: Ultra High Frequency/NON Directional Beacon
- **VOR**: VHF OMNI-Directional Range providing Azimuth only
- **VORTAC**: Combined VOR and TACAN providing VOR Azimuth, TACAN Azimuth and TACAN Distance (DME) at one site
- **VOR/DME**: VHF OMNI-DIRECTIONAL Range with associated Distance Measuring equipment
- **VOT**: FAA VOR Test Facility

### Airway Reference

**Airway Location Codes:**
- **A**: Alaska
- **C**: Contiguous U.S.
- **H**: Hawaii

**Airway Designation Codes:**
- **A**: Amber colored airway
- **AT**: Atlantic airway
- **B**: Blue colored airway
- **BF**: Bahama airway
- **G**: Green colored airway
- **J**: Jet airway
- **PA**: Pacific airway
- **PR**: Puerto Rico airway
- **R**: Red colored airway
- **RN**: RNAV airway (Tango and Quebec airways)
- **V**: Victor airway

## Development

### Environment Variables
- `G3X_SEARCH_PATH`: Default search path for input log files (g3xlog.py, g3xheaders.py)
- `G3X_LOG_PATH`: Default output path for processed logs (g3xlog.py, g3xheaders.py)
- `G3X_SYSTEM_SERIAL`: Default avionics system serial number, e.g., ABC123 (g3xdata.py)
- `G3X_SDCARD_PATH`: Default output path for SD card creation (g3xdata.py)
- `G3X_SDCARD_DEVICE`: Default SD card block device for volume serial number reading (g3xdata.py)
- `G3X_SDCARD_SERIAL`: Default SD card volume serial number in hex format, e.g., A1B2C3D4 (g3xdata.py)
- `G3X_GARMIN_ACCESS_TOKEN`: Default Garmin flygarmin access token for authentication (g3xdata.py)

### Testing

The project includes a test suite using pytest.

#### Running Tests

```bash
# Activate virtual environment first
source env/bin/activate

# Run all tests
pytest

# Run with coverage report
pytest --cov

# Run specific module tests
pytest tests/test_fpl.py
pytest tests/test_g3xdata.py

# Run with verbose output
pytest -v

# Stop on first failure
pytest -x
```

#### Code Quality

The project uses **pre-commit** to manage code quality checks including **ruff** (linting/formatting), **mypy** (type checking), and **vermin** (Python version compatibility):

```bash
# Install dev dependencies (includes pre-commit)
pip install -e ".[dev]"

# Install pre-commit git hooks (runs automatically on commit)
pre-commit install

# Run code quality checks only (fast)
pre-commit run --all-files

# Run ALL checks including tests (recommended before pushing)
./tests/check-all.sh

# Auto-fix formatting issues
ruff format .
ruff check --fix .
```

**Configured Checks:**
- **ruff**: Fast Python linter and formatter (auto-fixes enabled)
- **mypy**: Static type checking with type stubs
- **vermin**: Python 3.9+ compatibility verification
- **trailing-whitespace**: Removes trailing whitespace
- **end-of-file-fixer**: Ensures files end with newline
- **check-yaml**: Validates YAML syntax
- **mixed-line-ending**: Enforces LF line endings

**Recommended Workflow:**
```bash
# During development - runs automatically if hooks installed
git commit

# Before pushing - run full suite
./tests/check-all.sh
```

#### Manual Testing

Basic functionality can be tested without the test suite:

```bash
# Test authentication and API access
python3 garmin_login.py                             # Test authentication
python3 garmin_api.py -t aircraft                   # Test API calls

# Test database discovery
python3 g3xdata.py -l                               # List systems

# Test volume serial number reading (Linux)
sudo python3 sdcard.py /dev/sdc1                    # Replace with actual device

# Test volume serial number reading (Mac)
sudo python3 sdcard.py /dev/rdisk2s1                # Replace with actual device (always use /dev/r*, the raw device)

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
├── pyproject.toml            # Project metadata and dependencies
├── g3xchecklist.py           # Checklist converter
├── g3xdata.py                # Aviation database downloader and SD card creator
├── g3xfplan.py               # Flight route planner
├── g3xheaders.py             # Log structure analyzer
├── g3xlog.py                 # Flight data log processor
├── fpl.py                    # Flight plan file reader/writer (FPL v1 XML)
├── featunlk.py               # Feature unlock file generator
├── garmin_login.py           # OAuth authentication module
├── garmin_api.py             # REST API client module
├── nasr.py                   # NASR database generator
├── sdcard.py                 # SD card detection and volume serial number reader
└── taw.py                    # TAW archive extractor
```

## License

See LICENSE file.

## Disclaimer

This software is unofficial and not affiliated with Garmin. Always verify function and content in actual devices before flight. Checklists created with these tools are not intended to replace official AFM procedures.
Update cards created with these tools are unofficial, and to be used at the user's own risk.

---

## Appendix: Future Plans

### Project-wide TODOs

1. Concurrent downloads
2. Retry logic (urllib3.Retry)
3. Logging framework, rather than passing "verbose" around to functions

### Future Flight Planning Features

- Distinguish between various (T, Q, TK) RNAV airways
- DPs and STARs
- Preferred Routes and Coded Departure Routes
- Airspace-aware routing with airspace avoidance, including special use airspace
- Terrain-aware routing with terrain avoidance
- Obstacle-aware routing with obstacle avoidance
- IFR altitude constraints: MEA, MOCA, and related restrictions
- Figure out FPL file format: Country Codes for non-user waypoints, written by G3X are unknown/proprietary (US: "K2", Canada: "CY")
- G3X coordinates for airports, navaids and waypoints are slightly off from NASR and have precision differences (<100m)
- FPL export: Should we add the ability to set flight plan index?
- FPL export: User waypoint comments?
