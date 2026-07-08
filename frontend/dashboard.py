import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import plotly.graph_objects as go
from datetime import date, timedelta, datetime
from frontend.api_client import api_get

try:
    plt.style.use("seaborn-v0_8-whitegrid")
except OSError:
    try:
        plt.style.use("seaborn-whitegrid")
    except OSError:
        pass

def show_dashboard_page():
    """
    Renders the complete Sales Dashboard.
    Called from app.py when user selects Dashboard.
    """

    st.title("Sales Dashboard")
    st.markdown(
        "Real-time analytics from your processed sales data. "
        "Run the **Pipeline** page first if you don't see any data here."
    )

    st.divider()
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
            "avg_order_value": 0.0,
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
        st.metric(
            label="Total Revenue",
            value=_format_currency(summary_data.get("total_revenue", 0.0)),
            help="Sum of all final_amount in processed_sales"
        )
    with kpi2:
        st.metric(
            label="Tax Collected",
            value=_format_currency(summary_data.get("total_tax", 0.0)),
            help="Total GST (18%) collected"
        )
    with kpi3:
        st.metric(
            label="Total Orders",
            value=f"{summary_data.get('total_orders', 0):,}",
            help="Count of processed sales records"
        )
    with kpi4:
        st.metric(
            label="Avg Order Value",
            value=_format_currency(summary_data.get("avg_order_value", 0.0)),
            help="Average final_amount per sale"
        )

    last_updated = summary_data.get("last_updated")
    if last_updated:
        try:
            dt = datetime.fromisoformat(str(last_updated))
            st.caption(f"Last updated: {dt.strftime('%d %b %Y, %H:%M UTC')}")
        except Exception:
            st.caption(f"Last updated: {last_updated}")
    else:
        st.caption("Last updated: Never")

    st.divider()
    st.header("Revenue Trend")

    if "filter_start_date" not in st.session_state:
        st.session_state["filter_start_date"] = date.today() - timedelta(days=30)
    if "filter_end_date" not in st.session_state:
        st.session_state["filter_end_date"] = date.today()

    st.markdown("**Quick ranges:**")
    btn_col1, btn_col2, btn_col3 = st.columns(3)
    with btn_col1:
        if st.button("Last 7 days", key="range_7d", use_container_width=True):
            st.session_state["filter_start_date"] = date.today() - timedelta(days=7)
            st.session_state["filter_end_date"]   = date.today()
    with btn_col2:
        if st.button("Last 30 days", key="range_30d", use_container_width=True):
            st.session_state["filter_start_date"] = date.today() - timedelta(days=30)
            st.session_state["filter_end_date"]   = date.today()
    with btn_col3:
        if st.button("All time", key="range_all", use_container_width=True):
            st.session_state["filter_start_date"] = date(2020, 1, 1)
            st.session_state["filter_end_date"]   = date.today()

    dcol1, dcol2 = st.columns(2)
    with dcol1:
        start_date = st.date_input(
            "Start Date",
            value=st.session_state["filter_start_date"],
            max_value=date.today(),
            key="widget_start_date"
        )
    with dcol2:
        end_date = st.date_input(
            "End Date",
            value=st.session_state["filter_end_date"],
            max_value=date.today(),
            min_value=start_date,
            key="widget_end_date"
        )
    st.session_state["filter_start_date"] = start_date
    st.session_state["filter_end_date"]   = end_date

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
        st.error(
            f"Failed to load trend data: {trend_data}"
            if trend_status != 0
            else "Cannot connect to backend server."
        )
    elif not trend_data:
        st.info(
            f"No revenue data found between "
            f"**{start_date.strftime('%d %b %Y')}** and "
            f"**{end_date.strftime('%d %b %Y')}**."
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

    st.divider()

    chart_col_left, chart_col_right = st.columns(2)
    
    with chart_col_left:
        st.subheader("Top Products by Revenue")

        product_limit = st.slider(
            "Number of products to show",
            min_value=5,
            max_value=20,
            value=10,
            step=1,
            key="product_limit_slider",
            help="Drag to show more or fewer products in the chart"
        )
        
        with st.spinner("Loading top products..."):
            prod_success, prod_data, prod_status = api_get(
                "/dashboard/top-products",
                token=st.session_state.get("token"),
                params={"limit": product_limit}
            )

        if not prod_success:
            st.error(
                f"Failed to load products: {prod_data}"
                if prod_status != 0
                else "Cannot connect to backend."
            )
        elif not prod_data:
            st.info("No product data available yet.")
        else:
            fig_bar = _build_top_products_chart(prod_data)
            st.plotly_chart(fig_bar, use_container_width=True)
            
    with chart_col_right:
        st.subheader("Revenue by Category")

        with st.spinner("Loading category data..."):
            cat_success, cat_data, cat_status = api_get(
                "/dashboard/category-breakdown",
                token=st.session_state.get("token")
            )

        if not cat_success:
            st.error(
                f"Failed to load categories: {cat_data}"
                if cat_status != 0
                else "Cannot connect to backend."
            )
        elif not cat_data:
            st.info("No category data available yet.")
        else:
            fig_donut = _build_category_donut(cat_data)
            st.plotly_chart(fig_donut, use_container_width=True)

            df_cat = pd.DataFrame(cat_data)
            df_cat_display = df_cat[
                ["category", "revenue", "percentage", "order_count"]
            ].copy()
            df_cat_display.columns = [
                "Category", "Revenue (Rs.)", "Share (%)", "Orders"
            ]
            df_cat_display["Revenue (Rs.)"] = df_cat_display["Revenue (Rs.)"].apply(
                lambda x: f"Rs.{x:,.2f}"
            )
            df_cat_display["Share (%)"] = df_cat_display["Share (%)"].apply(
                lambda x: f"{x:.2f}%"
            )
            st.dataframe(
                df_cat_display,
                use_container_width=True,
                hide_index=True
            )

    st.divider()
    st.header("Processed Sales Data")
    st.markdown(
        "Complete record of all sales that have been through the ETL pipeline. "
        "Download as CSV for offline analysis."
    )

    with st.spinner("Loading processed sales data..."):
        table_success, table_data, table_status = api_get(
            "/sales/processed",
            token=st.session_state.get("token")
        )

    if not table_success:
        st.error(
            f"Failed to load data: {table_data}"
            if table_status != 0
            else "Cannot connect to backend."
        )
    elif not table_data:
        st.info("No processed records to display.")
    else:
        df_processed = pd.DataFrame(table_data)
        raw_success, raw_data, _ = api_get(
            "/sales/raw",
            token=st.session_state.get("token"),
            params={"status": "processed"}
        )

        if raw_success and raw_data:
            df_raw = pd.DataFrame(raw_data)        
            df_combined = df_processed.merge(
                df_raw[["id", "date", "product", "category", "qty", "price"]],
                left_on="raw_id",
                right_on="id",
                how="left",
                suffixes=("_proc", "_raw")            
            )        
        else:
            df_combined = df_processed
        if "processed_at" in df_combined.columns:
            df_combined = df_combined.sort_values(
                "processed_at",
                ascending=False            
            ).reset_index(drop=True)
        display_col_map = {
            "date" : "Sale Date",
            "product" : "Product",
            "category" : "Category",
            "qty" : "Qty",
            "price" : "Unit Price (Rs.)",
            "total" : "Subtotal (Rs.)",
            "tax" : "Tax (Rs.)",
            "discount" : "Discount (Rs.)",
            "final_amount" : "Final Amount (Rs.)",
            "processed_at" : "Processed At"
        }
        available = [c for c in display_col_map if c in df_combined.columns]
        df_display = df_combined[available].rename(columns=display_col_map)
        if "Sale Date" in df_display.columns:
            df_display["Sale Date"] = pd.to_datetime(
                df_display["Sale Date"], errors="coerce"
            ).dt.strftime("%d %b %Y")

        if "Processed At" in df_display.columns:
            df_display["Processed At"] = pd.to_datetime(
                df_display["Processed At"], errors="coerce"
            ).dt.strftime("%d %b %Y, %H:%M")
        tbl1, tbl2, tbl3 = st.columns(3)
        with tbl1:
            st.metric("Records", len(df_display))
        with tbl2:
            if "final_amount" in df_combined.columns:
                st.metric(
                    "Total Revenue",
                    f"Rs.{df_combined['final_amount'].sum():,.2f}"
                )
        with tbl3:
            if "tax" in df_combined.columns:
                st.metric(
                    "Total Tax",
                    f"Rs.{df_combined['tax'].sum():,.2f}"
                )

        st.dataframe(
            df_display,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Unit Price (Rs.)" : st.column_config.NumberColumn(
                    "Unit Price (Rs.)",
                    format="Rs. %.2f"
                ),
                "Subtotal (Rs.)" : st.column_config.NumberColumn(
                    "Subtotal (Rs.)",
                    format="Rs. %.2f"
                ),
                "Tax (Rs.)" : st.column_config.NumberColumn(
                    "Tax (Rs.)",
                    format="Rs. %.2f"
                ),
                "Discount (Rs.)" : st.column_config.NumberColumn(
                    "Discount (Rs.)",
                    format="Rs. %.2f"
                ),
                "Final Amount (Rs.)": st.column_config.NumberColumn(
                    "Final Amount (Rs.)",
                    format="Rs. %.2f"
                ),
                "Qty" : st.column_config.NumberColumn(
                    "Qty",
                    format="%d"
                )
            }
        )

        # CSV Download Button
        csv_df = df_display.copy()
        csv_string = csv_df.to_csv(index=False)
        download_filename = (
            f"sales_report_{date.today().strftime('%Y-%m-%d')}.csv"
        )
        st.download_button(
            label="⬇️ Download Report as CSV",
            data=csv_string,    
            file_name=download_filename,
            mime="text/csv",    
            type="primary",
            use_container_width=False,
            key="download_csv_btn"
        )

