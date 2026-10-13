"""Minimal black/white + macaron chart theme for the public product."""

PUBLIC_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Noto+Sans+SC:wght@400;500;700&display=swap');

html, body, [class*="css"]  {
  font-family: "Noto Sans SC", "DM Sans", sans-serif;
}
.stApp {
  background: #fafafa;
  color: #1a1a1a;
}
/* Clear Streamlit top chrome so page titles are not clipped */
header[data-testid="stHeader"] {
  background: rgba(250, 250, 250, 0.85);
}
.block-container {
  padding-top: 4.25rem !important;
  padding-bottom: 2.5rem !important;
  max-width: 1040px;
}
/* CJK headings: avoid negative letter-spacing + overflow clipping */
h1, h2, h3, h4 {
  color: #111 !important;
  letter-spacing: 0 !important;
  line-height: 1.5 !important;
  overflow: visible !important;
  padding-top: 0.15em !important;
  padding-bottom: 0.1em !important;
  margin-top: 0.35rem !important;
}
div[data-testid="stMarkdownContainer"] {
  overflow: visible !important;
}
div[data-testid="stMarkdownContainer"] h1,
div[data-testid="stMarkdownContainer"] h2,
div[data-testid="stMarkdownContainer"] h3 {
  overflow: visible !important;
  clip-path: none !important;
}
section.main > div {
  overflow: visible !important;
}
/* Avoid Vega/Altair title and axis labels looking clipped */
div[data-testid="stVegaLiteChart"],
div[data-testid="stArrowVegaLiteChart"] {
  overflow: visible !important;
  padding: 0.35rem 0.25rem 0.75rem 0.25rem;
}
div[data-testid="stVegaLiteChart"] svg,
div[data-testid="stArrowVegaLiteChart"] svg {
  overflow: visible !important;
}
.stAlert { border-radius: 12px; }

div[data-testid="stMetric"] {
  background: #fff;
  border: 1px solid #e8e8e8;
  padding: 0.75rem 1rem;
  border-radius: 12px;
}
.hero-card {
  background: #fff;
  border: 1px solid #ececec;
  border-radius: 16px;
  padding: 1.25rem 1.5rem;
  margin-bottom: 1rem;
}
.muted { color: #666; font-size: 0.95rem; line-height: 1.6; }
.pill {
  display: inline-block;
  background: #F8E1E7;
  color: #333;
  border-radius: 999px;
  padding: 0.2rem 0.75rem;
  font-size: 0.85rem;
  margin-right: 0.35rem;
}
.page-title {
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1.5;
  color: #111;
  margin: 0.5rem 0 1rem 0;
  padding-top: 0.35rem;
  overflow: visible;
}
</style>
"""

# Macaron series for charts (used as st chart theming via dataframe columns order)
MACARON = ["#B8E0D2", "#F8E1E7", "#FFE5B4", "#C9E4F1", "#E6D5F2", "#F5D0C5"]
