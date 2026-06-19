import math

from kid_events.branches import load_location_book
from kid_events.geo import haversine_miles, radius_miles

MV = (37.3894, -122.0819)
SAN_JOSE = (37.3382, -121.8863)
PALO_ALTO = (37.4419, -122.143)


def test_haversine_zero_and_symmetry():
    assert haversine_miles(*MV, *MV) == 0
    there = haversine_miles(*MV, *SAN_JOSE)
    back = haversine_miles(*SAN_JOSE, *MV)
    assert math.isclose(there, back, rel_tol=1e-9)


def test_haversine_known_distances():
    assert 8 < haversine_miles(*MV, *SAN_JOSE) < 14
    assert 3 < haversine_miles(*MV, *PALO_ALTO) < 8


def test_radius_presets():
    assert radius_miles("mv") == 5.0
    assert radius_miles("far") == 20.0
    assert radius_miles("any") is None
    assert radius_miles("bogus") is None


def test_location_book_resolution():
    book = load_location_book()
    assert book.center_name == "Mountain View"

    lat, lon, city = book.resolve("Morgan Hill Library")
    assert city == "Morgan Hill"
    assert lat is not None and lon is not None

    lat, lon, city = book.resolve("Rinconada Library", default_city="palo alto")
    assert city == "Palo Alto"
    assert (lat, lon) == (book.cities["palo alto"].lat, book.cities["palo alto"].lon)


def test_location_book_online_and_longest_match():
    book = load_location_book()
    assert book.resolve("Online Program", default_city="mountain view") == (None, None, "Online")

    _, _, city = book.resolve("Los Altos Hills Community Room")
    assert city == "Los Altos Hills"

    assert book.resolve("Children's Room", default_city="") == (None, None, "")