def _build_top_products_chart(prod_data: list) -> go.Figure:
    """
    Builds a horizontal Plotly bar chart of top products by revenue.
    """
    prod_data_sorted = sorted(prod_data, key=lambda x: x["revenue"])
    products = [row["product"] for row in prod_data_sorted]
    revenues = [row["revenue"] for row in prod_data_sorted]
    units = [row["units_sold"] for row in prod_data_sorted]
    cats = [row.get("category", "N/A") for row in prod_data_sorted]
    colors = revenues
    fig = go.Figure(go.Bar(
        x=revenues,
        y=products,
        orientation="h",
        marker=dict(
            color=colors,
            colorscale="Blues",
            showscale=True,
            colorbar=dict(
                title=dict(
                    text="Revenue<br>(Rs.)"
                )
            )
        ),
        text=[f"Rs.{r:,.0f}" for r in revenues],
        textposition="outside",
        customdata=list(zip(units, cats)),
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Revenue: Rs.%{x:,.2f}<br>"
            "Units Sold: %{customdata[0]}<br>"
            "Category: %{customdata[1]}"
            "<extra></extra>"
        ),
        name=""
    ))

    fig.update_layout(
        title=dict(
            text="Top Products by Revenue",
            font=dict(size=16, color="#1a1a1a"),
            x=0.0
        ),
        xaxis=dict(
            title="Revenue (Rs.)",
            showgrid=True,
            gridcolor="rgba(0,0,0,0.1)",
            gridwidth=1,
            tickformat=",.0f",
        ),
        yaxis=dict(
            title="",
            showgrid=False,
            tickfont=dict(size=11)
        ),
        height=max(350, len(prod_data) * 35),
        margin=dict(l=10, r=80, t=50, b=40),
        plot_bgcolor="white",
        showlegend=False
    )

    return fig

