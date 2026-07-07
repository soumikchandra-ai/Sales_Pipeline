import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from datetime import date, timedelta, datetime
from frontend.api_client import api_get

plt.style.use("seaborn-v0_8-whitegrid")


def show_dashboard_page():
    """
    Renders the full Sales Dashboard page.
    Called from app.py when user selects "Dashboard".
    """

    st.title("Sales Dashboard")
    st.markdown(
        "Real-time analytics from your processed sales data. "
        "Run the **Pipeline** page first if you don't see any data here."
    )
    st.markdown("---")


    st.header("Key Performance Indicators")

    with st.spinner("Loading summary..."):
        success, summary_data, status_code = api_get(
            "/dashboard/summary",
            token=st.session_state.get("token")
        )

    if not success:
        if status_code == 0:
            st.error(
                "Cannot connect to the backend server. "
                "Make sure it is running."
            )
        else:
            st.error(f"Failed to load summary: {summary_data}")
        summary_data = {
            "total_revenue" : 0.0,
            "total_tax" : 0.0,
            "total_orders" : 0,
            "avg_order_value" : 0.0,
            "last_updated" : None
        }

    has_data = summary_data.get("total_orders", 0) > 0

    if not has_data:
        st.warning(
            "No processed data available yet. "
            "Go to the **Upload** page to add sales data, "
            "then run the **Pipeline** to process it."
        )

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)

    with kpi1:
        total_rev = summary_data.get("total_revenue", 0.0)
        st.metric(
            label="Total Revenue",
            value=_format_currency(total_rev),
            help="Sum of all final_amount values in processed_sales"
        )

    with kpi2:
        total_tax = summary_data.get("total_tax", 0.0)
        st.metric(
            label="Total Tax Collected",
            value=_format_currency(total_tax),
            help=f"18% GST collected on all processed sales"
        )

    with kpi3:
        total_orders = summary_data.get("total_orders", 0)
        st.metric(
            label="Total Orders",
            value=f"{total_orders:,}",
            help="Total number of records in processed_sales"
        )

    with kpi4:
        avg_order = summary_data.get("avg_order_value", 0.0)
        st.metric(
            label="Avg Order Value",
            value=_format_currency(avg_order),
            help="Average final_amount per processed sale"
        )

    last_updated = summary_data.get("last_updated")
    if last_updated:
        try:
            dt = datetime.fromisoformat(last_updated)
            formatted_time = dt.strftime("%d %b %Y, %H:%M UTC")

            st.caption(f"Last updated: {formatted_time}")
        except Exception:
            st.caption(f"Last updated: {last_updated}")
    else:
        st.caption("Last updated: Never (no processed records yet)")

    st.markdown("---")


    st.header("Revenue Trend")

    filter_col1, filter_col2, filter_col3 = st.columns([2, 2, 3])

    with filter_col1:
        start_date = st.date_input(
            "Start Date",
            value=date.today() - timedelta(days=30),
            max_value=date.today(),
            key="dashboard_start_date",
            help="Show revenue from this date onwards"
        )

    with filter_col2:
        end_date = st.date_input(
            "End Date",
            value=date.today(),
            max_value=date.today(),
            min_value=start_date,
            key="dashboard_end_date",
            help="Show revenue up to this date"
        )
        
    def _set_range_7d():
        st.session_state["dashboard_start_date"] = date.today() - timedelta(days=7)

    def _set_range_30d():
        st.session_state["dashboard_start_date"] = date.today() - timedelta(days=30)

    def _set_range_all():
        st.session_state["dashboard_start_date"] = date(2020, 1, 1)
        
    with filter_col3:
        st.markdown("**Quick ranges:**")
        btn_col1, btn_col2, btn_col3 = st.columns(3)

        with btn_col1:
            st.button("Last 7d", key="range_7d", on_click=_set_range_7d)

        with btn_col2:
            st.button("Last 30d", key="range_30d", on_click=_set_range_30d)

        with btn_col3:
            st.button("All time", key="range_all", on_click=_set_range_all)

    if start_date > end_date:
        st.error("Start date must be before end date.")
        st.stop()


    with st.spinner("Loading revenue trend..."):
        trend_success, trend_data, trend_status = api_get(
            "/dashboard/revenue-trend",
            token=st.session_state.get("token"),
            params={
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date"  : end_date.strftime("%Y-%m-%d")
            }
        )

    if not trend_success:
        if trend_status == 0:
            st.error("Cannot connect to backend server.")
        else:
            st.error(f"Failed to load trend data: {trend_data}")

    elif len(trend_data) == 0:
        st.info(
            f"No revenue data found between "
            f"**{start_date.strftime('%d %b %Y')}** and "
            f"**{end_date.strftime('%d %b %Y')}**. "
            "Try expanding the date range or run the pipeline first."
        )

    else:
        dates = [row["date"] for row in trend_data]
        revenues = [row["revenue"] for row in trend_data]

        fig = _build_revenue_chart(dates, revenues, start_date, end_date)
        st.pyplot(fig)

        plt.close(fig)

        with st.expander("View raw trend data"):
            df_trend = pd.DataFrame(trend_data)
            df_trend.columns = ["Date", "Revenue (Rs.)", "Orders"]
            df_trend["Revenue (Rs.)"] = df_trend["Revenue (Rs.)"].apply(
                lambda x: f"Rs.{x:,.2f}"
            )
            st.dataframe(df_trend, use_container_width=True, hide_index=True)

    st.markdown("---")


    st.header("Category Breakdown")

    with st.spinner("Loading category data..."):
        cat_success, cat_data, _ = api_get(
            "/sales/raw",
            token=st.session_state.get("token"),
            params={"status": "processed"}
        )

    if cat_success and cat_data and len(cat_data) > 0:
        df_cat = pd.DataFrame(cat_data)

        if "category" in df_cat.columns and "price" in df_cat.columns:
            df_cat["revenue"] = df_cat["qty"] * df_cat["price"]
            cat_summary = (
                df_cat.groupby("category")["revenue"]
                .sum()
                .round(2)
                .sort_values(ascending=False)
                .reset_index()
            )

            cat_summary.columns = ["Category", "Revenue (Rs.)"]

            fig2, ax2 = plt.subplots(figsize=(10, 4))

            bars = ax2.bar(
                cat_summary["Category"],
                cat_summary["Revenue (Rs.)"],
                color=plt.cm.Set3.colors[:len(cat_summary)],
                edgecolor="grey",
                linewidth=0.5
            )

            for bar in bars:
                height = bar.get_height()
                ax2.text(
                    bar.get_x() + bar.get_width() / 2.,
                    height + (height * 0.01),
                    f"Rs.{height:,.0f}",
                    ha="center", va="bottom",
                    fontsize=9, fontweight="bold"
                )

            ax2.set_title("Revenue by Category", fontsize=14, fontweight="bold")
            ax2.set_xlabel("Category", fontsize=11)
            ax2.set_ylabel("Revenue (Rs.)", fontsize=11)
            ax2.yaxis.set_major_formatter(
                mticker.FuncFormatter(lambda x, _: f"Rs.{x:,.0f}")
            )
            plt.xticks(rotation=30, ha="right")
            plt.tight_layout()

            st.pyplot(fig2)
            plt.close(fig2)

            cat_display = cat_summary.copy()
            cat_display["Revenue (Rs.)"] = cat_display["Revenue (Rs.)"].apply(
                lambda x: f"Rs.{x:,.2f}"
            )
            st.dataframe(cat_display, use_container_width=True, hide_index=True)

    elif not cat_success:
        st.error("Failed to load category data.")
    else:
        st.info("No category data available yet.")



