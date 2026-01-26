#!/usr/bin/env python3
"""
Garmin Flight Plan (FPL) v1 XML File Format Module

This module provides support for reading and writing Garmin Flight Plan files

Quick Start - Reading:
    >>> from fpl import read_fpl
    >>> flight_plan = read_fpl("flight.fpl")
    >>> print(f"Route: {flight_plan.route.route_name}")
    >>> print(f"Waypoints: {len(flight_plan.waypoint_table)}")
    >>> for wp in flight_plan.waypoint_table:
    ...     print(f"  {wp.identifier} ({wp.type}): {wp.lat}, {wp.lon}")

Quick Start - Creating:
    >>> from fpl import *
    >>> from datetime import datetime, timezone
    >>>
    >>> # Create waypoints
    >>> waypoints = [
    ...     create_waypoint("KBLU", 39.274964, -120.709748, WAYPOINT_TYPE_AIRPORT, "K2"),
    ...     create_waypoint("USR001", 39.2, -120.8, comment="MY WAYPOINT"),
    ...     create_waypoint("KAUN", 38.954827, -121.081717, WAYPOINT_TYPE_AIRPORT, "K2"),
    ... ]
    >>>
    >>> # Create route
    >>> route = create_route("KBLU/KAUN", [
    ...     ("KBLU", WAYPOINT_TYPE_AIRPORT, "K2"),
    ...     ("USR001", WAYPOINT_TYPE_USER, ""),
    ...     ("KAUN", WAYPOINT_TYPE_AIRPORT, "K2"),
    ... ], flight_plan_index=1)
    >>>
    >>> # Create flight plan
    >>> flight_plan = create_flight_plan(
    ...     waypoints,
    ...     route,
    ...     created=datetime.now(timezone.utc)
    ... )
    >>>
    >>> # Validate and write
    >>> validate_flight_plan(flight_plan)
    >>> write_fpl(flight_plan, "output.fpl")

Quick Start - Modifying:
    >>> from fpl import read_fpl, write_fpl, get_waypoint
    >>>
    >>> # Read existing flight plan
    >>> fp = read_fpl("flight.fpl")
    >>>
    >>> # Look up a waypoint
    >>> wp = get_waypoint(fp, "KBLU", WAYPOINT_TYPE_AIRPORT, "K2")
    >>> if wp:
    ...     print(f"Found: {wp.identifier} at {wp.lat}, {wp.lon}")
    >>>
    >>> # Modify and write
    >>> write_fpl(fp, "modified.fpl")

Validation:
    The module supports optional validation of all XSD constraints:
    - String patterns (identifiers, country codes, comments, route names)
    - Numeric ranges (latitude, longitude, flight plan index)
    - Enum values (waypoint types)
    - Collection sizes (waypoint table: 1-3000, route points: 0-300)
    - Key/keyref constraints (route points must reference existing waypoints)

    Validation is enabled by default but can be disabled:
    >>> fp = read_fpl("flight.fpl", validate=False)  # Lenient reading
    >>> write_fpl(fp, "output.fpl", validate=False)  # No constraint checking

Constants:
    Waypoint types (for use with create_waypoint and create_route):
    - WAYPOINT_TYPE_USER: "USER WAYPOINT"
    - WAYPOINT_TYPE_AIRPORT: "AIRPORT"
    - WAYPOINT_TYPE_NDB: "NDB"
    - WAYPOINT_TYPE_VOR: "VOR"
    - WAYPOINT_TYPE_INT: "INT"
    - WAYPOINT_TYPE_INT_VRP: "INT-VRP"

Data Model:
    FlightPlan
    ├── waypoint_table: list[Waypoint]
    ├── route: Route (optional)
    ├── created: datetime (optional)
    ├── file_description: str (optional)
    ├── author: Person (optional)
    ├── link: str (optional)
    └── extensions: Any (optional)

    Route
    ├── route_name: str
    ├── flight_plan_index: int (1-98)
    ├── route_points: list[RoutePoint]
    ├── route_description: str (optional)
    └── extensions: Any (optional)

    Waypoint
    ├── identifier: str (1-12 uppercase alphanumerics)
    ├── type: str (one of WAYPOINT_TYPES)
    ├── country_code: str (2 alphanumerics or empty)
    ├── lat: float (-90.0 to 90.0)
    ├── lon: float (-180.0 to 180.0)
    ├── comment: str (1-25 uppercase alphanumerics/spaces/slashes or empty)
    ├── elevation: float (optional, meters)
    ├── waypoint_description: str (optional)
    ├── symbol: str (optional)
    └── extensions: Any (optional)
"""

import pathlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

