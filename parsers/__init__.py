"""One parser per site. Each takes the page HTML (plus optional keyword options
from sites.json, like `building`) and returns a list of unit dicts."""
from functools import partial

from . import avalon, newport, rentcafe, yardi_site

PARSERS = {
    "avalon": avalon.parse,
    "newport": newport.parse,
    "rentcafe": rentcafe.parse,
    "yardi_site": yardi_site.parse,
    "blvd": partial(rentcafe.parse, building_names={
        "B401": "BLVD 401",
        "B425": "BLVD 425",
        "B475N": "BLVD 475 North",
        "B475S": "BLVD 475 South",
    }),
}
