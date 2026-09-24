"""One parser module per site. Each exposes parse(html) -> list[dict]."""
from . import newport

PARSERS = {
    "newport": newport.parse,
}
