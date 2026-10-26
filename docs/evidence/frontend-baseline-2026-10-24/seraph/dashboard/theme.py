# C12 — Dashboard (FR39–FR42): the DESIGN.md token layer.
"""Design tokens and the uncertainty signature, as CSS for Streamlit.

Tokens are DESIGN.md §3 verbatim. The layout idiom — mono type, letterspaced
small-caps card headers, a dense instrument-panel grid, a ticker strip — comes
from the reference mock, which reads as a trading terminal rather than a
consumer dashboard. The two reconcile cleanly: DESIGN.md is already dark-first
and deferential, and a terminal idiom is the honest visual language for an
instrument that is monitored for long stretches.

**The signature (DESIGN.md §2) is implemented, not decorated.** The CSRS panel
sits on a material whose optical softness scales with `Var(CSRS)`, so a viewer
registers uncertainty pre-attentively before reading a digit. Two rules from
DESIGN.md are load-bearing and observed here: the numerals themselves are never
blurred (they sit crisply on top at full contrast), and the same information is
carried redundantly by the confidence-band width, so the design is complete
where backdrop-filter is unavailable or `prefers-reduced-transparency` is set.

**Regime is always encoded at least twice** (DESIGN.md §3): colour plus fixed
stack position plus an explicit text label. Green-amber-red is the worst hue
triple for deuteranopia and protanopia — roughly 8% of men cannot separate
regime 1 from regime 3 — so colour is never the sole channel, and the lightness
values are deliberately separated so the palette survives greyscale.
"""
from __future__ import annotations

# DESIGN.md §3 — surfaces, ink, semantic regime colours, reserved accent.
TOKENS = {
    "bg_base": "#0B1014",
    "bg_raised": "#141B21",
    "bg_overlay": "#1C252D",
    "bg_sunken": "#070B0E",
    "separator": "#212C34",
    "separator_strong": "#2E3A44",
    "ink_primary": "#E8EDF0",
    "ink_secondary": "#97A5AF",
    "ink_tertiary": "#64727C",
    "ink_quaternary": "#414D56",   # statistically insignificant marks ONLY
    "tranquil": "#4A9D7E",
    "stressed": "#C9A227",
    "crisis": "#C4462F",
    "dormant": "#55707E",
    "accent": "#5B9DD9",           # focus/selection and nothing else
}

ALERT_COLOUR = {
    "green": TOKENS["tranquil"],
    "amber": TOKENS["stressed"],
    "red": TOKENS["crisis"],
}
REGIME_LABELS = ("Tranquil", "Stressed", "Crisis")
REGIME_COLOURS = (TOKENS["tranquil"], TOKENS["stressed"], TOKENS["crisis"])


def blur_radius(variance: float) -> float:
    """DESIGN.md §2: blur_radius = clamp(0, 16, 40·sqrt(variance)) px."""
    return max(0.0, min(16.0, 40.0 * max(variance, 0.0) ** 0.5))


def edge_opacity(variance: float) -> float:
    """DESIGN.md §2: edge_opacity = clamp(0.15, 1.0, 1 − 3·sqrt(variance))."""
    return max(0.15, min(1.0, 1.0 - 3.0 * max(variance, 0.0) ** 0.5))