# Public API
__all__ = [
    # Constants
    'WAYPOINT_TYPE_USER',
    'WAYPOINT_TYPE_AIRPORT',
    'WAYPOINT_TYPE_NDB',
    'WAYPOINT_TYPE_VOR',
    'WAYPOINT_TYPE_INT',
    'WAYPOINT_TYPE_INT_VRP',
    'WAYPOINT_TYPES',
    # Dataclasses
    'Email',
    'Person',
    'Waypoint',
    'RoutePoint',
    'Route',
    'FlightPlan',
    # Primary functions
    'read_fpl',
    'write_fpl',
    # Helper functions
    'create_waypoint',
    'create_route',
    'create_flight_plan',
    'create_flight_plan_from_route_list',
    'get_waypoint',
    'validate_flight_plan',
    # Validation functions
    'validate_identifier',
    'validate_country_code',
    'validate_comment',
    'validate_route_name',
    'validate_latitude',
    'validate_longitude',
    'validate_flight_plan_index',
    'validate_waypoint_type',
]

# Constants (private - implementation details)
_FPL_NAMESPACE = "http://www8.garmin.com/xmlschemas/FlightPlan/v1"

# Waypoint type constants
WAYPOINT_TYPE_USER = "USER WAYPOINT"
WAYPOINT_TYPE_AIRPORT = "AIRPORT"
WAYPOINT_TYPE_NDB = "NDB"
WAYPOINT_TYPE_VOR = "VOR"
WAYPOINT_TYPE_INT = "INT"
WAYPOINT_TYPE_INT_VRP = "INT-VRP"
WAYPOINT_TYPES = frozenset(
    [
        WAYPOINT_TYPE_USER,
        WAYPOINT_TYPE_AIRPORT,
        WAYPOINT_TYPE_NDB,
        WAYPOINT_TYPE_VOR,
        WAYPOINT_TYPE_INT,
        WAYPOINT_TYPE_INT_VRP,
    ]
)

# Validation patterns from XSD
IDENTIFIER_PATTERN = re.compile(r'^[A-Z0-9]{1,12}$')
COUNTRY_CODE_PATTERN = re.compile(r'^([A-Z0-9]{2})?$')
COMMENT_PATTERN = re.compile(r'^([A-Z0-9 /]{1,25})?$')
ROUTE_NAME_PATTERN = re.compile(r'^([A-Z0-9 /]{1,25})?$')

# Security limits
COORDINATE_DECIMAL_PLACES = 6  # 6 decimal places


# Validation functions
def validate_identifier(identifier: str) -> None:
    """
    Validate waypoint identifier.

    Must be 1-12 uppercase alphanumeric characters.

    Args:
        identifier: The identifier to validate

    Raises:
        ValueError: If identifier doesn't match pattern
    """
    if not IDENTIFIER_PATTERN.match(identifier):
        raise ValueError(f"Invalid identifier '{identifier}': must be 1-12 uppercase " f"alphanumeric characters")


def validate_country_code(country_code: str) -> None:
    """
    Validate country code.

    Must be 2 uppercase alphanumeric characters or empty string.

    Args:
        country_code: The country code to validate

    Raises:
        ValueError: If country code doesn't match pattern
    """
    if not COUNTRY_CODE_PATTERN.match(country_code):
        raise ValueError(
            f"Invalid country code '{country_code}': must be 2 uppercase " f"alphanumeric characters or empty string"
        )


def validate_comment(comment: str) -> None:
    """
    Validate waypoint comment.

    Must be 1-25 uppercase alphanumeric characters, spaces, or slashes, or empty.

    Args:
        comment: The comment to validate

    Raises:
        ValueError: If comment doesn't match pattern
    """
    if not COMMENT_PATTERN.match(comment):
        raise ValueError(
            f"Invalid comment '{comment}': must be 1-25 uppercase "
            f"alphanumeric characters, spaces, or slashes, or empty"
        )


def validate_route_name(route_name: str) -> None:
    """
    Validate route name.

    Must be 1-25 uppercase alphanumeric characters, spaces, or slashes, or empty.

    Args:
        route_name: The route name to validate

    Raises:
        ValueError: If route name doesn't match pattern
    """
    if not ROUTE_NAME_PATTERN.match(route_name):
        raise ValueError(
            f"Invalid route name '{route_name}': must be 1-25 uppercase "
            f"alphanumeric characters, spaces, or slashes, or empty"
        )


def validate_latitude(lat: float) -> None:
    """
    Validate latitude value.

    Must be between -90.0 and 90.0 degrees (WGS84, north positive).

    Args:
        lat: The latitude to validate

    Raises:
        ValueError: If latitude is out of range
    """
    if not -90.0 <= lat <= 90.0:
        raise ValueError(f"Invalid latitude {lat}: must be between -90.0 and 90.0")


def validate_longitude(lon: float) -> None:
    """
    Validate longitude value.

    Must be between -180.0 and 180.0 degrees (WGS84, east positive).

    Args:
        lon: The longitude to validate

    Raises:
        ValueError: If longitude is out of range
    """
    if not -180.0 <= lon <= 180.0:
        raise ValueError(f"Invalid longitude {lon}: must be between -180.0 and 180.0")


