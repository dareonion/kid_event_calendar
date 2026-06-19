from kid_events.ages import (
    audience_name_to_bands,
    child_age_to_bands,
    infer_bands_from_title,
    parse_age_to_months,
)
from kid_events.models import AgeBand


def test_bibliocommons_audience_names_map_cleanly():
    assert audience_name_to_bands("Babies (under 2)") == {AgeBand.INFANT}
    assert audience_name_to_bands("Toddlers (18 mos. to 3 yrs)") == {AgeBand.TODDLER}
    assert audience_name_to_bands("Pre-schoolers (3-5)") == {AgeBand.PRESCHOOL}
    assert audience_name_to_bands("Kids (6-11)") == {AgeBand.SCHOOL_AGE}


def test_libcal_audience_categories_map_cleanly():
    assert audience_name_to_bands("Babies") == {AgeBand.INFANT}
    assert audience_name_to_bands("Toddlers") == {AgeBand.TODDLER}
    assert audience_name_to_bands("Preschoolers") == {AgeBand.PRESCHOOL}
    assert audience_name_to_bands("Children") == {AgeBand.SCHOOL_AGE}
    assert audience_name_to_bands("Tweens") == {AgeBand.TWEEN_TEEN}
    assert audience_name_to_bands("Teens") == {AgeBand.TWEEN_TEEN}
    assert audience_name_to_bands("Families") == {AgeBand.ALL_AGES}
    assert audience_name_to_bands("All Ages") == {AgeBand.ALL_AGES}
    assert audience_name_to_bands("Adults") == {AgeBand.ADULT}


def test_preschool_does_not_collide_with_school_age():
    bands = audience_name_to_bands("Preschool Storytime")
    assert AgeBand.PRESCHOOL in bands
    assert AgeBand.SCHOOL_AGE not in bands


def test_unknown_audience_is_empty():
    assert audience_name_to_bands("Book Club") == set()


def test_child_age_to_bands_always_includes_all_ages():
    assert child_age_to_bands(8) == {AgeBand.INFANT, AgeBand.ALL_AGES}
    assert child_age_to_bands(24) == {AgeBand.TODDLER, AgeBand.ALL_AGES}
    assert child_age_to_bands(48) == {AgeBand.PRESCHOOL, AgeBand.ALL_AGES}
    assert child_age_to_bands(96) == {AgeBand.SCHOOL_AGE, AgeBand.ALL_AGES}


def test_infer_from_title_uses_storytime_and_keywords():
    assert infer_bands_from_title("Baby Storytime") == {
        AgeBand.INFANT,
        AgeBand.TODDLER,
        AgeBand.PRESCHOOL,
    }
    assert infer_bands_from_title("Chess Club") == set()


def test_parse_age_to_months():
    assert parse_age_to_months("8 months") == 8
    assert parse_age_to_months("8mo") == 8
    assert parse_age_to_months("18 months") == 18
    assert parse_age_to_months("2y") == 24
    assert parse_age_to_months("2 years") == 24
    assert parse_age_to_months("3") == 36  # bare number => years
    assert parse_age_to_months("") is None
    assert parse_age_to_months("no age here") is None