def _build_category_donut(cat_data: list) -> go.Figure:
    """
    Builds a Plotly donut chart for category revenue breakdown.
    """
    categories  = [row["category"] for row in cat_data]
    revenues = [row["revenue"] for row in cat_data]
    percentages = [row["percentage"] for row in cat_data]
    order_counts = [row["order_count"] for row in cat_data]

    fig = go.Figure(go.Pie(
        labels=categories,
        values=revenues,
        hole=0.45,
        textinfo="label+percent",
        textposition="outside",
        customdata=list(zip(revenues, percentages, order_counts)),
        hovertemplate=(
            "<b>%{label}</b><br>"
            "Revenue: Rs.%{customdata[0]:,.2f}<br>"
            "Share: %{customdata[1]:.2f}%%<br>"
            "Orders: %{customdata[2]}"
            "<extra></extra>"
        ),
        marker=dict(
            colors=[
                "#1565C0", "#1976D2", "#1E88E5",
                "#2196F3", "#42A5F5", "#64B5F6",
                "#90CAF9", "#BBDEFB", "#E3F2FD", "#E8EAF6"
            ]
        ),
        pull=[0.05] + [0] * (len(categories) - 1),
    ))

    fig.update_layout(
        title=dict(
            text="Revenue by Category",
            font=dict(size=16, color="#1a1a1a"),
            x=0.0
        ),
        legend=dict(
            orientation="v",
            x=1.02,
            y=0.5,
            xanchor="left",
            yanchor="middle"
        ),
        height=420,
        margin=dict(l=10, r=120, t=50, b=10),
        showlegend=True
    )
    total_rev = sum(revenues)
    fig.add_annotation(
        text=f"<b>Total</b><br>Rs.{total_rev:,.0f}",
        x=0.5, y=0.5,
        font=dict(size=14, color="#1a1a1a"),
        showarrow=False,
        xref="paper", yref="paper"
    )

    return fig


