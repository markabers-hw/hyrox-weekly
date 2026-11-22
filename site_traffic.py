"""
Website traffic section for the dashboard's Analytics page.

Data comes from the traffic_* Postgres functions (see migrations/2026-11-22_page_views.sql), which are fed by
the /api/track Netlify function. Aggregation happens in the database because Supabase caps each REST response
at 1000 rows, so the raw page_views rows are never pulled into Python.
"""

from typing import Any, Callable, Optional

import altair as alt
import pandas as pd
import streamlit as st

# rpc(function_name, args) -> list of row dicts, or None if the call failed
RpcFn = Callable[[str, dict[str, Any]], Optional[list[dict[str, Any]]]]

# traffic_daily returns one row per day, so the longest range must stay under Supabase's 1000-row cap.
RANGES: dict[str, int] = {
    "Last 7 days": 7,
    "Last 30 days": 30,
    "Last 90 days": 90,
    "Last year": 365,
    "Longest (1000 days)": 1000,
}

def _day_axis(span_days: int) -> alt.Axis:
    """Date axis shared by every chart: one style ("Nov 22"), and one tick per day on short ranges
    (Altair otherwise puts a tick every few hours there, repeating each date label)."""
    if span_days <= 14:
        return alt.Axis(format="%b %d", tickCount="day", labelOverlap=True)
    return alt.Axis(format="%b %d", labelOverlap=True)


EDITION_COLOR = "#ef4444"
VIEWS_COLOR = "#2563eb"
VISITORS_COLOR = "#f59e0b"
SIGNUPS_COLOR = "#16a34a"


@st.cache_data(ttl=300, show_spinner=False)
def _load_traffic(_rpc: RpcFn, days: int, tz: str) -> dict[str, list[dict[str, Any]]]:
    """Fetch every traffic dataset for one range. Raises if any call fails, so a failure is never cached."""
    calls: dict[str, tuple[str, dict[str, Any]]] = {
        "daily": ("traffic_daily", {"p_days": days, "p_tz": tz}),
        "signups": ("traffic_signups_daily", {"p_days": days, "p_tz": tz}),
        "pages": ("traffic_breakdown", {"p_dimension": "path", "p_days": days, "p_limit": 15}),
        "referrers": ("traffic_breakdown", {"p_dimension": "referrer", "p_days": days, "p_limit": 15}),
        "countries": ("traffic_breakdown", {"p_dimension": "country", "p_days": days, "p_limit": 15}),
        "devices": ("traffic_breakdown", {"p_dimension": "device", "p_days": days, "p_limit": 5}),
        "campaigns": ("traffic_breakdown", {"p_dimension": "utm_campaign", "p_days": days, "p_limit": 10}),
    }
    out: dict[str, list[dict[str, Any]]] = {}
    for key, (function_name, args) in calls.items():
        rows = _rpc(function_name, args)
        if rows is None:
            raise RuntimeError(
                f"{function_name} failed. Has migrations/2026-11-22_page_views.sql been applied?"
            )
        out[key] = rows
    return out


def _daily_frame(data: dict[str, list[dict[str, Any]]], days: int, tz: str) -> pd.DataFrame:
    """One row per local day (zero-filled) with views, visitors and signups. Empty if there is no traffic."""
    if not data["daily"]:
        return pd.DataFrame()

    views = pd.DataFrame(data["daily"])
    views["day"] = pd.to_datetime(views["day"])
    frame = views.set_index("day")[["views", "visitors"]]

    if data["signups"]:
        signups = pd.DataFrame(data["signups"])
        signups["day"] = pd.to_datetime(signups["day"])
        frame = frame.join(signups.set_index("day")[["signups"]], how="outer")
    else:
        frame["signups"] = 0

    today = pd.Timestamp.now(tz=tz).normalize().tz_localize(None)
    start = max(today - pd.Timedelta(days=days - 1), frame.index.min())
    frame = frame.reindex(pd.date_range(start, today), fill_value=0).fillna(0).astype(int)
    frame.index.name = "day"
    return frame


