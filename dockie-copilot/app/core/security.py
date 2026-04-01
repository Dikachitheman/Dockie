"""
Security utilities.

All untrusted input should be passed through here before storage or rendering.
We store raw payloads as-is but clean before any downstream use.
"""

import html
import re
from urllib.parse import urlparse

import bleach


# URL schemes safe for outbound links
_SAFE_SCHEMES = {"http", "https"}

# Control characters (non-printable ASCII except tab/newline)
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def escape_html(value: str) -> str:
    """HTML-escape a string for safe rendering."""
    return html.escape(value, quote=True)


def strip_control_chars(value: str) -> str:
    """Remove null bytes and other dangerous control characters."""
    return _CONTROL_CHAR_RE.sub("", value)


def sanitize_text(value: str) -> str:
    """Clean a text field: strip control chars, strip HTML tags."""
    cleaned = strip_control_chars(value)
    # bleach.clean strips all tags by default
    cleaned = bleach.clean(cleaned, tags=[], strip=True)
    return cleaned.strip()


def is_safe_url(url: str) -> bool:
    """Return True only for http/https URLs."""
    try:
        parsed = urlparse(url)
        return parsed.scheme.lower() in _SAFE_SCHEMES
    except Exception:
        return False


def sanitize_url(url: str) -> str | None:
    """Return the URL if safe, else None."""
    return url if is_safe_url(url) else None


def validate_coordinate(value: float, *, lat: bool) -> bool:
    """Validate latitude (-90..90) or longitude (-180..180)."""
    if lat:
        return -90.0 <= value <= 90.0
    return -180.0 <= value <= 180.0


def validate_speed(sog: float) -> bool:
    """Speed over ground: 0..102.2 knots (AIS max)."""
    return 0.0 <= sog <= 102.3


def validate_course(cog: float) -> bool:
    """Course over ground: 0..360."""
    return 0.0 <= cog <= 360.0
