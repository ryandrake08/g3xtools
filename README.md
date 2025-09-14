# G3X Tools

A Python toolset for processing and analyzing Garmin G3X aircraft systems, including data logs and aviation checklists.

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
source ./env/bin/activate

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

## Installation

1. **Python Environment:**
   ```bash
   source ./env/bin/activate
   pip install pyyaml  # Required for g3xchecklist.py
   ```

2. **Dependencies:**
   - Python 3.13 (virtual environment in `./env/`)
   - pandas, numpy (for g3xlog.py)
   - PyYAML (for g3xchecklist.py)
   - Standard library modules: csv, struct, zlib, argparse

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

## Development

### Environment Setup
```bash
# Activate virtual environment
source ./env/bin/activate

# Install dependencies
pip install pyyaml pandas numpy
```

### Environment Variables
- `G3X_SEARCH_PATH`: Default search path for input log files
- `G3X_LOG_PATH`: Default output path for processed logs

### Testing
Test the tools with provided example files in `ace_examples/`:
```bash
# Test checklist conversion
python3 g3xchecklist.py -x ace_examples/test.ace -o test.yaml
python3 g3xchecklist.py -c test.yaml -o test_new.ace

# Test log processing
python3 g3xlog.py /path/to/logs -o /output/path -v

# Test header analysis
python3 g3xheaders.py /path/to/logs
```

## File Structure

```
g3xtools/
├── README.md                  # This file
├── g3xlog.py                  # Flight data log processor
├── g3xheaders.py             # Log structure analyzer
├── g3xchecklist.py           # Checklist converter
├── env/                      # Python virtual environment
├── ace/                      # JavaScript checklist editor
│   ├── index.html           # Web interface
│   ├── app.js               # Editor logic
│   ├── style.css            # Styling
│   └── acefile.txt          # ACE format documentation
└── ace_examples/             # Example ACE files
    ├── test.ace
    ├── empty.ace
    └── *.ace
```

## Contributing

When working with this codebase:

1. **Activate Environment**: Always use `source ./env/bin/activate`
2. **Follow Patterns**: Study existing code patterns before implementing
3. **Test Thoroughly**: Verify changes with example files
4. **Document Changes**: Update relevant documentation

## License

See individual files for license information. The JavaScript checklist editor (ace/) is MIT licensed.

## Disclaimer

This software is not affiliated with Garmin. Always verify checklist function and content in actual devices before flight. Checklists created with these tools are not intended to replace official AFM procedures.