def _edition_days(editions: list[dict[str, Any]], tz: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Publish dates of editions that fall inside the chart range, as local calendar days."""
    rows: list[dict[str, Any]] = []
    for edition in editions:
        raw = edition.get("publish_date")
        if not raw:
            continue
        text = str(raw)
        if len(text) == 10:  # plain date: already a calendar day, no timezone shift
            stamp = pd.to_datetime(text, errors="coerce")
        else:
            stamp = pd.to_datetime(text, utc=True, errors="coerce")
            if pd.notna(stamp):
                stamp = stamp.tz_convert(tz).tz_localize(None)
        if pd.isna(stamp):
            continue
        day = stamp.normalize()
        if start <= day <= end:
            rows.append({"day": day, "label": f"Edition #{edition.get('edition_number')}"})
    return pd.DataFrame(rows, columns=["day", "label"])


def _with_edition_rules(chart: alt.Chart, editions_df: pd.DataFrame) -> alt.LayerChart | alt.Chart:
    """Overlay a dashed vertical line on each edition publish date."""
    if editions_df.empty:
        return chart
    rules = (
        alt.Chart(editions_df)
        .mark_rule(strokeDash=[4, 4], color=EDITION_COLOR, opacity=0.7)
        .encode(x="day:T", tooltip=[alt.Tooltip("label:N", title="Published")])
    )
    return chart + rules


def _breakdown_table(rows: list[dict[str, Any]], label_name: str) -> None:
    """Show one top-N table, or a short note if it has no data."""
    if not rows:
        st.caption("No data yet.")
        return
    table = pd.DataFrame(rows).rename(columns={"label": label_name, "views": "Views", "visitors": "Visitors"})
    st.dataframe(table, hide_index=True, width="stretch")


def render_site_traffic(rpc: RpcFn, editions: list[dict[str, Any]], tz: str) -> None:
    """Render the website traffic section: summary, daily trend, weekly table and top-N breakdowns."""
    controls, refresh = st.columns([5, 1])
    with controls:
        label = st.radio("Range", list(RANGES), index=2, horizontal=True, key="traffic_range")
    with refresh:
        if st.button("Refresh", key="traffic_refresh"):
            _load_traffic.clear()
    days = RANGES[label]

    try:
        data = _load_traffic(rpc, days, tz)
    except RuntimeError as error:
        st.error(str(error))
        return

    frame = _daily_frame(data, days, tz)
    if frame.empty:
        st.info("No traffic recorded in this range yet. Tracking starts once /hw.js is live on the site.")
        return

    # --- Summary ---
    total_views = int(frame["views"].sum())
    total_visitors = int(frame["visitors"].sum())
    total_signups = int(frame["signups"].sum())
    span_days = len(frame)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Page views", f"{total_views:,}")
    m2.metric("Visitor-days", f"{total_visitors:,}")
    m3.metric("Avg views / day", f"{total_views / span_days:,.1f}")
    m4.metric("New signups", f"{total_signups:,}")

    editions_df = _edition_days(editions, tz, frame.index.min(), frame.index.max())

    # --- Daily trend (views and visitors, then signups on the same time axis) ---
    plot = frame.reset_index()
    long = plot.melt(id_vars="day", value_vars=["views", "visitors"], var_name="metric", value_name="count")
    trend = (
        alt.Chart(long)
        .mark_line(point=True)
        .encode(
            x=alt.X("day:T", title=None, axis=_day_axis(span_days)),
            y=alt.Y("count:Q", title=None),
            color=alt.Color(
                "metric:N",
                title=None,
                scale=alt.Scale(domain=["views", "visitors"], range=[VIEWS_COLOR, VISITORS_COLOR]),
                legend=alt.Legend(orient="top"),  # keeps both charts the same width so their days line up
            ),
            tooltip=[alt.Tooltip("day:T", title="Day"), "metric:N", "count:Q"],
        )
        .properties(height=240)
    )
    st.altair_chart(_with_edition_rules(trend, editions_df), width="stretch")

    signups_chart = (
        alt.Chart(plot)
        .mark_bar(color=SIGNUPS_COLOR)
        .encode(
            x=alt.X("day:T", title=None, axis=_day_axis(span_days)),
            y=alt.Y(
                "signups:Q",
                title="New signups",
                axis=alt.Axis(tickMinStep=1, format="d"),
                scale=alt.Scale(domain=[0, max(1, int(frame["signups"].max()))]),
            ),
            tooltip=[alt.Tooltip("day:T", title="Day"), "signups:Q"],
        )
        .properties(height=110)
    )
    st.altair_chart(_with_edition_rules(signups_chart, editions_df), width="stretch")
    st.caption("Dashed red lines mark edition publish dates.")

    # --- Weekly table (weeks start Monday) ---
    st.markdown("#### By week")
    week_start = frame.index - pd.to_timedelta(frame.index.weekday, unit="D")
    weekly = frame.groupby(week_start)[["views", "visitors", "signups"]].sum().sort_index(ascending=False)
    weekly.index = weekly.index.strftime("%Y-%m-%d")
    weekly.index.name = "Week of"
    weekly.columns = ["Views", "Visitor-days", "Signups"]
    st.dataframe(weekly, width="stretch")

    # --- Breakdowns ---
    left, right = st.columns(2)
    with left:
        st.markdown("#### Top pages")
        _breakdown_table(data["pages"], "Page")
        st.markdown("#### Countries")
        _breakdown_table(data["countries"], "Country")
    with right:
        st.markdown("#### Referrers")
        _breakdown_table(data["referrers"], "Referrer")
        st.markdown("#### Devices")
        _breakdown_table(data["devices"], "Device")

    tagged = [row for row in data["campaigns"] if row["label"] != "(none)"]
    if tagged:
        st.markdown("#### Campaigns (utm_campaign)")
        _breakdown_table(tagged, "Campaign")

    st.caption(
        "Visitors are counted per day, so a returning visitor counts once for each day they visit "
        "(hence 'visitor-days'). Tracking is cookieless, honors Do Not Track, and skips bots and preview "
        "deploys, so totals read lower than Netlify's server-side numbers."
    )