def validate_flight_plan_index(index: int) -> None:
    """
    Validate flight plan index.

    Must be between 1 and 98 (inclusive).

    Args:
        index: The flight plan index to validate

    Raises:
        ValueError: If index is out of range
    """
    if not 1 <= index <= 98:
        raise ValueError(f"Invalid flight plan index {index}: must be between 1 and 98")


def validate_waypoint_type(waypoint_type: str) -> None:
    """
    Validate waypoint type.

    Must be one of the defined waypoint types.

    Args:
        waypoint_type: The waypoint type to validate

    Raises:
        ValueError: If waypoint type is not recognized
    """
    if waypoint_type not in WAYPOINT_TYPES:
        raise ValueError(
            f"Invalid waypoint type '{waypoint_type}': must be one of " f"{', '.join(sorted(WAYPOINT_TYPES))}"
        )


# Dataclasses
@dataclass
class Email:
    """
    Email address broken into id and domain to prevent harvesting.

    Attributes:
        id: The id part of the email (e.g., "billgates2004")
        domain: The domain part of the email (e.g., "hotmail.com")
    """

    id: str
    domain: str


@dataclass
class Person:
    """
    Author or organization information.

    Attributes:
        author_name: The name of the author or organization
        email: The author's email address
        link: A link to more information (anyURI)
    """

    author_name: Optional[str] = None
    email: Optional[Email] = None
    link: Optional[str] = None


@dataclass
class Waypoint:
    """
    A waypoint in the flight plan.

    Attributes:
        identifier: Waypoint identifier (1-12 uppercase alphanumerics)
        type: Waypoint type (one of WAYPOINT_TYPES)
        country_code: 2-character country code or empty string
        lat: Latitude in decimal degrees (-90.0 to 90.0, WGS84, north positive)
        lon: Longitude in decimal degrees (-180.0 to 180.0, WGS84, east positive)
        comment: Comment (1-25 uppercase alphanumerics/spaces/slashes or empty)
        elevation: Elevation in meters (ignored by panel mount devices)
        waypoint_description: Description (reference only, ignored by device)
        symbol: Waypoint symbol name
        extensions: Extensions element for additional data
    """

    identifier: str
    type: str
    country_code: str
    lat: float
    lon: float
    comment: str
    elevation: Optional[float] = None
    waypoint_description: Optional[str] = None
    symbol: Optional[str] = None
    extensions: Optional[Any] = None


@dataclass
class RoutePoint:
    """
    A reference to a waypoint in the route order.

    Attributes:
        waypoint_identifier: Identifier of the waypoint
        waypoint_type: Type of the waypoint
        waypoint_country_code: Country code of the waypoint
        extensions: Extensions element for additional data
    """

    waypoint_identifier: str
    waypoint_type: str
    waypoint_country_code: str
    extensions: Optional[Any] = None


@dataclass
class Route:
    """
    The flight plan route.

    Attributes:
        route_name: Name of the route (1-25 uppercase alphanumerics/spaces/slashes)
        flight_plan_index: Flight plan index (1-98, default 1)
        route_points: List of route points (0-300)
        route_description: Description (reference only, ignored by device)
        extensions: Extensions element for additional data
    """

    route_name: str
    flight_plan_index: int
    route_points: list[RoutePoint]
    route_description: Optional[str] = None
    extensions: Optional[Any] = None


@dataclass
class FlightPlan:
    """
    A complete Garmin flight plan.

    Attributes:
        waypoint_table: List of waypoints (1-3000)
        created: UTC timestamp of creation
        route: The route
        file_description: File description (reference only, ignored by device)
        author: Author or organization information
        link: A link to more information (anyURI)
        extensions: Extensions element for additional data
    """

    waypoint_table: list[Waypoint]
    created: Optional[datetime] = None
    route: Optional[Route] = None
    file_description: Optional[str] = None
    author: Optional[Person] = None
    link: Optional[str] = None
    extensions: Optional[Any] = None


# XML Reading (Deserialization)


def _ns(tag: str) -> str:
    """
    Add namespace to tag name.

    Args:
        tag: The tag name without namespace

    Returns:
        The tag name with namespace
    """
    return f"{{{_FPL_NAMESPACE}}}{tag}"


def _find_text_optional(elem: ET.Element, tag: str, default: Optional[str] = None) -> Optional[str]:
    """
    Find text content of child element with namespace handling (optional field).

    Args:
        elem: The parent element
        tag: The tag name (without namespace)
        default: Default value if element not found

    Returns:
        The text content or default value (may be None)
    """
    child = elem.find(_ns(tag))
    if child is not None and child.text is not None:
        return child.text
    return default


def _find_text_required(elem: ET.Element, tag: str) -> str:
    """
    Find text content of child element, required to be present.

    Args:
        elem: The parent element
        tag: The tag name (without namespace)

    Returns:
        The text content (never None)

    Raises:
        ValueError: If the element is not found or has no text content
    """
    child = elem.find(_ns(tag))
    if child is None:
        raise ValueError(f"Required element '{tag}' not found")
    if child.text is None:
        # Return empty string for elements like <country-code></country-code>
        return ""
    return child.text


