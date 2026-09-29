"""Page 3: Deterministic Match Insights."""
import pandas as pd
import streamlit as st

from dashboard.api_client import DashboardAPIClient, DashboardAPIError
from dashboard.auth import ensure_authenticated_dashboard_session
from dashboard.ui.charts import create_match_distribution_chart
from dashboard.ui.components import (
    render_expired_session_screen,
    render_page_header,
    render_sidebar_workspace_link,
)
from dashboard.ui.styles import inject_editorial_mineral_styles


def render_matches_view() -> None:
    inject_editorial_mineral_styles()
    render_sidebar_workspace_link()

    token = ensure_authenticated_dashboard_session()
    if not token:
        render_expired_session_screen()
        return

    api_client = DashboardAPIClient()

    # Sidebar Filters
    st.sidebar.markdown("### Match Filters")
    try:
        jobs_data = api_client.get_jobs(token)
        job_options = {"All Jobs": None}
        for j in jobs_data.jobs:
            job_options[f"{j.title}"] = str(j.job_id)
    except Exception:
        job_options = {"All Jobs": None}

    selected_job_label = st.sidebar.selectbox("Filter by Job", options=list(job_options.keys()))
    selected_job_id = job_options[selected_job_label]

    tier_option = st.sidebar.selectbox("Confidence Tier", ["All Tiers", "HIGH", "MEDIUM", "LOW"])
    selected_tier = None if tier_option == "All Tiers" else tier_option

    gap_option = st.sidebar.selectbox("Must-Have Requirement Gaps", ["All", "Only with Must-Have Gaps", "Full Must-Have Coverage"])
    has_gaps = True if gap_option == "Only with Must-Have Gaps" else False if gap_option == "Full Must-Have Coverage" else None

    try:
        matches_data = api_client.get_matches(
            token=token,
            job_id=selected_job_id,
            confidence_tier=selected_tier,
            has_must_have_gaps=has_gaps,
        )
    except DashboardAPIError as e:
        if e.status_code == 401:
            render_expired_session_screen()
            return
        st.error(f"Error loading match insights: {e.message}")
        return

    render_page_header(
        title="Resume Requirement Alignment",
        eyebrow="Deterministic Matching Insights",
        subtitle="Objective compatibility scores and skill gap distribution. (Interview scores are strictly separate).",
        generated_at=matches_data.metadata.generated_at,
    )

    matches = matches_data.matches
    if not matches:
        st.info("No matching results found for the selected criteria.")
        return

    # 1. Match Score Distribution
    df = pd.DataFrame([m.model_dump() for m in matches])
    col_chart, col_stats = st.columns([3, 2])

    with col_chart:
        st.markdown("### Score Distribution")
        chart = create_match_distribution_chart(df)
        st.altair_chart(chart, use_container_width=True)

    with col_stats:
        st.markdown("### Summary Metrics")
        avg_score = df["match_score"].mean()
        high_conf = len(df[df["confidence_tier"] == "HIGH"])
        gap_count = len(df[df["missing_must_have_count"] > 0])

        st.metric("Average Match Score", f"{avg_score:.1f}%")
        st.metric("High Confidence Matches", f"{high_conf} / {len(df)}")
        st.metric("Candidates with Missing Must-Haves", f"{gap_count}")

    # 2. Match Details Table
    st.markdown("### Candidate Match Alignments")
    table_records = [
        {
            "Candidate": m.candidate_display_name,
            "Job Title": m.job_title,
            "Match Score (%)": f"{m.match_score:.1f}%",
            "Confidence": m.confidence_tier,
            "Must-Have Coverage": f"{m.must_have_coverage:.0f}%",
            "Preferred Coverage": f"{m.preferred_coverage:.0f}%",
            "Missing Must-Haves": m.missing_must_have_count,
            "Missing Preferred": m.missing_preferred_count,
            "Match Date": m.match_created_at.strftime("%Y-%m-%d"),
        }
        for m in matches
    ]
    st.dataframe(pd.DataFrame(table_records), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    render_matches_view()