def _format_currency(amount: float) -> str:
    """
    Formats a number as Indian currency with Rs. symbol.
    Returns:
        Formatted string like "Rs.1,23,456.78"
    """
    if amount == 0:
        return "Rs.0.00"

    amount = round(amount, 2)
    integer_part = int(amount)
    decimal_part = round(amount - integer_part, 2)

    s = str(integer_part)

    if len(s) <= 3:
        formatted = s
    else:
        last_three = s[-3:]
        remaining = s[:-3]
        groups = []
        while remaining:
            groups.append(remaining[-2:])
            remaining = remaining[:-2]
        groups.reverse()
        formatted = ",".join(groups) + "," + last_three
        formatted = formatted.lstrip(",")

    decimal_str = f"{decimal_part:.2f}"[1:]

    return f"Rs.{formatted}{decimal_str}"


def _build_revenue_chart(
    dates: list,
    revenues: list,
    start_date,
    end_date
):
    """
    Builds a matplotlib revenue trend line chart.
    """

    fig, ax = plt.subplots(figsize=(12, 5))

    ax.plot(
        dates,
        revenues,
        marker="o",
        color="#2196F3",
        linewidth=2.5,
        markersize=7,
        markerfacecolor="white",
        markeredgecolor="#2196F3",
        markeredgewidth=2,
        label="Daily Revenue",
        zorder=3
    )

    ax.fill_between(
        dates,
        revenues,
        alpha=0.1,
        color="#2196F3",
        zorder=2
    )

    plt.xticks(rotation=45, ha="right", fontsize=9)

    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"Rs.{x:,.0f}")
    )

    ax.grid(True, alpha=0.3, linestyle="--", linewidth=0.7)

    ax.set_title(
        "Daily Revenue Trend",
        fontsize=16,
        fontweight="bold",
        pad=15
    )
    ax.set_xlabel("Date", fontsize=12, labelpad=10)
    ax.set_ylabel("Revenue (Rs.)", fontsize=12, labelpad=10)

    date_range_str = (
        f"{start_date.strftime('%d %b %Y')} — "
        f"{end_date.strftime('%d %b %Y')}"
    )
    ax.set_title(
        date_range_str,
        fontsize=10,
        color="grey",
        loc="right"
    )

    ax.set_title("Daily Revenue Trend", fontsize=16, fontweight="bold", pad=15)
    fig.text(
        0.99, 0.98,
        date_range_str,
        ha="right", va="top",
        fontsize=9, color="grey",
        transform=fig.transFigure
    )

    if len(dates) <= 20:
        for i, (d, r) in enumerate(zip(dates, revenues)):
            ax.annotate(
                f"Rs.{r:,.0f}",
                xy=(d, r),
                xytext=(0, 12),
                textcoords="offset points",
                ha="center",
                fontsize=8,
                color="#1565C0",
                fontweight="bold"
            )

    total = sum(revenues)
    ax.text(
        0.02, 0.97,
        f"Total: Rs.{total:,.2f}",
        transform=ax.transAxes,
        fontsize=11,
        fontweight="bold",
        verticalalignment="top",
        color="#1565C0",
        bbox=dict(
            boxstyle="round,pad=0.4",
            facecolor="lightblue",
            alpha=0.7,
            edgecolor="#1565C0"
        )
    )

    plt.tight_layout()

    return fig