def _parse_email(elem: ET.Element) -> Email:
    """
    Parse an email element.

    Args:
        elem: The email element

    Returns:
        An Email dataclass instance
    """
    email_id = elem.get("id", "")
    domain = elem.get("domain", "")
    return Email(id=email_id, domain=domain)


def _parse_person(elem: ET.Element) -> Person:
    """
    Parse a person element.

    Args:
        elem: The person element

    Returns:
        A Person dataclass instance
    """
    author_name = _find_text_optional(elem, "author-name")
    link = _find_text_optional(elem, "link")

    email_elem = elem.find(_ns("email"))
    email = _parse_email(email_elem) if email_elem is not None else None

    return Person(author_name=author_name, email=email, link=link)


def _parse_waypoint(elem: ET.Element, validate: bool) -> Waypoint:
    """
    Parse a waypoint element.

    Args:
        elem: The waypoint element
        validate: Whether to validate constraints

    Returns:
        A Waypoint dataclass instance

    Raises:
        ValueError: If validation fails
    """
    identifier = _find_text_required(elem, "identifier")
    waypoint_type = _find_text_required(elem, "type")
    country_code = _find_text_required(elem, "country-code")
    lat_str = _find_text_required(elem, "lat")
    lon_str = _find_text_required(elem, "lon")
    comment = _find_text_required(elem, "comment")

    lat = float(lat_str)
    lon = float(lon_str)

    # Optional elements
    elevation_str = _find_text_optional(elem, "elevation")
    elevation = float(elevation_str) if elevation_str is not None else None
    waypoint_description = _find_text_optional(elem, "waypoint-description")
    symbol = _find_text_optional(elem, "symbol")

    # Extensions
    extensions_elem = elem.find(_ns("extensions"))

    if validate:
        validate_identifier(identifier)
        validate_waypoint_type(waypoint_type)
        validate_country_code(country_code)
        validate_latitude(lat)
        validate_longitude(lon)
        validate_comment(comment)

    return Waypoint(
        identifier=identifier,
        type=waypoint_type,
        country_code=country_code,
        lat=lat,
        lon=lon,
        comment=comment,
        elevation=elevation,
        waypoint_description=waypoint_description,
        symbol=symbol,
        extensions=extensions_elem,
    )


def _parse_route_point(elem: ET.Element, validate: bool) -> RoutePoint:
    """
    Parse a route-point element.

    Args:
        elem: The route-point element
        validate: Whether to validate constraints

    Returns:
        A RoutePoint dataclass instance

    Raises:
        ValueError: If validation fails
    """
    waypoint_identifier = _find_text_required(elem, "waypoint-identifier")
    waypoint_type = _find_text_required(elem, "waypoint-type")
    waypoint_country_code = _find_text_required(elem, "waypoint-country-code")

    # Extensions
    extensions_elem = elem.find(_ns("extensions"))

    if validate:
        validate_identifier(waypoint_identifier)
        validate_waypoint_type(waypoint_type)
        validate_country_code(waypoint_country_code)

    return RoutePoint(
        waypoint_identifier=waypoint_identifier,
        waypoint_type=waypoint_type,
        waypoint_country_code=waypoint_country_code,
        extensions=extensions_elem,
    )


def _parse_route(elem: ET.Element, validate: bool) -> Route:
    """
    Parse a route element.

    Args:
        elem: The route element
        validate: Whether to validate constraints

    Returns:
        A Route dataclass instance

    Raises:
        ValueError: If validation fails
    """
    route_name = _find_text_required(elem, "route-name")
    route_description = _find_text_optional(elem, "route-description")
    flight_plan_index_str = _find_text_required(elem, "flight-plan-index")
    flight_plan_index = int(flight_plan_index_str)

    # Parse route points
    route_points = []
    for rp_elem in elem.findall(_ns("route-point")):
        route_points.append(_parse_route_point(rp_elem, validate))

    # Extensions
    extensions_elem = elem.find(_ns("extensions"))

    if validate:
        validate_route_name(route_name)
        validate_flight_plan_index(flight_plan_index)
        if len(route_points) > 300:
            raise ValueError(f"Too many route points: {len(route_points)} (max 300)")

    return Route(
        route_name=route_name,
        flight_plan_index=flight_plan_index,
        route_points=route_points,
        route_description=route_description,
        extensions=extensions_elem,
    )


