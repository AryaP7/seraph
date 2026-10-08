# C12 — Dashboard: theme signature and renderers (FR39, FR40, DESIGN.md §2/§3)
from __future__ import annotations

import numpy as np
import pytest

from seraph.dashboard.app import (
    render_mp_density,
    render_regime_stack,
    render_shapley,
    render_signals,
    render_ticker,
)
from seraph.dashboard.theme import blur_radius, edge_opacity, signature_html


def test_signature_blur_and_opacity_track_variance():
    """DESIGN.md §2 — softness scales with Var(CSRS), clamped at both ends."""
    assert blur_radius(0.0) == 0.0
    assert blur_radius(0.01) == pytest.approx(4.0)
    assert blur_radius(10.0) == 16.0, "blur must clamp at 16px"
    assert edge_opacity(0.0) == 1.0
    assert edge_opacity(10.0) == 0.15, "edge opacity must clamp at 0.15"
    assert blur_radius(0.04) > blur_radius(0.01)
    assert edge_opacity(0.04) < edge_opacity(0.01)


def test_signature_numerals_are_never_blurred():
    """The value sits on top at full contrast; only the material behind it
    softens (DESIGN.md §2). The filter must not apply to the text layer."""
    html = signature_html(0.62, 0.02, 0.5, 0.74, "amber", False)
    material = html[html.index("srph-material"):html.index("srph-value")]
    assert "filter: blur(" in material
    value = html[html.index("srph-value"):html.index("srph-meta")]
    assert "blur(" not in value


def test_signature_band_width_carries_uncertainty_independently():
    """Mandatory fallback: the design must be complete without the blur."""
    narrow = signature_html(0.5, 0.0001, 0.49, 0.51, "green", False)
    wide = signature_html(0.5, 0.04, 0.20, 0.80, "green", False)
    def width(h):
        seg = h[h.index("srph-fill"):]
        return float(seg.split("width:")[1].split("%")[0])
    assert width(wide) > width(narrow) * 3


def test_degraded_mask_is_stated_on_the_face_of_the_panel():
    assert "DEGRADED MASK" in signature_html(0.5, 0.01, 0.4, 0.6, "amber", True)
    assert "DEGRADED MASK" not in signature_html(0.5, 0.01, 0.4, 0.6, "amber", False)


def test_regime_stack_encodes_regime_more_than_once():
    """Colour alone fails for ~8% of men (DESIGN.md §3): position and an
    explicit label must also carry it."""
    html = render_regime_stack((0.6, 0.3, 0.1))
    for label in ("Tranquil", "Stressed", "Crisis"):
        assert label in html
    assert html.index("Tranquil") < html.index("Crisis"), "fixed stack order"
    assert "60%" in html


def test_regime_stack_shows_a_gap_when_unfitted():
    assert "awaiting" in render_regime_stack(None)


def test_shapley_masked_pillar_drawn_as_noise_not_hidden():
    html = render_shapley({"hawkes": 0.0, "rmt": 0.4, "hamilton": 0.2})
    assert "MARKET TOXICITY" in html, "a masked pillar stays visible, subordinate"
    assert "#414D56" in html, "zero contribution uses the designated noise ink"


def test_ticker_shows_dashes_for_absent_pillars():
    view = {"csrs": 0.5, "ciLower": 0.4, "ciUpper": 0.6, "maskDegraded": True}
    html = render_ticker(view, {"rmt": 0.33})
    assert "—" in html, "an unavailable pillar reads as a gap, not a zero"
    assert "DEGRADED" in html


def test_signals_feed_invents_nothing_when_quiet():
    view = {"alertLevel": "green", "explanation": "calm"}
    assert "no active signals" in render_signals(view, ())


def test_signals_feed_surfaces_amber_sectors():
    view = {"alertLevel": "amber", "explanation": "Elevated systemic risk"}
    html = render_signals(view, ({"sectorId": "steel", "flag": "amber"},
                                 {"sectorId": "pharma", "flag": "none"}))
    assert "steel" in html and "pharma" not in html


def test_mp_density_labels_the_q_actually_in_force():
    """AMENDMENT-02 — never a hard-coded Q=2."""
    lo, hi = 0.142, 2.634
    html = render_mp_density(0.021, lo, hi, 2.58, 388)
    assert "Q_t=2.58" in html and "N_t=388" in html
    assert "awaiting" not in html


def test_mp_density_shows_a_gap_before_the_pillar_runs():
    assert "awaiting" in render_mp_density(None, None, None, 0, 0)
