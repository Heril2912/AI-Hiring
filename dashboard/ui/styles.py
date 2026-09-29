"""Editorial Mineral styling and CSS injection for Streamlit."""
import streamlit as st

EDITORIAL_MINERAL_CSS = """
<style>
/* Base typography and background overrides */
html, body, [data-testid="stAppViewContainer"] {
    background-color: #F3F0E6;
    color: #202927;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

[data-testid="stSidebar"] {
    background-color: #FCFBF6;
    border-right: 1px solid #D6D1C4;
}

/* Header section */
.dashboard-header-container {
    padding: 1.5rem 0 1rem 0;
    border-bottom: 1px solid #D6D1C4;
    margin-bottom: 1.5rem;
}

.dashboard-eyebrow {
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #5A6561;
    margin-bottom: 0.25rem;
}

.dashboard-title {
    font-size: 1.85rem;
    font-weight: 700;
    color: #174F4A;
    margin: 0;
    line-height: 1.2;
}

.dashboard-subtitle {
    font-size: 0.95rem;
    color: #4A5652;
    margin-top: 0.35rem;
}

/* Metric Cards */
.mineral-card {
    background-color: #FCFBF6;
    border: 1px solid #D6D1C4;
    border-radius: 6px;
    padding: 1.25rem 1rem;
    margin-bottom: 1rem;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.mineral-card-label {
    font-size: 0.8rem;
    font-weight: 600;
    color: #5A6561;
    margin-bottom: 0.35rem;
}

.mineral-card-value {
    font-size: 2rem;
    font-weight: 700;
    color: #174F4A;
    line-height: 1.1;
}

.mineral-card-hint {
    font-size: 0.75rem;
    color: #6C7A75;
    margin-top: 0.35rem;
}

/* Status Badges */
.mineral-badge {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
}

.badge-available {
    background-color: #E2ECE9;
    color: #1B5E20;
    border: 1px solid #B8D5CD;
}

.badge-attention {
    background-color: #FBF4E4;
    color: #8A6414;
    border: 1px solid #ECD9A9;
}

.badge-unavailable {
    background-color: #F4EAEF;
    color: #5C2438;
    border: 1px solid #DEBCCB;
}

/* Links and actions */
a.mineral-link {
    color: #174F4A;
    text-decoration: underline;
    font-weight: 600;
}

a.mineral-link:hover {
    color: #0E3632;
}

/* Tables styling */
[data-testid="stDataFrame"] {
    border: 1px solid #D6D1C4;
    border-radius: 6px;
    background-color: #FCFBF6;
}
</style>
"""


def inject_editorial_mineral_styles() -> None:
    st.markdown(EDITORIAL_MINERAL_CSS, unsafe_allow_html=True)
