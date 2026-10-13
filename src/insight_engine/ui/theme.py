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
h1, h2, h3 { color: #111 !important; letter-spacing: -0.02em; }
.block-container { padding-top: 1.5rem; max-width: 980px; }
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
</style>
"""

# Macaron series for charts (used as st chart theming via dataframe columns order)
MACARON = ["#B8E0D2", "#F8E1E7", "#FFE5B4", "#C9E4F1", "#E6D5F2", "#F5D0C5"]
