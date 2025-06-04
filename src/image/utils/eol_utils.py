import re
from datetime import (
    datetime, 
    timezone,
)
from pathlib import Path
from typing import (
    Any, 
    Optional, 
    Literal,
)

from ...shared.logs import get_logger

UBUNTU_DISTRO_INFO = "/usr/share/distro-info/ubuntu.csv"
VERSION_ID_REGEX = re.compile(r"^(\d{1,2}\.\d{1,2})$")

# Track EOL strfmt
EOL_TRACK_FMT = "%Y-%m-%dT%H:%M:%SZ"

# Distro Info strfmt
EOL_DISTRO_FMT = "%Y-%m-%d"

logger = get_logger()


def is_track_eol(track_value: dict[str, str], track_name: str | None = None) -> bool:
    """Test if track is EOL, or still valid. Log warning if track_name is provided.

    Args:
        track_value (dict[str, str]): The value of the track, a dictionary containing 'end-of-life' and a iso timestamp.
        track_name (str | None): The name of the track. Defaults to None.
    Returns:
        bool: True if the track is EOL, False otherwise.
    """
    eol_str = track_value.get('end-of-life')

    # Handle situations where EOL is not populated, and assumes that it is EOL
    # This might never happen, but it's a simple check
    if eol_str is None:
        logger.error(f"No EOL provided for {track_name or 'UNNAMED TRACK'}! Assuming EOL is now")
        return True
    
    eol_date = datetime.strptime(eol_str, EOL_TRACK_FMT).replace(tzinfo=timezone.utc)
    is_eol = eol_date < datetime.now(timezone.utc)

    if is_eol:
        logger.warning(f'Removing EOL track "{track_name or 'UNKNOWN TRACK'}", EOL: {eol_date}')

    return is_eol


def get_base_eol(base: str, eol_target: Literal['eol', 'eol-server', 'eol-esm'] = 'eol') -> datetime:
    """Find the EOL of the Ubuntu base image by reading /usr/share/distro-info/ubuntu.csv.

    Args:
        base (str): The version ID of the base image, e.g., "22.04".
        eol_target (Literal['eol', 'eol-server', 'eol-esm']): The EOL target to get (default 'eol')
    Returns:
        datetime: The end-of-life date of the base image.
    Raises:
        ValueError: If the base image is not found in the CSV file. Or the slected EOL path is not populated for base image
    """
    distro_info = Path(UBUNTU_DISTRO_INFO).open(encoding="UTF-8")
    headers = next(distro_info).strip().split(',') # get headers

    # Iterate the rows and zip the headers with the valid distros
    valid_distro: list[dict[str,str]] = [
        dict(zip(headers, row.strip().split(',')))
        for row in distro_info
        if row.startswith(base) # Check that the row starts with base before splitting
    ]

    # If no valid distros are found, raise ValueError and log error
    if not valid_distro:
        raise ValueError(f"Base image {base} not found in {UBUNTU_DISTRO_INFO}")
    
    distro = valid_distro.pop(0)

    if eol_target not in distro:
        raise ValueError(f"Base image {base} does not have {eol_target}")

    eol_date = datetime.strptime(distro[eol_target], EOL_DISTRO_FMT).replace(tzinfo=timezone.utc)
    return eol_date

def generate_base_eol_exceed_warning(tracks_eol_exceed_base_eol: list[dict[str, Any]]) -> tuple[str, str]:
    """Generates markdown table for the tracks that exceed the base image EOL date.

    Args:
        tracks_eol_exceed_base_eol (list[dict[str, Any]]): List of tracks with EOL date exceeding base image's EOL date.
            This list contains dictionaries with keys: 'track', 'base', 'track_eol', and 'base_eol'.
    Returns:
        tuple: A tuple containing the title and text for the warning.
    """
    
    # Set up lazy record generator
    table_records = (
        f"| {build['track']} | {build['base']} | {build['track_eol']} | {build['base_eol']} |" 
        for build in tracks_eol_exceed_base_eol
    )

    title = "Found tracks with EOL date exceeding base image's EOL date"

    # Build body text using implicit string joining
    body = ("Following tracks have an EOL date that exceeds the base image's EOL date:\n"
            "| Track | Base | Track EOL Date | Base EOL Date |\n"
            "|-------|------|----------------|---------------|\n"
            f"{'\n'.join(table_records)}" # Insert records
            "\nPlease check the EOL date of the base image and the track.\n")
    return title, body


def track_eol_exceeds_base_eol(track: str, track_eol: str, base: str | None = None) -> Optional[dict[str, Any]]:
    """Check if the track EOL date exceeds the base image EOL date.

    Args:
        track (str): The name of the track, e.g., "1.0-22.04".
        track_eol (str): The end-of-life date of the track, e.g., "2024-04-30T00:00:00Z".
        base (str | None): The base image name, e.g., "ubuntu:22.04". If None, the base will be inferred from the track name.

    Returns:
        Optional[dict[str, Any]]: Dictionary containing the track name, base image, EOL date, and base image EOL date if the track EOL exceeds the base image EOL date.
        None: If the track EOL date does not exceed the base image EOL date.
    """
    if not base:
        base_version_id = track.split("-")[-1]
        if not VERSION_ID_REGEX.match(base_version_id):
            logger.warning(f"Track-base-EOL validation skipped for aliased track {track}")
            return None
    else:
        base_version_id = base.split(":")[-1]

    base_eol = get_base_eol(base_version_id)
    eol_date = datetime.strptime(track_eol,EOL_TRACK_FMT).replace(tzinfo=timezone.utc)

    if eol_date > base_eol:
        logger.warning(
            f"Track {track} has an EOL date {eol_date} that exceeds the base image EOL date {base_eol}"
        )

        return {
            "track": track,
            "base": f"ubuntu:{base_version_id}",
            "track_eol": eol_date.strftime(EOL_DISTRO_FMT),
            "base_eol": base_eol.strftime(EOL_DISTRO_FMT),
        }

    return None
