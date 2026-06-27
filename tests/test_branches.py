from kid_events.branches import Coord, LocationBook, load_location_book


def test_branch_coord_is_case_and_space_insensitive():
    book = LocationBook(
        center_name="x",
        center=Coord(lat=0, lon=0),
        cities={},
        branches={"miss": {"burnhamthorpe library": Coord(lat=43.6, lon=-79.64)}},
    )
    assert book.branch_coord("miss", "Burnhamthorpe Library").lat == 43.6
    assert book.branch_coord("miss", "  burnhamthorpe library  ").lat == 43.6
    assert book.branch_coord("miss", "Unknown Library") is None
    assert book.branch_coord("other-source", "Burnhamthorpe Library") is None


def test_location_book_loads_with_optional_branches():
    book = load_location_book()
    assert book.center_name and book.cities
    assert isinstance(book.branches, dict)  # optional, defaults to {}
