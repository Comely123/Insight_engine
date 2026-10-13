"""Soft seafoam public theme — low-glare accents instead of harsh red."""

# Soft primary: muted seafoam / sage (eye-friendly)
_PRIMARY = "#6D9B8E"
_PRIMARY_HOVER = "#5A867A"
_PRIMARY_SOFT = "#D8E8E3"
_PRIMARY_TEXT = "#243D38"
_RING = "#A8C4BC"

PUBLIC_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Noto+Sans+SC:wght@400;500;700&display=swap');

:root {{
  --ie-primary: {_PRIMARY};
  --ie-primary-hover: {_PRIMARY_HOVER};
  --ie-primary-soft: {_PRIMARY_SOFT};
  --ie-primary-text: {_PRIMARY_TEXT};
}}

html, body, [class*="css"]  {{
  font-family: "Noto Sans SC", "DM Sans", sans-serif;
}}
.stApp {{
  background: #f7f9f8;
  color: #1a1a1a;
}}

/* Frosted-glass sticky header — hosts native top page switcher */
header[data-testid="stHeader"] {{
  background: rgba(247, 249, 248, 0.55) !important;
  backdrop-filter: blur(18px) saturate(1.35) !important;
  -webkit-backdrop-filter: blur(18px) saturate(1.35) !important;
  border-bottom: 1px solid rgba(212, 224, 220, 0.85) !important;
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.45) inset !important;
  z-index: 999990 !important;
}}

.block-container,
div[data-testid="stMainBlockContainer"],
section.main .block-container {{
  /* Must sit fully below sticky frosted header + top circle nav */
  padding-top: 7.5rem !important;
  padding-bottom: 2.5rem !important;
  max-width: 1040px;
}}
/* Explicit spacer so first widgets never tuck under glass */
.ie-below-header {{
  height: 1.25rem;
  width: 100%;
}}

/* Keep the right-hand page scrollbar */
html, body, .stApp {{
  height: 100%;
}}
section[data-testid="stMain"] {{
  overflow: auto !important;
}}
div[data-testid="stAppViewContainer"],
div[data-testid="stMain"] {{
  overflow: auto !important;
}}
section.main {{
  overflow: auto !important;
}}

/* Top nav: icon-only circular switches (hide text pills) */
a[data-testid="stTopNavLink"] {{
  width: 2.35rem !important;
  height: 2.35rem !important;
  min-width: 2.35rem !important;
  padding: 0 !important;
  margin: 0 0.15rem !important;
  gap: 0 !important;
  justify-content: center !important;
  align-items: center !important;
  border-radius: 999px !important;
  background: transparent !important;
}}
a[data-testid="stTopNavLink"]:hover {{
  background: {_PRIMARY_SOFT} !important;
}}
/* Active page = soft circle */
a[data-testid="stTopNavLink"][aria-current="page"],
a[data-testid="stTopNavLink"][aria-selected="true"] {{
  background: {_PRIMARY_SOFT} !important;
  color: {_PRIMARY_TEXT} !important;
}}
/* Hide label text — keep Material icon only (2nd child / markdown) */
a[data-testid="stTopNavLink"] > span:nth-child(2),
a[data-testid="stTopNavLink"] [data-testid="stMarkdownContainer"] {{
  position: absolute !important;
  width: 1px !important;
  height: 1px !important;
  padding: 0 !important;
  margin: -1px !important;
  overflow: hidden !important;
  clip: rect(0, 0, 0, 0) !important;
  white-space: nowrap !important;
  border: 0 !important;
}}
div[data-testid="stTopNavLinkContainer"] {{
  display: inline-flex !important;
  align-items: center !important;
}}

/* Chart grid cells — prevent legend from sitting under sticky chrome */
div[data-testid="stVegaLiteChart"],
div[data-testid="stArrowVegaLiteChart"] {{
  margin-top: 0.25rem;
}}
/* Square-ish 2×2 chart cells */
div[data-testid="stVerticalBlockBorderWrapper"] {{
  min-height: 340px;
  background: #fff;
  border-radius: 14px !important;
}}

