# C12 — Redesigned console: the stylesheet (FR39).
"""One scoped stylesheet, injected once per render by the redesigned app.

**Scoping.** Every rule here is either a CSS custom property on `:root`, a
`.rd-*` class, or a Streamlit structural selector qualified by the app's own
`data-testid` container. Classic runs in a different process on a different
port and never imports this module, so it cannot be reached by this CSS; the
`rd-` prefix is the second line of defence, so that a future shared page
could not be restyled by accident either.

Nothing here is a component Classic shares. Changing a colour in `tokens.py`
changes the redesigned frontend and nothing else.
"""
from __future__ import annotations

import streamlit as st

from . import tokens as T

_CSS = f"""
<style id="seraph-redesign">
:root {{
  --rd-app:{T.APP_BG}; --rd-nav:{T.NAV_BG}; --rd-card:{T.CARD_BG};
  --rd-s2:{T.SURFACE_2}; --rd-s3:{T.SURFACE_3}; --rd-border:{T.BORDER};
  --rd-text:{T.TEXT}; --rd-dim:{T.TEXT_DIM}; --rd-faint:{T.TEXT_FAINT};
  --rd-accent:{T.ACCENT}; --rd-selected:{T.SELECTED};
  --rd-hawkes:{T.PILLAR_COLOUR['hawkes']};
  --rd-rmt:{T.PILLAR_COLOUR['rmt']};
  --rd-hamilton:{T.PILLAR_COLOUR['hamilton']};
  --rd-radius-lg:{T.RADIUS_LG}; --rd-radius-md:{T.RADIUS_MD};
  --rd-radius-sm:{T.RADIUS_SM}; --rd-shadow:{T.SHADOW};
  --rd-mono:{T.MONO}; --rd-sans:{T.SANS};
}}

/* ---- page shell ------------------------------------------------------ */
.stApp, [data-testid="stAppViewContainer"] {{ background:var(--rd-app); }}
[data-testid="stHeader"] {{ background:transparent; }}
.stApp, .stApp p, .stApp span, .stApp div, .stApp label {{
  font-family:var(--rd-sans); color:var(--rd-text);
}}
/* ...but NOT the icon spans. Streamlit draws its chevrons and the sidebar
   collapse control as ligatures in a Material icon font; overriding their
   family makes the browser render the ligature NAME as literal text
   ("keyboard_double_arrow_left") beside the control. Restore the font the
   element asked for and let the ligature resolve. */
.stApp [data-testid="stIconMaterial"],
.stApp .material-symbols-rounded, .stApp .material-icons,
.stApp span[class*="material-symbols"], .stApp [data-testid*="Icon"] span {{
  font-family:"Material Symbols Rounded","Material Icons" !important;
}}
[data-testid="stAppViewContainer"] .block-container {{
  max-width:1680px; padding:1.1rem 1.6rem 3rem;
}}
[data-testid="stSidebar"] {{
  background:var(--rd-nav); border-right:1px solid var(--rd-border);
}}
[data-testid="stSidebar"] .block-container {{ padding-top:1.4rem; }}

/* Financial values are tabular everywhere they are financial. */
.rd-num, .rd-metric-value, .rd-table td.rd-n, .rd-dial text, .rd-axis text {{
  font-family:var(--rd-mono);
  font-variant-numeric:tabular-nums; font-feature-settings:"tnum" 1,"zero" 1;
}}

/* ---- large rounded containers, smaller cards inside ------------------ */
.rd-panel {{
  background:var(--rd-card); border:1px solid var(--rd-border);
  border-radius:var(--rd-radius-lg); box-shadow:var(--rd-shadow);
  padding:18px 20px 20px; margin-bottom:14px;
}}
.rd-card {{
  background:var(--rd-s2); border:1px solid var(--rd-border);
  border-radius:var(--rd-radius-md); padding:14px 16px;
}}
.rd-card--flat {{ background:var(--rd-s3); box-shadow:none; }}
.rd-panel-head {{
  display:flex; align-items:baseline; gap:10px; margin:0 0 14px;
}}
.rd-panel-title {{
  font-size:12px; font-weight:650; letter-spacing:.10em;
  text-transform:uppercase; color:var(--rd-text); margin:0;
}}
.rd-panel-sub {{ font-size:12px; color:var(--rd-dim); margin:0; }}
.rd-panel-note {{
  font-size:11.5px; color:var(--rd-faint); line-height:1.55; margin:10px 0 0;
}}

/* ---- top bar --------------------------------------------------------- */
.rd-topbar {{
  display:flex; align-items:center; justify-content:space-between; gap:18px;
  background:var(--rd-nav); border:1px solid var(--rd-border);
  border-radius:var(--rd-radius-lg); padding:14px 20px; margin-bottom:14px;
}}
.rd-topbar h1 {{
  font-size:18px; font-weight:680; letter-spacing:.015em; margin:0;
  color:var(--rd-text);
}}
.rd-topbar .rd-eyebrow {{
  font-size:10.5px; letter-spacing:.16em; text-transform:uppercase;
  color:var(--rd-accent); margin:0 0 3px;
}}
.rd-topbar-right {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}

/* ---- chips ----------------------------------------------------------- */
.rd-chip {{
  display:inline-flex; align-items:center; gap:7px;
  background:var(--rd-s2); border:1px solid var(--rd-border);
  border-radius:999px; padding:5px 12px; font-size:11.5px;
  color:var(--rd-dim); white-space:nowrap;
}}
.rd-chip b {{ color:var(--rd-text); font-weight:600; }}
.rd-chip .rd-dot {{
  width:7px; height:7px; border-radius:50%; background:var(--rd-faint);
  flex:0 0 auto;
}}
.rd-chip--warn {{ border-color:#5A4420; background:#1E1708; }}
.rd-chip--warn .rd-dot {{ background:{T.ALERT['amber']}; }}
.rd-chip--bad {{ border-color:#56222C; background:#1D0E12; }}
.rd-chip--bad .rd-dot {{ background:{T.ALERT['red']}; }}
.rd-chip--ok {{ border-color:#1F4435; background:#0A1A14; }}
.rd-chip--ok .rd-dot {{ background:{T.ALERT['green']}; }}
.rd-chip--accent {{ border-color:#3A3366; background:#15122A; color:var(--rd-text); }}
.rd-chip--accent .rd-dot {{ background:var(--rd-accent); }}

/* ---- the unavailable treatment -------------------------------------- */
/* Deliberate, never empty: a dashed border and a stated reason. A missing
   quantity must look different from a quantity that happens to be small. */
.rd-unavail {{
  border:1px dashed var(--rd-border); border-radius:var(--rd-radius-md);
  background:repeating-linear-gradient(135deg,
    transparent 0 7px, rgba(255,255,255,.016) 7px 14px);
  padding:12px 14px;
}}
.rd-unavail-label {{
  font-size:10.5px; font-weight:650; letter-spacing:.13em;
  text-transform:uppercase; color:var(--rd-faint); margin:0 0 5px;
}}
.rd-reason {{ font-size:11.5px; color:var(--rd-dim); line-height:1.6; margin:0; }}
.rd-reason + .rd-reason {{ margin-top:5px; }}

/* ---- metric ---------------------------------------------------------- */
.rd-metric-label {{
  font-size:10.5px; letter-spacing:.12em; text-transform:uppercase;
  color:var(--rd-faint); margin:0 0 4px;
}}
.rd-metric-value {{ font-size:26px; font-weight:600; line-height:1.1; margin:0; }}
.rd-metric-unit {{ font-size:11.5px; color:var(--rd-dim); margin:3px 0 0; }}

/* ---- pillar cards ---------------------------------------------------- */
.rd-pillar {{
  background:var(--rd-s2); border:1px solid var(--rd-border);
  border-radius:var(--rd-radius-md); padding:0; overflow:hidden; height:100%;
}}
.rd-pillar-rule {{ height:3px; width:100%; }}
.rd-pillar-body {{ padding:13px 15px 15px; }}
.rd-pillar-name {{
  font-size:11px; font-weight:650; letter-spacing:.13em; text-transform:uppercase;
  margin:0 0 2px;
}}
.rd-pillar-model {{ font-size:11px; color:var(--rd-faint); margin:0 0 11px; }}

/* ---- legend ---------------------------------------------------------- */
.rd-legend {{ display:flex; flex-wrap:wrap; gap:7px 16px; margin:12px 0 0; }}
.rd-legend-item {{
  display:flex; align-items:center; gap:7px;
  font-size:11px; color:var(--rd-dim);
}}
.rd-swatch {{ width:11px; height:11px; border-radius:3px; flex:0 0 auto; }}
.rd-swatch--track {{
  background:{T.UNAVAILABLE_TRACK}; border:1px dashed var(--rd-border);
}}

/* ---- tables ---------------------------------------------------------- */
.rd-table {{ width:100%; border-collapse:collapse; font-size:12px; }}
.rd-table th {{
  text-align:left; font-size:10px; font-weight:600; letter-spacing:.11em;
  text-transform:uppercase; color:var(--rd-faint);
  padding:7px 10px; border-bottom:1px solid var(--rd-border);
}}
.rd-table td {{
  padding:8px 10px; border-bottom:1px solid rgba(41,51,66,.5);
  color:var(--rd-text);
}}
.rd-table td.rd-n {{ text-align:right; }}
.rd-table tr:last-child td {{ border-bottom:none; }}
.rd-table td.rd-muted {{ color:var(--rd-faint); }}

/* ---- Streamlit controls, restyled in place -------------------------- */
[data-testid="stSidebar"] .stRadio label p,
[data-testid="stSidebar"] .stSelectbox label p {{
  font-size:10.5px; letter-spacing:.11em; text-transform:uppercase;
  color:var(--rd-faint);
}}
.stSelectbox div[data-baseweb="select"] > div {{
  background:var(--rd-s2); border-color:var(--rd-border);
  border-radius:var(--rd-radius-sm); font-size:12.5px;
}}
.stRadio [role="radiogroup"] {{ gap:4px; }}
div[data-testid="stExpander"] {{
  border:1px solid var(--rd-border); border-radius:var(--rd-radius-md);
  background:var(--rd-card); overflow:hidden;
}}
div[data-testid="stExpander"] summary {{ font-size:12px; color:var(--rd-dim); }}
hr {{ border-color:var(--rd-border); }}

/* Altair canvases sit on the card, not on a white rectangle. */
[data-testid="stVegaLiteChart"], [data-testid="stVegaLiteChart"] canvas {{
  background:transparent !important;
}}
</style>
"""


def inject() -> None:
    """Put the stylesheet on the page. Idempotent within one render."""
    st.markdown(_CSS, unsafe_allow_html=True)


def css() -> str:
    """The stylesheet text, for tests that assert scoping without a browser."""
    return _CSS
