"""Editorial Mineral chart helpers using Altair."""
import altair as alt
import pandas as pd


def create_pipeline_horizontal_bar_chart(df: pd.DataFrame) -> alt.Chart:
    """
    Creates a restrained horizontal stage bar chart using Editorial Mineral colors (#174F4A).
    """
    chart = (
        alt.Chart(df)
        .mark_bar(color="#174F4A", cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
        .encode(
            x=alt.X("count:Q", title="Candidate Count", axis=alt.Axis(grid=True, gridColor="#E2DDD2")),
            y=alt.Y("stage:N", title=None, sort=None, axis=alt.Axis(labelFontSize=13, labelColor="#202927")),
            tooltip=["stage", "count", "description"],
        )
        .properties(height=260)
        .configure_view(strokeWidth=0)
    )
    return chart


def create_match_distribution_chart(df: pd.DataFrame) -> alt.Chart:
    """
    Creates a score distribution histogram.
    """
    chart = (
        alt.Chart(df)
        .mark_bar(color="#2F6690", cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("match_score:Q", bin=alt.Bin(maxbins=10), title="Compatibility Score (%)"),
            y=alt.Y("count()", title="Candidate Count"),
            tooltip=["count()"],
        )
        .properties(height=220)
        .configure_view(strokeWidth=0)
    )
    return chart
