# Getting Started

Welcome to the FPlan project! This guide will help you get started with setting up and running the project.

## Prerequisites

Before you begin, ensure you have met the following requirements:
 - [ ] You have installed a recent version of [Python](https://www.python.org/downloads/).
 - [ ] You have a working internet connection.
 - [ ] You have the following Python dependencies installed, recommend using pip in a venv:
   - `beautifulsoup4` (for NASR downloader)
   - `astar`
   - `rtree`

## Initial Setup

To set up the project's database, you need to:

1. Download current NASR data from FAA:
    ```sh
    python3 nasr.py --current
    ```

2. Build some pre-processed data files from the NASR data, so the planner doesn't have to navigate ZIP and CSV files:
    ```sh
    python3 makedb.py <filename downloaded above>
    ```

# Usage

Try some routes.

The defaults will produce a pretty decent VFR plan with under-100NM legs:
    ```sh
    python3 plan.py KHAF KUAO
    ```

The --direct option is useful to find the shortest way to visit a number of other airports:
    ```sh
    python3 plan.py --direct KLVK KAPC --via KVCB --via KHAF --via KCCR
    ```

The --airway option may include airways in the plan:
    ```sh
    python3 plan.py --airway KMOD KPSP
    ```

## Command line arguments

    ```sh
    python3 plan.py origin destination [options] [routing preferences]
    ```

    origin: Origin airport ICAO code. Mandatory argument.

    destination: Destination airport ICAO code. Mandatory argument.

    --via <waypoint>
        Generated route must include this airport, fix, or navaid. Each via must be specified separately, and they can be in any order. Route planner will determine the shortest route between each via.

    OUTPUT PREFERENCES

    --output-minimal-airway
        Output a condensed flight plan showing only airway entry and exit waypoints.


    ROUTE GENERATION PREFERENCES

    --direct:
        Generate a shortest-path direct flight plan between origin and destination, via any optional vias and exit. No intermediate legs are calculated.

    --airway:
        Generate a flight plan between origin and destination, via any optional vias, considering airways as well as waypoint-to-waypoint legs.

    If --direct or --airway is not specified, generate a flight plan between origin and destination, via any optional vias, with intermediate legs using the following criteria:

    --max-leg-length <distance>:
        Specify the maximum leg length for direct neighbors, in nautical miles. Default is 100.

    WAYPOINT PREFERENCES

    --route-airport [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle airports in the route. Default is 'INCLUDE'.

    --route-balloonport [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle balloonports in the route. Default is 'REJECT'.

    --route-seaplane-base [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle seaplane bases in the route. Default is 'REJECT'.

    --route-gliderport [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle gliderports in the route. Default is 'REJECT'.

    --route-heliport [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle heliports in the route. Default is 'REJECT'.

    --route-ultralight [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle ultralight aerodromes in the route. Default is 'REJECT'.

    --route-vfr-waypoint [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle VFR waypoints in the route. Default is 'INCLUDE'.

    --route-dme [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle DMEs in the route. Default is 'REJECT'.

    --route-ndb [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle NDBs in the route. Default is 'REJECT'.

    --route-ndbdme [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle NDB/DMEs in the route. Default is 'REJECT'.

    --route-vor [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle VORs in the route. Default is 'REJECT'.

    --route-vortac [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle VORTACs in the route. Default is 'REJECT'.

    --route-vordme [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle VOR/DMEs in the route. Default is 'REJECT'.

    AIRWAY PREFERENCES

    --route-airway-victor [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle Victor airways in the route, only when airway routing is enabled. Default is 'PREFER'

    --route-airway-rnav' [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle RNAV (T and Q) airways in the route, only when airway routing is enabled. Default is 'INCLUDE'

    --route-airway-jet [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle Jet airways in the route, only when airway routing is enabled. Default is 'REJECT'

    --route-airway-color [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle colored airways in the route, only when airway routing is enabled. Default is 'REJECT'

    --route-airway-other [PREFER | INCLUDE | AVOID | REJECT]:
        Specify how to handle atlantic, bahama, pacific, and puerto rico airways in the route, only when airway routing is enabled. Default is 'REJECT'

# Development Reference

## Waypoint Types

- **A**: Airport
- **B**: Balloonport
- **C**: Seaplane Base
- **G**: Gliderport
- **H**: Heliport
- **U**: Ultralight

- **CN**: Computer Navigation Fix
- **MR**: Military Reporting Point
- **MW**: Military Waypoint
- **NRS**: NRS Waypoint
- **RADAR**: Radar
- **RP**: Reporting Point
- **VFR**: VFR Waypoint
- **WP**: Waypoint

- **CONSOLAN**: A Low Frequency, Long-Distance NAVAID Used Principally for Transoceanic navigation.
- **DME**: Distance Measuring Equipment only.
- **FAN MARKER**: There are 3 types of EN ROUTE Marker Beacons. FAN MARKER, Low powered FAN MARKERS and Z MARKERS. A FAN MARKER Is used to provide a positive identification of positions at Definite points along the airways.
- **MARINE NDB**: A NON Directional Beacon used primarily for Marine (surface) Navigation.
- **MARINE NDB/DME**: A NON Directional Beacon with associated Distance measuring Equipment; used primarily for Marine (surface) Navigation.
- **NDB**: A NON Directional Beacon
- **NDB/DME**: Non Directional Beacon with associated Distance Measuring Equipment.
- **TACAN**: A Tactical Air Navigation System providing Azimuth and Slant Range Distance.
- **UHF/NDB**: Ultra High Frequency/NON Directional Beacon.
- **VOR**: A VHF OMNI-Directional Range providing Azimuth only.
- **VORTAC**: A Facility consisting of two components, VOR and TACAN, Which provides three individual services: VOR AZIMUTH, TACAN AZIMUTH and TACAN Distance (DME) at one site.
- **VOR/DME**: VHF OMNI-DIRECTIONAL Range with associated Distance Measuring equipment.
- **VOT**: A FAA VOR Test Facility.

## Airway Location

- **A**: Alaska
- **C**: Contiguous U.S.
- **H**: Hawaii

## Airway Designation

- **A**: Amber colored airway
- **AT**: Atlantic airway
- **B**: Blue colored airway
- **BF**: Bahama airway
- **G**: Green colored airway
- **J**: Jet airway
- **PA**: Pacific airway
- **PR**: Puerto Rico airway
- **R**: Red colored airway
- **RN**: RNAV airway (tango and quebec airways)
- **V**: Victor airway