def _parse_flight_plan(root: ET.Element, validate: bool) -> FlightPlan:
    """
    Parse a flight-plan element.

    Args:
        root: The flight-plan root element
        validate: Whether to validate constraints

    Returns:
        A FlightPlan dataclass instance

    Raises:
        ValueError: If validation fails
    """
    # Optional metadata
    file_description = _find_text_optional(root, "file-description")
    link = _find_text_optional(root, "link")
    created_str = _find_text_optional(root, "created")

    # Parse created timestamp
    created = None
    if created_str:
        created = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
        # Validate timezone is UTC
        utc_offset = created.utcoffset()
        if created.tzinfo is None or utc_offset is None or utc_offset.total_seconds() != 0:
            raise ValueError(f"Timestamp must be in UTC timezone, got: {created_str}")

    # Parse author
    author_elem = root.find(_ns("author"))
    author = _parse_person(author_elem) if author_elem is not None else None

    # Parse waypoint table (required)
    waypoint_table_elem = root.find(_ns("waypoint-table"))
    if waypoint_table_elem is None:
        raise ValueError("Missing required element: waypoint-table")

    waypoints = []
    for wp_elem in waypoint_table_elem.findall(_ns("waypoint")):
        waypoints.append(_parse_waypoint(wp_elem, validate))

    # Parse route (optional)
    route_elem = root.find(_ns("route"))
    route = _parse_route(route_elem, validate) if route_elem is not None else None

    # Extensions
    extensions_elem = root.find(_ns("extensions"))

    if validate:
        if len(waypoints) == 0:
            raise ValueError("Waypoint table must contain at least one waypoint")
        if len(waypoints) > 3000:
            raise ValueError(f"Too many waypoints: {len(waypoints)} (max 3000)")

    return FlightPlan(
        waypoint_table=waypoints,
        created=created,
        route=route,
        file_description=file_description,
        author=author,
        link=link,
        extensions=extensions_elem,
    )


def read_fpl(file_path: pathlib.Path, validate: bool = True) -> FlightPlan:
    """
    Read a Garmin FPL file and return a FlightPlan dataclass.

    Args:
        file_path: Path to the FPL file
        validate: Whether to validate constraints (default: True)

    Returns:
        A FlightPlan dataclass instance

    Raises:
        FileNotFoundError: If the file doesn't exist
        xml.etree.ElementTree.ParseError: If the XML is malformed
        ValueError: If validation fails (when validate=True)

    Example:
        >>> flight_plan = read_fpl("flight.fpl")
        >>> print(f"Route: {flight_plan.route.route_name}")
        >>> print(f"Waypoints: {len(flight_plan.waypoint_table)}")
    """
    # Parse XML file (reading local files, no XXE risk)
    tree = ET.parse(file_path)
    root = tree.getroot()
    return _parse_flight_plan(root, validate)


# XML Writing (Serialization)


def _add_optional_text(parent: ET.Element, tag: str, value: Optional[str]) -> None:
    """
    Add child element with text only if value is not None.

    Args:
        parent: The parent element
        tag: The tag name (without namespace)
        value: The text value (added only if not None)
    """
    if value is not None:
        elem = ET.SubElement(parent, tag)
        elem.text = value


def _create_email_elem(email: Email) -> ET.Element:
    """
    Create an email element.

    Args:
        email: The Email dataclass instance

    Returns:
        An email Element
    """
    elem = ET.Element("email")
    elem.set("id", email.id)
    elem.set("domain", email.domain)
    return elem


def _create_person_elem(person: Person) -> ET.Element:
    """
    Create a person/author element.

    Args:
        person: The Person dataclass instance

    Returns:
        An author Element
    """
    elem = ET.Element("author")
    _add_optional_text(elem, "author-name", person.author_name)
    if person.email is not None:
        elem.append(_create_email_elem(person.email))
    _add_optional_text(elem, "link", person.link)
    return elem


def _create_waypoint_elem(waypoint: Waypoint, validate: bool) -> ET.Element:
    """
    Create a waypoint element.

    Args:
        waypoint: The Waypoint dataclass instance
        validate: Whether to validate constraints

    Returns:
        A waypoint Element

    Raises:
        ValueError: If validation fails
    """
    if validate:
        validate_identifier(waypoint.identifier)
        validate_waypoint_type(waypoint.type)
        validate_country_code(waypoint.country_code)
        validate_latitude(waypoint.lat)
        validate_longitude(waypoint.lon)
        validate_comment(waypoint.comment)

    elem = ET.Element("waypoint")
    ET.SubElement(elem, "identifier").text = waypoint.identifier
    ET.SubElement(elem, "type").text = waypoint.type

    # Use empty string to ensure closing tag for empty elements
    country_elem = ET.SubElement(elem, "country-code")
    country_elem.text = waypoint.country_code if waypoint.country_code else None

    # Format coordinates with controlled precision
    ET.SubElement(elem, "lat").text = f"{waypoint.lat:.{COORDINATE_DECIMAL_PLACES}f}"
    ET.SubElement(elem, "lon").text = f"{waypoint.lon:.{COORDINATE_DECIMAL_PLACES}f}"
    comment_elem = ET.SubElement(elem, "comment")
    comment_elem.text = waypoint.comment if waypoint.comment else None

    if waypoint.elevation is not None:
        ET.SubElement(elem, "elevation").text = str(waypoint.elevation)
    _add_optional_text(elem, "waypoint-description", waypoint.waypoint_description)
    _add_optional_text(elem, "symbol", waypoint.symbol)

    if waypoint.extensions is not None:
        elem.append(waypoint.extensions)

    return elem