def css() -> str:
    t = TOKENS
    return f"""
<style>
  :root {{
    --bg-base:{t['bg_base']}; --bg-raised:{t['bg_raised']}; --bg-overlay:{t['bg_overlay']};
    --bg-sunken:{t['bg_sunken']}; --separator:{t['separator']};
    --separator-strong:{t['separator_strong']};
    --ink-primary:{t['ink_primary']}; --ink-secondary:{t['ink_secondary']};
    --ink-tertiary:{t['ink_tertiary']}; --ink-quaternary:{t['ink_quaternary']};
    --tranquil:{t['tranquil']}; --stressed:{t['stressed']}; --crisis:{t['crisis']};
    --dormant:{t['dormant']}; --accent:{t['accent']};
    --mono: ui-monospace, SFMono-Regular, Menlo, "Cascadia Mono", monospace;
  }}
  .stApp {{ background: var(--bg-base); color: var(--ink-primary); }}
  #MainMenu, footer {{ visibility: hidden; }}

  .srph-brand {{ font-family: var(--mono); font-size: 17px; letter-spacing: .34em;
     font-weight: 600; color: var(--ink-primary); }}
  .srph-brand .accent {{ color: var(--stressed); }}

  /* Elevation by surface value and a hairline — never by shadow (DESIGN.md §3):
     shadows imply a physical light source this interface does not have. */
  .srph-card {{ background: var(--bg-raised); border: 1px solid var(--separator);
     border-radius: 5px; padding: 0; margin-bottom: 10px; }}
  .srph-card h3 {{ margin: 0; padding: 8px 12px; border-bottom: 1px solid var(--separator);
     font-family: var(--mono); font-size: 10px; letter-spacing: .16em;
     color: var(--ink-secondary); font-weight: 500; text-transform: uppercase; }}
  .srph-card .srph-body {{ padding: 11px 12px; }}

  .srph-ticker {{ display:flex; gap:26px; padding:7px 12px; overflow-x:auto;
     white-space:nowrap; font-family:var(--mono); font-size:11px;
     background: var(--bg-sunken); border:1px solid var(--separator); border-radius:4px; }}
  .srph-ticker b {{ font-weight:500; color:var(--ink-tertiary); margin-right:7px; }}

  /* THE SIGNATURE — optical softness scales with Var(CSRS). The numerals are
     layered on top at full contrast and are never blurred. */
  .srph-signature {{ position:relative; border-radius:6px; overflow:hidden;
     background: var(--bg-sunken); padding: 18px 20px; }}
  .srph-signature .srph-material {{ position:absolute; inset:0; }}
  .srph-signature .srph-value {{ position:relative; font-family:var(--mono);
     font-size:46px; font-weight:600; color:var(--ink-primary); line-height:1; }}
  .srph-signature .srph-meta {{ position:relative; font-family:var(--mono);
     font-size:11px; color:var(--ink-secondary); margin-top:6px; }}

  /* Fallback channel, mandatory per DESIGN.md §2: where backdrop blur is
     unavailable the confidence band alone must still carry the uncertainty. */
  @media (prefers-reduced-transparency: reduce) {{
    .srph-signature .srph-material {{ filter: none !important; opacity: .5 !important; }}
  }}

  .srph-band {{ height:6px; border-radius:3px; background:var(--bg-overlay);
     position:relative; margin-top:10px; }}
  .srph-band .srph-fill {{ position:absolute; top:0; bottom:0; border-radius:3px; }}

  .srph-chip {{ display:inline-block; font-family:var(--mono); font-size:9.5px;
     letter-spacing:.08em; padding:1px 6px; border-radius:2px; border:1px solid; }}
  .srph-degraded {{ font-family:var(--mono); font-size:10.5px; color:var(--stressed);
     border-left:2px solid var(--stressed); padding-left:8px; margin-top:8px; }}
  .srph-note {{ font-family:var(--mono); font-size:10px; color:var(--ink-tertiary); }}
</style>
"""


def signature_html(csrs: float, variance: float, ci_lo: float, ci_hi: float,
                   alert: str, degraded: bool) -> str:
    """The CSRS panel. Uncertainty is carried by three redundant channels:
    material blur, edge opacity, and the width of the confidence band."""
    colour = ALERT_COLOUR.get(alert, TOKENS["dormant"])
    blur = blur_radius(variance)
    opacity = edge_opacity(variance)
    lo, hi = max(0.0, ci_lo), min(1.0, ci_hi)
    width = max(1.0, (hi - lo) * 100.0)
    left = lo * 100.0
    degraded_html = (
        '<div class="srph-degraded">DEGRADED MASK — not comparable with '
        'full-coverage readings</div>' if degraded else ""
    )
    return f"""
<div class="srph-signature">
  <div class="srph-material" style="
       background: radial-gradient(120% 140% at 20% 0%, {colour}2E, transparent 70%);
       filter: blur({blur:.1f}px); opacity: {opacity:.2f};"></div>
  <div class="srph-value">{csrs:.3f}</div>
  <div class="srph-meta">COMPOSITE SYSTEMIC RISK SCORE &nbsp;·&nbsp;
     95% CI {lo:.3f}–{hi:.3f} &nbsp;·&nbsp;
     <span class="srph-chip" style="color:{colour};border-color:{colour}77">
     {alert.upper()}</span></div>
  <div class="srph-band"><div class="srph-fill" style="
       left:{left:.1f}%; width:{width:.1f}%; background:{colour}CC"></div></div>
  {degraded_html}
</div>
"""