/* CJK headings: avoid clipping */
h1, h2, h3, h4 {{
  color: #111 !important;
  letter-spacing: 0 !important;
  line-height: 1.5 !important;
  overflow: visible !important;
  padding-top: 0.15em !important;
  padding-bottom: 0.1em !important;
  margin-top: 0.35rem !important;
}}
div[data-testid="stMarkdownContainer"] {{
  overflow: visible !important;
}}
div[data-testid="stVegaLiteChart"],
div[data-testid="stArrowVegaLiteChart"] {{
  overflow: visible !important;
  padding: 0.35rem 0.25rem 0.75rem 0.25rem;
}}
div[data-testid="stVegaLiteChart"] svg,
div[data-testid="stArrowVegaLiteChart"] svg {{
  overflow: visible !important;
}}
.stAlert {{ border-radius: 12px; }}

div[data-testid="stMetric"] {{
  background: #fff;
  border: 1px solid #e4ebe8;
  padding: 0.75rem 1rem;
  border-radius: 12px;
}}
.hero-card {{
  background: #fff;
  border: 1px solid #e4ebe8;
  border-radius: 16px;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1rem;
}}
.muted {{ color: #666; font-size: 0.95rem; line-height: 1.6; }}
.pill {{
  display: inline-block;
  background: {_PRIMARY_SOFT};
  color: {_PRIMARY_TEXT};
  border-radius: 999px;
  padding: 0.2rem 0.75rem;
  font-size: 0.85rem;
  margin-right: 0.35rem;
}}

/* Soft primary — buttons */
button[kind="primary"],
button[data-testid="baseButton-primary"],
div[data-testid="stButton"] button[kind="primary"] {{
  background-color: {_PRIMARY} !important;
  border-color: {_PRIMARY} !important;
  color: #fff !important;
}}
button[kind="primary"]:hover,
button[data-testid="baseButton-primary"]:hover {{
  background-color: {_PRIMARY_HOVER} !important;
  border-color: {_PRIMARY_HOVER} !important;
}}

span[data-baseweb="tag"],
div[data-baseweb="tag"] {{
  background-color: {_PRIMARY_SOFT} !important;
  color: {_PRIMARY_TEXT} !important;
  border-color: {_RING} !important;
}}
span[data-baseweb="tag"] span,
div[data-baseweb="tag"] span {{
  color: {_PRIMARY_TEXT} !important;
}}

div[role="radiogroup"] label[data-checked="true"] svg,
div[data-testid="stRadio"] label svg[data-testid="stRadioOptionIcon"] {{
  fill: {_PRIMARY} !important;
}}
input[type="radio"]:checked {{
  accent-color: {_PRIMARY};
}}
input[type="checkbox"]:checked {{
  accent-color: {_PRIMARY};
}}

*:focus-visible {{
  outline-color: {_RING} !important;
}}

div[data-testid="stProgress"] > div > div {{
  background-color: {_PRIMARY_SOFT} !important;
}}
div[data-testid="stProgress"] > div > div > div {{
  background: linear-gradient(
    90deg,
    {_PRIMARY} 0%,
    {_PRIMARY_HOVER} 45%,
    {_PRIMARY} 100%
  ) !important;
  background-size: 200% 100% !important;
  animation: ie-progress-shine 1.1s linear infinite !important;
  transition: width 0.35s ease-out !important;
}}
@keyframes ie-progress-shine {{
  0% {{ background-position: 100% 0; }}
  100% {{ background-position: -100% 0; }}
}}
</style>
"""

# Soft macaron series for charts
MACARON = ["#B8E0D2", "#D8E8E3", "#FFE5B4", "#C9E4F1", "#E6D5F2", "#F5D0C5"]