def _create_route_point_elem(route_point: RoutePoint, validate: bool) -> ET.Element:
    """
    Create a route-point element.

    Args:
        route_point: The RoutePoint dataclass instance
        validate: Whether to validate constraints

    Returns:
        A route-point Element

    Raises:
        ValueError: If validation fails
    """
    if validate:
        validate_identifier(route_point.waypoint_identifier)
        validate_waypoint_type(route_point.waypoint_type)
        validate_country_code(route_point.waypoint_country_code)

    elem = ET.Element("route-point")
    ET.SubElement(elem, "waypoint-identifier").text = route_point.waypoint_identifier
    ET.SubElement(elem, "waypoint-type").text = route_point.waypoint_type
    country_elem = ET.SubElement(elem, "waypoint-country-code")
    country_elem.text = route_point.waypoint_country_code if route_point.waypoint_country_code else None

    if route_point.extensions is not None:
        elem.append(route_point.extensions)

    return elem


def _create_route_elem(route: Route, validate: bool) -> ET.Element:
    """
    Create a route element.

    Args:
        route: The Route dataclass instance
        validate: Whether to validate constraints

    Returns:
        A route Element

    Raises:
        ValueError: If validation fails
    """
    if validate:
        validate_route_name(route.route_name)
        validate_flight_plan_index(route.flight_plan_index)
        if len(route.route_points) > 300:
            raise ValueError(f"Too many route points: {len(route.route_points)} (max 300)")

    elem = ET.Element("route")
    ET.SubElement(elem, "route-name").text = route.route_name
    _add_optional_text(elem, "route-description", route.route_description)
    ET.SubElement(elem, "flight-plan-index").text = str(route.flight_plan_index)

    for rp in route.route_points:
        elem.append(_create_route_point_elem(rp, validate))

    if route.extensions is not None:
        elem.append(route.extensions)

    return elem


def _create_flight_plan_elem(flight_plan: FlightPlan, validate: bool) -> ET.Element:
    """
    Create a flight-plan element.

    Args:
        flight_plan: The FlightPlan dataclass instance
        validate: Whether to validate constraints

    Returns:
        A flight-plan Element

    Raises:
        ValueError: If validation fails
    """
    if validate:
        if len(flight_plan.waypoint_table) == 0:
            raise ValueError("Waypoint table must contain at least one waypoint")
        if len(flight_plan.waypoint_table) > 3000:
            raise ValueError(f"Too many waypoints: {len(flight_plan.waypoint_table)} (max 3000)")

    elem = ET.Element("flight-plan")
    elem.set("xmlns", _FPL_NAMESPACE)

    _add_optional_text(elem, "file-description", flight_plan.file_description)

    if flight_plan.author is not None:
        elem.append(_create_person_elem(flight_plan.author))

    _add_optional_text(elem, "link", flight_plan.link)

    if flight_plan.created is not None:
        # Validate timezone is UTC when writing
        if validate:
            utc_offset = flight_plan.created.utcoffset()
            if flight_plan.created.tzinfo is None or utc_offset is None or utc_offset.total_seconds() != 0:
                raise ValueError(f"Timestamp must be in UTC timezone, got offset: {flight_plan.created.utcoffset()}")
        created_str = flight_plan.created.isoformat().replace('+00:00', 'Z')
        ET.SubElement(elem, "created").text = created_str

    # Waypoint table
    waypoint_table_elem = ET.SubElement(elem, "waypoint-table")
    for wp in flight_plan.waypoint_table:
        waypoint_table_elem.append(_create_waypoint_elem(wp, validate))

    # Route
    if flight_plan.route is not None:
        elem.append(_create_route_elem(flight_plan.route, validate))

    if flight_plan.extensions is not None:
        elem.append(flight_plan.extensions)

    return elem


def write_fpl(flight_plan: FlightPlan, file_path: pathlib.Path, validate: bool = True, pretty: bool = True) -> None:
    """
    Write a FlightPlan dataclass to a Garmin FPL file.

    Args:
        flight_plan: The FlightPlan dataclass instance
        file_path: Path to write the FPL file
        validate: Whether to validate constraints (default: True)
        pretty: Whether to pretty-print the XML (default: True)

    Raises:
        ValueError: If validation fails (when validate=True)
        PermissionError: If unable to write to the file

    Example:
        >>> flight_plan = create_flight_plan([...], route)
        >>> write_fpl(flight_plan, "output.fpl")
    """
    # Create the XML tree
    root = _create_flight_plan_elem(flight_plan, validate)
    tree = ET.ElementTree(root)

    # Pretty print if requested
    if pretty:
        ET.indent(tree, space="  ")

    # Write to file with XML declaration
    tree.write(
        file_path,
        encoding="utf-8",
        xml_declaration=True,
        short_empty_elements=False,
    )


