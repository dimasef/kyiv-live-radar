"""A device is woken by the region it is IN, not by the deployment's.

The gate used to be one `threat.region != HOME_REGION` return at the top of
evaluate_home_danger. It cannot be a deployment-wide constant any more: a phone
carried to Kharkiv should follow it there while the desktop at home keeps
watching Kyiv, so the question is asked per subscription.
"""

from app.domain.region_lookup import region_at
from app.pipeline.home_push import _follows_region


def _sql(region: str) -> str:
    return str(_follows_region(region).compile(compile_kwargs={"literal_binds": True}))


def test_a_device_with_no_region_follows_the_home_region():
    """Every row predating the column implicitly meant the home region, so NULL
    has to keep meaning that or the upgrade goes silent."""
    sql = _sql("kyiv")
    assert "IS NULL" in sql
    assert "'kyiv'" in sql


def test_a_non_home_region_never_matches_the_null_rows():
    """The inverse of the rule above: an unconfigured device must NOT start
    getting Kharkiv pushes just because it never said where it was."""
    sql = _sql("kharkiv")
    assert "IS NULL" not in sql
    assert "'kharkiv'" in sql


class TestRegionAtDerivesTheDeviceRegion:
    """Where a home point falls is what "which region am I in" means. Uses the
    same committed outlines the map's oblast layer draws."""

    def test_kyiv_city_centre(self):
        assert region_at(50.4501, 30.5234) == "kyiv"

    def test_a_point_in_the_kyiv_oblast_ring(self):
        assert region_at(49.79, 30.11) == "kyiv"  # Біла Церква

    def test_chernihiv(self):
        assert region_at(51.49, 31.29) == "chernihiv"

    def test_kharkiv(self):
        assert region_at(49.99, 36.23) == "kharkiv"

    def test_sumy(self):
        assert region_at(50.91, 34.80) == "sumy"

    def test_dnipro(self):
        assert region_at(48.46, 35.05) == "dnipro"

    def test_an_unwatched_oblast_is_no_region_not_the_home_one(self):
        """Most of the country is unwatched. None must not collapse to 'kyiv',
        or a home in Lviv would be told it is in Kyiv."""
        assert region_at(49.84, 24.03) is None  # Львів
        assert region_at(46.48, 30.73) is None  # Одеса

    def test_a_point_off_the_map_is_none(self):
        assert region_at(0.0, 0.0) is None