def _build_revenue_chart(dates, revenues, start_date, end_date):
    """
    Builds a matplotlib revenue trend line chart.
    Uses numeric x positions to avoid fill_between issues with strings.
    Caller MUST call plt.close(fig) after st.pyplot(fig).
    """
    x_numeric = list(range(len(dates)))
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(
        x_numeric, revenues,
        marker="o", color="#2196F3", linewidth=2.5,
        markersize=7, markerfacecolor="white",
        markeredgecolor="#2196F3", markeredgewidth=2,
        label="Daily Revenue", zorder=3
    )
    ax.fill_between(x_numeric, revenues, alpha=0.1, color="#2196F3", zorder=2)

    ax.set_xticks(x_numeric)
    ax.set_xticklabels(dates, rotation=45, ha="right", fontsize=9)

    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"Rs.{x:,.0f}")
    )
    ax.grid(True, alpha=0.3, linestyle="--", linewidth=0.7)
    ax.set_title("Daily Revenue Trend", fontsize=16, fontweight="bold", pad=15)
    ax.set_xlabel("Date", fontsize=12, labelpad=10)
    ax.set_ylabel("Revenue (Rs.)", fontsize=12, labelpad=10)

    date_range_str = (
        f"{start_date.strftime('%d %b %Y')} — {end_date.strftime('%d %b %Y')}"
    )
    fig.text(
        0.99, 0.98, date_range_str,
        ha="right", va="top", fontsize=9, color="grey",
        transform=fig.transFigure
    )

    if len(dates) <= 20:
        for x, r in zip(x_numeric, revenues):
            ax.annotate(
                f"Rs.{r:,.0f}", xy=(x, r), xytext=(0, 12),
                textcoords="offset points", ha="center",
                fontsize=8, color="#1565C0", fontweight="bold"
            )

    total = sum(revenues)
    ax.text(
        0.02, 0.97, f"Total: Rs.{total:,.2f}",
        transform=ax.transAxes, fontsize=11, fontweight="bold",
        verticalalignment="top", color="#1565C0",
        bbox=dict(
            boxstyle="round,pad=0.4", facecolor="lightblue",
            alpha=0.7, edgecolor="#1565C0"
        )
    )

    plt.tight_layout()
    return fig

def _format_currency(amount: float) -> str:
    """
    Formats a float as Indian currency string.
    123456.78 → "Rs.1,23,456.78"
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