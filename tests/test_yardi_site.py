from pathlib import Path

from parsers.yardi_site import parse

HTML = (Path(__file__).parent / "sample_yardi_site.html").read_text()


def units():
    return {u["unit"]: u for u in parse(HTML, building="18 Park")}


def test_units_and_beds_by_section():
    u = units()
    # "#" in its own span (1031) isn't matched; everything else is
    assert set(u) == {"PH26", "0906", "0610", "TH2", "2112", "0517"}
    assert u["PH26"]["beds"] == "Studio"
    assert u["0906"]["beds"] == "1 Bedroom"
    assert u["2112"]["beds"] == "1 Bedroom"
    assert u["0517"]["beds"] == "2 Bedrooms"
    assert u["TH2"]["beds"] is None          # no bed count in its section: don't guess


def test_beds_given_for_single_floor_plan_page():
    u = {x["unit"]: x for x in parse(HTML, building="235 Grand", beds="1 Bedroom")}
    assert all(x["beds"] == "1 Bedroom" for x in u.values())
    assert u["2112"]["base_rent"] == 3715


def test_fields():
    u = units()
    assert u["0906"] == {
        "building": "18 Park", "unit": "0906", "beds": "1 Bedroom", "rent": None,
        "base_rent": 3720, "base_rent_max": 4090, "available": "9/25/2026", "sqft": 646,
        "special": None, "floor_plan": "1 bed 1 bath",
    }
    assert u["0610"]["available"] == "Now"
    assert u["2112"]["sqft"] is None and u["2112"]["base_rent"] == 3715   # no Sq. Ft. column
    assert u["TH2"]["sqft"] == 1100


LABELED = """<html><body><h2>1 bed 1 bath</h2><table><tbody>
<tr><td><span class="lbl">Apartment</span> #0906</td>
    <td><span class="lbl">Sq. Ft.</span> 646</td>
    <td><span class="lbl">Rent</span> $3,720.00 to -$4,090.00</td>
    <td><span class="lbl">Date Available</span> 9/25/2026</td><td><a>Apply</a></td></tr>
<tr><td>#0930</td><td><span>Sq.Ft.:</span><span>1,037</span></td><td>$3,725.00</td><td>12/7/2026</td></tr>
<tr><td>#1204</td><td><span class="sr-only">Unit 1204</span> 702</td><td>$3,650.00</td><td>Now</td></tr>
<tr><td>#1510</td><td>655 sq ft</td><td>$3,610.00</td><td>Now</td></tr>
</tbody></table></body></html>"""


def test_sqft_with_hidden_cell_labels():
    u = {x["unit"]: x for x in parse(LABELED, building="18 Park", beds="1 Bedroom")}
    assert u["0906"]["sqft"] == 646
    assert u["0906"]["base_rent"] == 3720 and u["0906"]["available"] == "9/25/2026"
    assert u["0930"]["sqft"] == 1037
    assert u["1204"]["sqft"] == 702        # skips the repeated unit number
    assert u["1510"]["sqft"] == 655


BAY = """<html><body>
<h1>1 BR 1 BA Res 01 &amp; 09: FL 8 - 44</h1>
<p>1 Bed | 1 Bath | Approximately 685 square feet</p>
<div class="unit"><span>Apartment:</span> <span># 30-09</span>
  <span>Starting at: $4,016.00</span> <span>Move-in: 10/5/2026</span> <a>Apply</a></div>
<div class="unit"><span>Apartment:</span> <span># 08-01</span>
  <span>Starting at: $3,796.00</span> <span>Move-in: Available Now</span></div>
</body></html>"""


def test_plan_page_with_one_size_for_all_units():
    u = {x["unit"]: x for x in parse(BAY, building="65 Bay Street", beds="1 Bedroom")}
    assert set(u) == {"30-09", "08-01"}
    assert u["30-09"]["base_rent"] == 4016 and u["30-09"]["available"] == "10/5/2026"
    assert u["08-01"]["available"] == "Now"
    assert u["30-09"]["sqft"] == 685 and u["08-01"]["sqft"] == 685


def test_plan_size_range_is_not_used():
    ranged = BAY.replace("Approximately 685 square feet", "650 - 780 square feet")
    u = {x["unit"]: x for x in parse(ranged, building="65 Bay Street", beds="1 Bedroom")}
    assert u["30-09"]["sqft"] is None
