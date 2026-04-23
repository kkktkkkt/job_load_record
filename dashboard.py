"""
Activity Tracker ダッシュボード
起動: streamlit run dashboard.py
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
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
    return df


def build_sessions(df: pd.DataFrame, gap_seconds: int = 20) -> pd.DataFrame:
    """連続する同アプリ+タイトルの記録をセッション (start/end) に集約する"""
    if df.empty:
        return pd.DataFrame()

    df = df.sort_values("timestamp").copy()
    sessions = []
    cur_app = cur_title = session_start = last_end = None

    for row in df.itertuples():
        row_end = row.timestamp + pd.Timedelta(seconds=row.duration_seconds)
        gap = (row.timestamp - last_end).total_seconds() if last_end is not None else 0

        same = (cur_app == row.app_name and cur_title == row.window_title and gap <= gap_seconds)

        if not same:
            if cur_app is not None:
                sessions.append({"app_name": cur_app, "window_title": cur_title,
                                  "start": session_start, "end": last_end})
            cur_app, cur_title, session_start = row.app_name, row.window_title, row.timestamp

        last_end = row_end

    if cur_app is not None:
        sessions.append({"app_name": cur_app, "window_title": cur_title,
                          "start": session_start, "end": last_end})

    sdf = pd.DataFrame(sessions)
    sdf["duration_min"] = ((sdf["end"] - sdf["start"]).dt.total_seconds() / 60).round(1)
    sdf["date"] = sdf["start"].dt.date
    sdf["hour"] = sdf["start"].dt.hour
    return sdf


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

else:
    col_y, col_m = st.sidebar.columns(2)
    year = col_y.number_input("年", value=today.year, min_value=2020, max_value=2035, step=1)
    month = col_m.number_input("月", value=today.month, min_value=1, max_value=12, step=1)
    start_dt = datetime(int(year), int(month), 1)
    end_dt = datetime(int(year) + 1, 1, 1) if int(month) == 12 else datetime(int(year), int(month) + 1, 1)
    period_label = f"{int(year)}/{int(month):02d}"

# ─── ヘッダー ─────────────────────────────────────────────────

st.title("🖥️ PC Activity Tracker")
st.caption(f"期間: {period_label}　　最終更新: {datetime.now().strftime('%H:%M:%S')}")
if st.button("🔄 データを更新"):
    st.cache_data.clear()
    st.rerun()

df = load_data(start_dt, end_dt)

if df.empty:
    st.warning("この期間のデータがありません。トラッカーが起動しているか確認してください。")
    st.stop()

sessions = build_sessions(df)

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

# ─── タブ ─────────────────────────────────────────────────────

tab_summary, tab_timeline, tab_timeband = st.tabs(["📊 集計", "📅 タイムライン", "🕐 時間帯分析"])


# ════════════════════════════════════════════════════════════════
# TAB 1: 集計
# ════════════════════════════════════════════════════════════════

with tab_summary:
    app_totals = (
        df.groupby("app_name")["duration_seconds"]
        .sum()
        .reset_index()
        .assign(minutes=lambda x: (x["duration_seconds"] / 60).round(1))
        .sort_values("duration_seconds", ascending=False)
    )

    col_bar, col_pie = st.columns([3, 2])

    with col_bar:
        st.subheader("アプリ別使用時間 (上位 15)")
        fig_bar = px.bar(
            app_totals.head(15),
            x="minutes", y="app_name", orientation="h",
            labels={"minutes": "使用時間 (分)", "app_name": "アプリ"},
            color="minutes", color_continuous_scale="Blues", text="minutes",
        )
        fig_bar.update_traces(texttemplate="%{text:.1f}分", textposition="outside")
        fig_bar.update_layout(yaxis={"categoryorder": "total ascending"}, coloraxis_showscale=False)
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_pie:
        st.subheader("使用割合 (上位 10)")
        fig_pie = px.pie(
            app_totals.head(10), values="minutes", names="app_name", hole=0.4,
            color_discrete_sequence=px.colors.sequential.Blues_r,
        )
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig_pie, use_container_width=True)

    if view_mode != "日":
        st.subheader("日別アプリ使用時間推移")
        top5 = app_totals.head(5)["app_name"].tolist()
        daily = (
            df[df["app_name"].isin(top5)]
            .groupby(["date", "app_name"])["duration_seconds"]
            .sum().reset_index()
            .assign(minutes=lambda x: (x["duration_seconds"] / 60).round(1))
        )
        fig_daily = px.bar(
            daily, x="date", y="minutes", color="app_name", barmode="stack",
            labels={"minutes": "使用時間 (分)", "date": "日付", "app_name": "アプリ"},
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        st.plotly_chart(fig_daily, use_container_width=True)

    st.subheader("🔍 ウィンドウタイトル詳細")
    selected_app = st.selectbox(
        "アプリを選択",
        options=app_totals["app_name"].tolist(),
        format_func=lambda x: f"{x}  ({app_totals.loc[app_totals['app_name']==x, 'minutes'].values[0]:.1f} 分)",
        key="summary_app_select",
    )
    title_df = (
        df[df["app_name"] == selected_app]
        .groupby("window_title")["duration_seconds"].sum().reset_index()
        .assign(minutes=lambda x: (x["duration_seconds"] / 60).round(1))
        .sort_values("duration_seconds", ascending=False).head(30)
        .rename(columns={"window_title": "ウィンドウタイトル", "minutes": "使用時間 (分)"})
        [["ウィンドウタイトル", "使用時間 (分)"]]
    )
    st.dataframe(title_df, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════
# TAB 2: タイムライン
# ════════════════════════════════════════════════════════════════

with tab_timeline:
    st.subheader("📅 作業タイムライン")

    # 日付選択（週/月モードでは日付を絞る）
    available_dates = sorted(sessions["date"].unique(), reverse=True)
    if not available_dates:
        st.warning("データがありません。")
        st.stop()

    timeline_date = st.selectbox(
        "日付を選択",
        options=available_dates,
        format_func=lambda d: d.strftime("%Y/%m/%d (%a)"),
        key="timeline_date",
    )

    day_sessions = sessions[sessions["date"] == timeline_date].copy()

    if day_sessions.empty:
        st.warning("この日のデータがありません。")
    else:
        # 短すぎるセッション（10秒未満）は非表示オプション
        min_min = st.slider("最短セッション表示 (分)", 0.0, 5.0, 0.5, 0.5, key="min_session")
        day_sessions = day_sessions[day_sessions["duration_min"] >= min_min]

        # ラベル: アプリ名 + タイトルの先頭50文字
        day_sessions["label"] = day_sessions.apply(
            lambda r: f"{r['app_name']}  |  {str(r['window_title'])[:60]}", axis=1
        )

        fig_gantt = px.timeline(
            day_sessions,
            x_start="start", x_end="end",
            y="app_name",
            color="app_name",
            hover_data={"window_title": True, "duration_min": True,
                        "start": "|%H:%M:%S", "end": "|%H:%M:%S", "app_name": False},
            labels={"app_name": "アプリ", "duration_min": "時間(分)", "window_title": "タイトル"},
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig_gantt.update_layout(
            xaxis_title="時刻",
            yaxis_title="",
            height=max(300, 40 * day_sessions["app_name"].nunique() + 100),
            showlegend=False,
            xaxis=dict(
                tickformat="%H:%M",
                range=[
                    datetime.combine(timeline_date, datetime.min.time()),
                    datetime.combine(timeline_date, datetime.max.time()),
                ],
            ),
        )
        st.plotly_chart(fig_gantt, use_container_width=True)

        # セッション一覧テーブル
        with st.expander("セッション一覧"):
            tbl = day_sessions[["start", "end", "app_name", "window_title", "duration_min"]].copy()
            tbl["start"] = tbl["start"].dt.strftime("%H:%M:%S")
            tbl["end"]   = tbl["end"].dt.strftime("%H:%M:%S")
            tbl = tbl.rename(columns={
                "start": "開始", "end": "終了",
                "app_name": "アプリ", "window_title": "ウィンドウタイトル", "duration_min": "時間(分)"
            })
            st.dataframe(tbl, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════
# TAB 3: 時間帯分析
# ════════════════════════════════════════════════════════════════

with tab_timeband:
    st.subheader("🕐 時間帯別の作業内容")

    # AM / PM / 夜 サマリー
    def band_label(hour: int) -> str:
        if hour < 6:   return "深夜 (0-5時)"
        if hour < 12:  return "午前 (6-11時)"
        if hour < 18:  return "午後 (12-17時)"
        return "夜 (18-23時)"

    df_band = df.copy()
    df_band["time_band"] = df_band["hour"].apply(band_label)

    band_app = (
        df_band.groupby(["time_band", "app_name"])["duration_seconds"]
        .sum().reset_index()
        .assign(minutes=lambda x: (x["duration_seconds"] / 60).round(1))
    )

    band_order = ["午前 (6-11時)", "午後 (12-17時)", "夜 (18-23時)", "深夜 (0-5時)"]
    present_bands = [b for b in band_order if b in band_app["time_band"].unique()]

    cols = st.columns(len(present_bands))
    for col, band in zip(cols, present_bands):
        with col:
            st.markdown(f"**{band}**")
            bdf = (
                band_app[band_app["time_band"] == band]
                .sort_values("minutes", ascending=False)
                .head(8)
            )
            fig = px.bar(
                bdf, x="minutes", y="app_name", orientation="h",
                color="minutes", color_continuous_scale="Blues",
                labels={"minutes": "分", "app_name": ""},
                text="minutes",
            )
            fig.update_traces(texttemplate="%{text:.0f}分", textposition="outside")
            fig.update_layout(
                height=300, margin=dict(l=0, r=20, t=10, b=30),
                coloraxis_showscale=False,
                yaxis={"categoryorder": "total ascending"},
            )
            st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # 時間帯 × アプリ ヒートマップ
    st.subheader("時間帯 × アプリ 使用時間ヒートマップ")

    top_apps_heat = (
        df.groupby("app_name")["duration_seconds"].sum()
        .nlargest(12).index.tolist()
    )
    heat_df = (
        df[df["app_name"].isin(top_apps_heat)]
        .groupby(["hour", "app_name"])["duration_seconds"]
        .sum().reset_index()
        .assign(minutes=lambda x: (x["duration_seconds"] / 60).round(1))
    )
    heat_pivot = (
        heat_df.pivot(index="app_name", columns="hour", values="minutes")
        .reindex(columns=range(24))
        .fillna(0)
    )
    fig_heat = px.imshow(
        heat_pivot,
        labels={"x": "時間帯", "y": "アプリ", "color": "使用時間 (分)"},
        color_continuous_scale="Blues",
        aspect="auto",
        text_auto=".0f",
        x=[f"{h}時" for h in range(24)],
    )
    fig_heat.update_layout(height=400)
    st.plotly_chart(fig_heat, use_container_width=True)