# Helper Functions and Utilities


def create_waypoint(
    identifier: str,
    lat: float,
    lon: float,
    waypoint_type: str = WAYPOINT_TYPE_USER,
    country_code: str = "",
    comment: str = "",
    elevation: Optional[float] = None,
    waypoint_description: Optional[str] = None,
    symbol: Optional[str] = None,
) -> Waypoint:
    """
    Create a new Waypoint with the given parameters.

    Args:
        identifier: Waypoint identifier (1-12 uppercase alphanumerics)
        lat: Latitude in decimal degrees (-90.0 to 90.0)
        lon: Longitude in decimal degrees (-180.0 to 180.0)
        waypoint_type: Type of waypoint (default: USER WAYPOINT)
        country_code: 2-character country code (default: empty string)
        comment: Comment (default: empty string)
        elevation: Elevation in meters (default: None)
        waypoint_description: Description (default: None)
        symbol: Symbol name (default: None)

    Returns:
        A Waypoint dataclass instance

    Example:
        >>> wp = create_waypoint("KBLU", 39.274964, -120.709748, WAYPOINT_TYPE_AIRPORT, "K2")
        >>> wp = create_waypoint("USR001", 39.2, -120.5, comment="MY WAYPOINT")
    """
    return Waypoint(
        identifier=identifier,
        type=waypoint_type,
        country_code=country_code,
        lat=lat,
        lon=lon,
        comment=comment,
        elevation=elevation,
        waypoint_description=waypoint_description,
        symbol=symbol,
    )


def create_route(
    name: str,
    waypoint_refs: list[tuple[str, str, str]],
    flight_plan_index: int = 1,
    route_description: Optional[str] = None,
) -> Route:
    """
    Create a new Route with the given waypoint references.

    Args:
        name: Route name (1-25 uppercase alphanumerics/spaces/slashes)
        waypoint_refs: List of (identifier, type, country_code) tuples
        flight_plan_index: Flight plan index (1-98, default: 1)
        route_description: Route description (default: None)

    Returns:
        A Route dataclass instance

    Example:
        >>> route = create_route("KBLU/KAUN", [
        ...     ("KBLU", WAYPOINT_TYPE_AIRPORT, "K2"),
        ...     ("KAUN", WAYPOINT_TYPE_AIRPORT, "K2"),
        ... ])
    """
    route_points = [
        RoutePoint(
            waypoint_identifier=identifier,
            waypoint_type=waypoint_type,
            waypoint_country_code=country_code,
        )
        for identifier, waypoint_type, country_code in waypoint_refs
    ]

    return Route(
        route_name=name,
        flight_plan_index=flight_plan_index,
        route_points=route_points,
        route_description=route_description,
    )


def create_flight_plan(
    waypoints: list[Waypoint],
    route: Optional[Route] = None,
    created: Optional[datetime] = None,
    file_description: Optional[str] = None,
    author: Optional[Person] = None,
    link: Optional[str] = None,
) -> FlightPlan:
    """
    Create a new FlightPlan with the given waypoints and optional route.

    Args:
        waypoints: List of waypoints (1-3000)
        route: The route (default: None)
        created: UTC timestamp of creation (default: None)
        file_description: File description (default: None)
        author: Author information (default: None)
        link: Link to more information (default: None)

    Returns:
        A FlightPlan dataclass instance

    Example:
        >>> waypoints = [
        ...     create_waypoint("KBLU", 39.274964, -120.709748, WAYPOINT_TYPE_AIRPORT, "K2"),
        ...     create_waypoint("KAUN", 38.954827, -121.081717, WAYPOINT_TYPE_AIRPORT, "K2"),
        ... ]
        >>> route = create_route("KBLU/KAUN", [
        ...     ("KBLU", WAYPOINT_TYPE_AIRPORT, "K2"),
        ...     ("KAUN", WAYPOINT_TYPE_AIRPORT, "K2"),
        ... ])
        >>> fp = create_flight_plan(waypoints, route)
    """
    return FlightPlan(
        waypoint_table=waypoints,
        route=route,
        created=created,
        file_description=file_description,
        author=author,
        link=link,
    )


