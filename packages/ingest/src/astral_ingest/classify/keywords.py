"""Pass 1: keyword-based category classification using pre-compiled regex."""

from __future__ import annotations

import re

from astral_core import SpaceCategory

# Pre-compiled regex patterns with word boundaries for each category.
# Checks title first (stronger signal), then first 2000 chars of body.
_CATEGORY_PATTERNS: dict[SpaceCategory, re.Pattern[str]] = {
    SpaceCategory.LAUNCH_VEHICLES: re.compile(
        r"\b("
        r"rocket|launch\s?vehicle|booster|falcon|starship|"
        r"new\s?glenn|vulcan|ariane|soyuz|long\s?march|"
        r"electron|neutron|terran|starliner|"
        r"first\s?stage|second\s?stage|upper\s?stage|"
        r"launch\s?pad|liftoff|static\s?fire|"
        r"reusab(le|ility)|fairing|payload\s?to\s?orbit"
        r")\b",
        re.IGNORECASE,
    ),
    SpaceCategory.SPACE_SCIENCE: re.compile(
        r"\b("
        r"exoplanet|extrasolar|habitable\s?zone|"
        r"james\s?webb|jwst|hubble|chandra|"
        r"dark\s?matter|dark\s?energy|cosmic|"
        r"supernova|neutron\s?star|black\s?hole|"
        r"spectroscop|astronomer|astrophysic|"
        r"cosmolog|gravitational\s?wave|"
        r"planet\s?form|solar\s?system|"
        r"stellar|galax"
        r")\b",
        re.IGNORECASE,
    ),
    SpaceCategory.COMMERCIAL_SPACE: re.compile(
        r"\b("
        r"spacex|blue\s?origin|rocket\s?lab|"
        r"virgin\s?(galactic|orbit)|relativity\s?space|"
        r"axiom|vast|orbital\s?reef|"
        r"commercial\s?(crew|cargo|space)|"
        r"space\s?tourism|suborbital|"
        r"private\s?astronaut|billionaire|"
        r"space\s?econom|space\s?startup|"
        r"ipo|valuation|fundrais|venture"
        r")\b",
        re.IGNORECASE,
    ),
    SpaceCategory.LUNAR: re.compile(
        r"\b("
        r"lunar|moon|artemis|gateway|"
        r"moonshot|cislunar|"
        r"luna\s?\d|chandrayaan|slim|"
        r"south\s?pole.{0,10}moon|"
        r"lunar\s?(lander|rover|base|surface|orbit)|"
        r"regolith|moon\s?rock|helium.?3"
        r")\b",
        re.IGNORECASE,
    ),
    SpaceCategory.MARS: re.compile(
        r"\b("
        r"mars|martian|perseverance|ingenuity|"
        r"curiosity\s?rover|insight\s?lander|"
        r"olympus\s?mons|valles\s?marineris|"
        r"mars\s?(sample|colony|habitat|base|mission)|"
        r"red\s?planet|phobos|deimos"
        r")\b",
        re.IGNORECASE,
    ),
    SpaceCategory.EARTH_OBSERVATION: re.compile(
        r"\b("
        r"earth\s?observation|remote\s?sensing|"
        r"weather\s?satellite|climate\s?monitor|"
        r"landsat|sentinel|copernicus|"
        r"synthetic\s?aperture|sar\s?imag|"
        r"geospatial|earth\s?imag|"
        r"wildfire\s?detect|flood\s?monitor|"
        r"carbon\s?monitor|greenhouse\s?gas\s?track"
        r")\b",
        re.IGNORECASE,
    ),
    SpaceCategory.POLICY: re.compile(
        r"\b("
        r"space\s?policy|space\s?law|"
        r"outer\s?space\s?treaty|artemis\s?accords|"
        r"faa\s?licens|space\s?regulat|"
        r"nasa\s?(budget|administrator|funding)|"
        r"congress.{0,15}space|senate.{0,15}space|"
        r"space\s?force|"
        r"orbital\s?debris\s?(policy|regulat)|"
        r"spectrum\s?allocat|itu\b|"
        r"export\s?control|itar\b"
        r")\b",
        re.IGNORECASE,
    ),
    SpaceCategory.INTERNATIONAL: re.compile(
        r"\b("
        r"esa\b|jaxa\b|cnsa\b|isro\b|roscosmos|"
        r"kari\b|cnes\b|dlr\b|"
        r"european\s?space|india.{0,10}space|"
        r"china.{0,10}space|japan.{0,10}space|"
        r"tiangong|tianwen|gaganyaan|"
        r"international\s?(cooperat|partner)"
        r")\b",
        re.IGNORECASE,
    ),
    SpaceCategory.ISS_STATIONS: re.compile(
        r"\b("
        r"international\s?space\s?station|iss\b|"
        r"space\s?station|tiangong|"
        r"crew\s?dragon\s?(dock|undock|splashdown)|"
        r"orbital\s?reef|axiom\s?station|"
        r"starlab|deorbit|"
        r"microgravity|spacewalk|eva\b"
        r")\b",
        re.IGNORECASE,
    ),
    SpaceCategory.DEFENSE_SPACE: re.compile(
        r"\b("
        r"space\s?force|ussf\b|"
        r"space\s?command|spacecom|"
        r"space\s?domain\s?awareness|"
        r"missile\s?(warning|defense|track)|"
        r"anti.?satellite|asat\b|"
        r"space\s?weapon|"
        r"national\s?reconnaissance|nro\b|"
        r"classified\s?(payload|mission|launch)"
        r")\b",
        re.IGNORECASE,
    ),
    SpaceCategory.SATELLITE_COMMS: re.compile(
        r"\b("
        r"starlink|kuiper|oneweb|"
        r"satellite\s?(internet|broadband|comms?|constellation)|"
        r"leo\s?constellation|"
        r"direct.to.(cell|device)|"
        r"geostationary|geo\s?satellite|"
        r"v.?band|ka.?band|ku.?band|"
        r"telesat|ses\b|intelsat|viasat"
        r")\b",
        re.IGNORECASE,
    ),
    SpaceCategory.DEEP_SPACE: re.compile(
        r"\b("
        r"deep\s?space|interstellar|voyager|"
        r"new\s?horizons|europa\s?clipper|"
        r"dragonfly|titan\b.{0,15}mission|"
        r"asteroid\s?(belt|mining|redirect)|"
        r"comet|kuiper\s?belt\s?object|"
        r"oort\s?cloud|"
        r"outer\s?planet|jupiter|saturn|uranus|neptune|pluto|"
        r"solar\s?probe|parker\s?solar|"
        r"heliophysic|solar\s?wind"
        r")\b",
        re.IGNORECASE,
    ),
}


def classify_by_keywords(title: str, body: str | None = None) -> list[SpaceCategory]:
    """Classify content using keyword regex patterns.

    Checks title first (stronger signal), then first 2000 chars of body.
    Returns a deduplicated list of matching categories.
    """
    matches: set[SpaceCategory] = set()
    body_prefix = (body or "")[:2000]

    for category, pattern in _CATEGORY_PATTERNS.items():
        if pattern.search(title) or (body_prefix and pattern.search(body_prefix)):
            matches.add(category)

    return sorted(matches, key=lambda c: c.value)
