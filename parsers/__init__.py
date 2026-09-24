"""One parser per site. Each takes the page HTML and returns a list of unit dicts."""
from functools import partial

from . import newport, rentcafe

PARSERS = {
    "newport": newport.parse,
    "blvd": partial(rentcafe.parse, building_names={
        "B401": "BLVD 401",
        "B425": "BLVD 425",
        "B475N": "BLVD 475 North",
        "B475S": "BLVD 475 South",
    }),
}
