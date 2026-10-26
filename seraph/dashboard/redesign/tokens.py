# C12 — Redesigned console: design tokens (FR39).
"""The one place a colour or a radius is named.

Pure data, no Streamlit import, so the instruments and the tests can read the
palette without starting an app.

**Pillar colour is a contract, not decoration.** `PILLAR_COLOUR` is keyed by
`PILLAR_ORDER` and every surface in this package — dial legend, pillar cards,
breakdown tracks, chart series, timeline — reads it from here. A pillar that
renders lavender in one panel and amber in another is a reading error waiting
to happen, so there is exactly one table.
"""
from seraph.shared_types import PILLAR_ORDER

# --- surfaces -------------------------------------------------------------
APP_BG = "#080D16"           # very dark navy — the page
NAV_BG = "#100E1B"           # near-black violet — the left rail and top bar
CARD_BG = "#0D1725"          # deep navy — analytical cards
SURFACE_2 = "#191727"        # dark violet — secondary surfaces inside a card
SURFACE_3 = "#121C2C"        # one step up from CARD_BG for nested tracks
BORDER = "#293342"           # muted slate

# --- type -----------------------------------------------------------------
TEXT = "#F1F4FA"             # soft white
TEXT_DIM = "#A2ACBD"         # cool gray secondary
TEXT_FAINT = "#6B7689"       # for units, axis ticks, disabled rows

# --- accents --------------------------------------------------------------
ACCENT = "#A69BE0"           # lavender — the product accent
SELECTED = "#3D83FF"         # electric blue — the selected series

#: Alert levels are produced by the model (`CsrsPoint.alert_level`), so they
#: get colours; nothing else in this file assigns a value a verdict colour.
ALERT = {
    "red": "#E0576B",
    "amber": "#E8A33D",
    "green": "#44C58A",
    "unavailable": TEXT_FAINT,
}

#: Keyed by PILLAR_ORDER. Hawkes lavender, RMT blue/cyan, Hamilton amber.
PILLAR_COLOUR = {
    "hawkes": "#A69BE0",
    "rmt": "#49C6E5",
    "hamilton": "#E8A33D",
}
assert set(PILLAR_COLOUR) == set(PILLAR_ORDER), "pillar colours must cover PILLAR_ORDER"

#: The empty track behind every instrument. Never a value — it is the scale
#: a value would be drawn against. Kept a step lighter than CARD_BG so an
#: unfilled gauge still reads as a gauge rather than as a blank card.
UNAVAILABLE_TRACK = "#1F2B3E"

# --- geometry -------------------------------------------------------------
RADIUS_LG = "20px"           # large rounded containers
RADIUS_MD = "14px"           # cards inside them
RADIUS_SM = "9px"            # chips, tracks
SHADOW = "0 1px 2px rgba(0,0,0,.40), 0 6px 18px rgba(0,0,0,.22)"

MONO = ('"JetBrains Mono", "SF Mono", "Cascadia Mono", ui-monospace, '
        '"Roboto Mono", Menlo, Consolas, monospace')
SANS = ('"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, '
        'Helvetica, Arial, sans-serif')


def pillar_colour(name: str) -> str:
    """The one colour for `name`, or the dim grey for anything unrecognised."""
    return PILLAR_COLOUR.get(str(name).lower(), TEXT_FAINT)


def alert_colour(level) -> str:
    """The colour for a model-produced alert level; grey for absence."""
    return ALERT.get(str(level).lower(), ALERT["unavailable"])