def create_flight_plan_from_route_list(
    route_waypoints: list[tuple[str, float, float, str, str]],
    route_name: Optional[str] = None,
    created: Optional[datetime] = None,
) -> FlightPlan:
    """
    Convenience function to create a FlightPlan from a simple list of waypoint data.

    This function simplifies creating flight plans by accepting a simple list format
    commonly used by route planning tools.

    Args:
        route_waypoints: List of (identifier, lat, lon, waypoint_type, country_code) tuples
        route_name: Route name (default: derived from first and last waypoint)
        created: UTC timestamp of creation (default: current time)

    Returns:
        A FlightPlan dataclass instance

    Example:
        >>> route_data = [
        ...     ("KBLU", 39.274964, -120.709748, WAYPOINT_TYPE_AIRPORT, "K2"),
        ...     ("KAUN", 38.954827, -121.081717, WAYPOINT_TYPE_AIRPORT, "K2"),
        ... ]
        >>> fp = create_flight_plan_from_route_list(route_data)
    """
    if not route_waypoints:
        raise ValueError("Route must contain at least one waypoint")

    # Create waypoints
    waypoints = [
        create_waypoint(identifier, lat, lon, waypoint_type, country_code)
        for identifier, lat, lon, waypoint_type, country_code in route_waypoints
    ]

    # Create route references
    route_refs = [
        (identifier, waypoint_type, country_code) for identifier, _, _, waypoint_type, country_code in route_waypoints
    ]

    # Generate route name if not provided
    if route_name is None:
        first_id = route_waypoints[0][0]
        last_id = route_waypoints[-1][0]
        route_name = f"{first_id}/{last_id}"

    # Create route
    route = create_route(route_name, route_refs)

    # Use current time if not provided
    if created is None:
        created = datetime.now(timezone.utc)

    return create_flight_plan(waypoints, route, created)


def get_waypoint(flight_plan: FlightPlan, identifier: str, waypoint_type: str, country_code: str) -> Optional[Waypoint]:
    """
    Find a waypoint in the flight plan by its key.

    The XSD defines a composite key of (identifier, type, country_code).

    Args:
        flight_plan: The FlightPlan to search
        identifier: Waypoint identifier
        waypoint_type: Waypoint type
        country_code: Country code

    Returns:
        The Waypoint if found, None otherwise

    Example:
        >>> wp = get_waypoint(fp, "KBLU", WAYPOINT_TYPE_AIRPORT, "K2")
    """
    for waypoint in flight_plan.waypoint_table:
        if (
            waypoint.identifier == identifier
            and waypoint.type == waypoint_type
            and waypoint.country_code == country_code
        ):
            return waypoint
    return None


def validate_flight_plan(flight_plan: FlightPlan) -> None:
    """
    Validate all constraints including route-waypoint consistency.

    This validates the XSD key/keyref constraint that all route points
    must reference waypoints that exist in the waypoint table.

    Args:
        flight_plan: The FlightPlan to validate

    Raises:
        ValueError: If validation fails

    Example:
        >>> try:
        ...     validate_flight_plan(fp)
        ...     print("Flight plan is valid")
        ... except ValueError as e:
        ...     print(f"Validation error: {e}")
    """
    # Validate waypoint table constraints
    if len(flight_plan.waypoint_table) == 0:
        raise ValueError("Waypoint table must contain at least one waypoint")
    if len(flight_plan.waypoint_table) > 3000:
        raise ValueError(f"Too many waypoints: {len(flight_plan.waypoint_table)} (max 3000)")

    # Build waypoint lookup cache for O(1) lookups (composite key: identifier, type, country_code)
    waypoint_cache = {}
    seen_waypoints = set()

    # Validate each waypoint and build cache
    for waypoint in flight_plan.waypoint_table:
        validate_identifier(waypoint.identifier)
        validate_waypoint_type(waypoint.type)
        validate_country_code(waypoint.country_code)
        validate_latitude(waypoint.lat)
        validate_longitude(waypoint.lon)
        validate_comment(waypoint.comment)

        # Check for duplicate waypoints (XSD composite key uniqueness)
        waypoint_key = (waypoint.identifier, waypoint.type, waypoint.country_code)
        if waypoint_key in seen_waypoints:
            raise ValueError(f"Duplicate waypoint: {waypoint.identifier}/{waypoint.type}/{waypoint.country_code}")
        seen_waypoints.add(waypoint_key)
        waypoint_cache[waypoint_key] = waypoint

    # Validate route if present
    if flight_plan.route is not None:
        validate_route_name(flight_plan.route.route_name)
        validate_flight_plan_index(flight_plan.route.flight_plan_index)

        if len(flight_plan.route.route_points) > 300:
            raise ValueError(f"Too many route points: {len(flight_plan.route.route_points)} (max 300)")

        # Validate key/keyref constraint: route points must reference waypoints
        # Uses O(1) cache lookup instead of O(n) linear search
        for rp in flight_plan.route.route_points:
            validate_identifier(rp.waypoint_identifier)
            validate_waypoint_type(rp.waypoint_type)
            validate_country_code(rp.waypoint_country_code)

            waypoint_key = (rp.waypoint_identifier, rp.waypoint_type, rp.waypoint_country_code)
            if waypoint_key not in waypoint_cache:
                raise ValueError(
                    f"Route point references non-existent waypoint: "
                    f"{rp.waypoint_identifier}/{rp.waypoint_type}/{rp.waypoint_country_code}"
                )
