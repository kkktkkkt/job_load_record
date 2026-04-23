"""
Activity Tracker ダッシュボード
起動: streamlit run dashboard.py
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

DB_PATH = Path(__file__).parent / "activity.db"

st.set_page_config(
    page_title="Activity Tracker",
    page_icon="🖥️",
    layout="wide",
)

# ─── データ読み込み ────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_data(start: datetime, end: datetime) -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame()
    with sqlite3.connect(DB_PATH) as conn:
        df = pd.read_sql_query(
            """
            SELECT timestamp, app_name, window_title, duration_seconds
            FROM activity
            WHERE timestamp >= ? AND timestamp < ?
            ORDER BY timestamp
            """,
            conn,
            params=(start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")),
        )
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["hour"] = df["timestamp"].dt.hour
    df["weekday"] = df["timestamp"].dt.day_name()
    return df


# ─── サイドバー: 期間選択 ──────────────────────────────────────

st.sidebar.title("⚙️ フィルター")
view_mode = st.sidebar.radio("表示期間", ["日", "週", "月"], horizontal=True)

today = datetime.now().date()

if view_mode == "日":
    selected = st.sidebar.date_input("日付を選択", today)
    start_dt = datetime.combine(selected, datetime.min.time())
    end_dt = start_dt + timedelta(days=1)
    period_label = selected.strftime("%Y/%m/%d")

elif view_mode == "週":
    week_start = today - timedelta(days=today.weekday())
    selected = st.sidebar.date_input("週の開始日 (月曜日)", week_start)
    start_dt = datetime.combine(selected, datetime.min.time())
    end_dt = start_dt + timedelta(days=7)
    period_label = f"{selected.strftime('%Y/%m/%d')} 〜 {(selected + timedelta(days=6)).strftime('%m/%d')}"

else:  # 月
    col_y, col_m = st.sidebar.columns(2)
    year = col_y.number_input("年", value=today.year, min_value=2020, max_value=2035, step=1)
    month = col_m.number_input("月", value=today.month, min_value=1, max_value=12, step=1)
    start_dt = datetime(int(year), int(month), 1)
    if int(month) == 12:
        end_dt = datetime(int(year) + 1, 1, 1)
    else:
        end_dt = datetime(int(year), int(month) + 1, 1)
    period_label = f"{int(year)}/{int(month):02d}"

# ─── メインコンテンツ ──────────────────────────────────────────

st.title("🖥️ PC Activity Tracker")
st.caption(f"期間: {period_label}　　最終更新: {datetime.now().strftime('%H:%M:%S')}")
if st.button("🔄 データを更新"):
    st.cache_data.clear()

df = load_data(start_dt, end_dt)

if df.empty:
    st.warning("この期間のデータがありません。トラッカーが起動しているか確認してください。")
    st.stop()

# ─── サマリー指標 ─────────────────────────────────────────────

total_minutes = df["duration_seconds"].sum() / 60
active_days = df["date"].nunique()
top_app = df.groupby("app_name")["duration_seconds"].sum().idxmax()

m1, m2, m3, m4 = st.columns(4)
m1.metric("合計作業時間", f"{total_minutes / 60:.1f} 時間")
m2.metric("合計 (分)", f"{total_minutes:.0f} 分")
m3.metric("記録日数", f"{active_days} 日")
m4.metric("最多使用アプリ", top_app)

st.divider()

# ─── アプリ別集計 ─────────────────────────────────────────────

app_totals = (
    df.groupby("app_name")["duration_seconds"]
    .sum()
    .reset_index()
    .assign(minutes=lambda x: (x["duration_seconds"] / 60).round(1))
    .sort_values("duration_seconds", ascending=False)
)

col_bar, col_pie = st.columns([3, 2])

with col_bar:
    st.subheader("📊 アプリ別使用時間 (上位 15)")
    fig_bar = px.bar(
        app_totals.head(15),
        x="minutes",
        y="app_name",
        orientation="h",
        labels={"minutes": "使用時間 (分)", "app_name": "アプリ"},
        color="minutes",
        color_continuous_scale="Blues",
        text="minutes",
    )
    fig_bar.update_traces(texttemplate="%{text:.1f}分", textposition="outside")
    fig_bar.update_layout(yaxis={"categoryorder": "total ascending"}, coloraxis_showscale=False)
    st.plotly_chart(fig_bar, use_container_width=True)

with col_pie:
    st.subheader("🥧 使用割合 (上位 10)")
    fig_pie = px.pie(
        app_totals.head(10),
        values="minutes",
        names="app_name",
        hole=0.4,
        color_discrete_sequence=px.colors.sequential.Blues_r,
    )
    fig_pie.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig_pie, use_container_width=True)

# ─── 時間帯ヒートマップ ───────────────────────────────────────

st.subheader("🗓️ 時間帯別アクティビティ (ヒートマップ)")

heatmap_data = (
    df.groupby(["date", "hour"])["duration_seconds"]
    .sum()
    .reset_index()
    .assign(minutes=lambda x: (x["duration_seconds"] / 60).round(1))
)

all_hours = pd.DataFrame({"hour": range(24)})
all_dates = pd.DataFrame({"date": sorted(df["date"].unique())})
heatmap_full = all_dates.merge(all_hours, how="cross").merge(
    heatmap_data[["date", "hour", "minutes"]], on=["date", "hour"], how="left"
).fillna(0)

heatmap_pivot = heatmap_full.pivot(index="date", columns="hour", values="minutes")

fig_heat = px.imshow(
    heatmap_pivot,
    labels={"x": "時間帯", "y": "日付", "color": "使用時間 (分)"},
    color_continuous_scale="Blues",
    aspect="auto",
    text_auto=".0f",
)
fig_heat.update_layout(height=max(200, 40 * len(heatmap_pivot)))
st.plotly_chart(fig_heat, use_container_width=True)

# ─── 日別推移 (週/月表示時) ───────────────────────────────────

if view_mode != "日":
    st.subheader("📈 日別アプリ使用時間推移")

    top5 = app_totals.head(5)["app_name"].tolist()
    daily = (
        df[df["app_name"].isin(top5)]
        .groupby(["date", "app_name"])["duration_seconds"]
        .sum()
        .reset_index()
        .assign(minutes=lambda x: (x["duration_seconds"] / 60).round(1))
    )

    fig_daily = px.bar(
        daily,
        x="date",
        y="minutes",
        color="app_name",
        barmode="stack",
        labels={"minutes": "使用時間 (分)", "date": "日付", "app_name": "アプリ"},
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    st.plotly_chart(fig_daily, use_container_width=True)

# ─── ウィンドウタイトル詳細 ───────────────────────────────────

st.divider()
st.subheader("🔍 ウィンドウタイトル詳細")

selected_app = st.selectbox(
    "アプリを選択",
    options=app_totals["app_name"].tolist(),
    format_func=lambda x: f"{x}  ({app_totals.loc[app_totals['app_name']==x, 'minutes'].values[0]:.1f} 分)",
)

title_df = (
    df[df["app_name"] == selected_app]
    .groupby("window_title")["duration_seconds"]
    .sum()
    .reset_index()
    .assign(minutes=lambda x: (x["duration_seconds"] / 60).round(1))
    .sort_values("duration_seconds", ascending=False)
    .head(30)
    .rename(columns={"window_title": "ウィンドウタイトル", "minutes": "使用時間 (分)"})
    [["ウィンドウタイトル", "使用時間 (分)"]]
)

st.dataframe(title_df, use_container_width=True, hide_index=True)
