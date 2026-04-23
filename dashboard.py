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

from database import init_db, get_categories, set_category

DB_PATH = Path(__file__).parent / "activity.db"

init_db()

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
has_data = not df.empty

if has_data:
    sessions = build_sessions(df)
    total_minutes = df["duration_seconds"].sum() / 60
    active_days   = df["date"].nunique()
    top_app       = df.groupby("app_name")["duration_seconds"].sum().idxmax()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("合計作業時間", f"{total_minutes / 60:.1f} 時間")
    m2.metric("合計 (分)",   f"{total_minutes:.0f} 分")
    m3.metric("記録日数",    f"{active_days} 日")
    m4.metric("最多使用アプリ", top_app)
    st.divider()
else:
    st.info("この期間のデータがありません。「⚙️ 設定」タブは引き続き利用できます。")

# ─── タブ ─────────────────────────────────────────────────────

tab_summary, tab_timeline, tab_timeband, tab_productivity, tab_meeting, tab_settings = st.tabs(
    ["📊 集計", "📅 タイムライン", "🕐 時間帯分析", "🎯 生産性スコア", "🤝 会議分析", "⚙️ 設定"]
)


# ════════════════════════════════════════════════════════════════
# TAB 1: 集計
# ════════════════════════════════════════════════════════════════

with tab_summary:
    if not has_data:
        st.warning("この期間のデータがありません。")
    else:
        app_totals = (
            df.groupby("app_name")["duration_seconds"]
            .sum().reset_index()
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

    if not has_data:
        st.warning("この期間のデータがありません。")
    else:
        available_dates = sorted(sessions["date"].unique(), reverse=True)

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
            min_min = st.slider("最短セッション表示 (分)", 0.0, 5.0, 0.5, 0.5, key="min_session")
            day_sessions = day_sessions[day_sessions["duration_min"] >= min_min]

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

    if not has_data:
        st.warning("この期間のデータがありません。")
    else:
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
                    .sort_values("minutes", ascending=False).head(8)
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
        heat_col, heat_toggle_col = st.columns([5, 1])
        heat_col.subheader("時間帯 × アプリ 使用時間ヒートマップ")
        hide_zero = heat_toggle_col.toggle("ゼロ行を非表示", value=True, key="hide_zero_heat")

        top_apps_heat = (
            df.groupby("app_name")["duration_seconds"].sum().nlargest(12).index.tolist()
        )
        heat_df = (
            df[df["app_name"].isin(top_apps_heat)]
            .groupby(["hour", "app_name"])["duration_seconds"]
            .sum().reset_index()
            .assign(minutes=lambda x: (x["duration_seconds"] / 60).round(1))
        )
        heat_pivot = (
            heat_df.pivot(index="app_name", columns="hour", values="minutes")
            .reindex(columns=range(24)).fillna(0)
        )
        if hide_zero:
            # text_auto=".0f" で「0」表示になる行（合計 < 0.5 分）を除外
            heat_pivot = heat_pivot[heat_pivot.sum(axis=1) >= 0.5]
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


# ════════════════════════════════════════════════════════════════
# TAB 4: 生産性スコア
# ════════════════════════════════════════════════════════════════

with tab_productivity:
    st.subheader("🎯 生産性スコア")

    categories = get_categories()

    if not categories:
        st.info("「⚙️ 設定」タブでアプリを「集中」または「気晴らし」に分類してください。")
    elif not has_data:
        st.warning("この期間のデータがありません。")
    else:
        def calc_score(focus_min: float, distraction_min: float) -> float | None:
            total = focus_min + distraction_min
            return None if total == 0 else round(focus_min / total * 100, 1)

        def score_color(score: float | None) -> str:
            if score is None:  return "#9E9E9E"
            if score >= 70:    return "#43A047"
            if score >= 40:    return "#FB8C00"
            return "#E53935"

        df_scored = df.copy()
        df_scored["cat"] = df_scored["app_name"].map(lambda a: categories.get(a, "neutral"))
        daily_cat = (
            df_scored.groupby(["date", "cat"])["duration_seconds"]
            .sum().reset_index()
            .assign(minutes=lambda x: x["duration_seconds"] / 60)
        )
        daily_pivot = daily_cat.pivot(index="date", columns="cat", values="minutes").fillna(0)
        for c in ("focus", "distraction", "neutral"):
            if c not in daily_pivot.columns:
                daily_pivot[c] = 0.0
        daily_pivot["score"] = daily_pivot.apply(
            lambda r: calc_score(r["focus"], r["distraction"]), axis=1
        )
        daily_pivot = daily_pivot.reset_index()

        valid = daily_pivot.dropna(subset=["score"])
        if valid.empty:
            st.warning("集中/気晴らしアプリの使用記録がまだありません。")
        else:
            avg_score        = valid["score"].mean()
            best_day         = valid.loc[valid["score"].idxmax(), "date"]
            best_score       = valid["score"].max()
            focus_total_h    = daily_pivot["focus"].sum() / 60
            distract_total_h = daily_pivot["distraction"].sum() / 60

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("平均スコア",   f"{avg_score:.1f} / 100")
            c2.metric("ベストデー",   f"{best_day}  ({best_score:.0f}点)")
            c3.metric("合計集中時間", f"{focus_total_h:.1f} 時間")
            c4.metric("合計気晴らし", f"{distract_total_h:.1f} 時間")
            st.divider()

            st.subheader("日別 生産性スコア")
            bar_colors = [score_color(s) for s in daily_pivot["score"]]
            fig_score = go.Figure(go.Bar(
                x=daily_pivot["date"].astype(str),
                y=daily_pivot["score"].fillna(0),
                marker_color=bar_colors,
                text=daily_pivot["score"].apply(lambda s: f"{s:.0f}" if pd.notna(s) else "—"),
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>スコア: %{y:.1f}<extra></extra>",
            ))
            fig_score.add_hline(y=70, line_dash="dot", line_color="#43A047",
                                annotation_text="目標 70", annotation_position="right")
            fig_score.update_layout(
                yaxis=dict(range=[0, 110], title="スコア"),
                xaxis_title="日付",
                height=350,
            )
            st.plotly_chart(fig_score, use_container_width=True)

            st.subheader("集中時間 vs 気晴らし時間")
            fig_stack = go.Figure()
            fig_stack.add_bar(
                x=daily_pivot["date"].astype(str), y=daily_pivot["focus"],
                name="集中", marker_color="#1E88E5",
            )
            fig_stack.add_bar(
                x=daily_pivot["date"].astype(str), y=daily_pivot["distraction"],
                name="気晴らし", marker_color="#E53935",
            )
            fig_stack.update_layout(
                barmode="stack", yaxis_title="使用時間 (分)", xaxis_title="日付",
                height=300, legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig_stack, use_container_width=True)

            with st.expander("アプリ別 集中/気晴らし 内訳"):
                breakdown = (
                    df_scored[df_scored["cat"].isin(["focus", "distraction"])]
                    .groupby(["app_name", "cat"])["duration_seconds"]
                    .sum().reset_index()
                    .assign(minutes=lambda x: (x["duration_seconds"] / 60).round(1))
                    .sort_values(["cat", "minutes"], ascending=[True, False])
                    .rename(columns={"app_name": "アプリ", "cat": "カテゴリ", "minutes": "使用時間 (分)"})
                    [["カテゴリ", "アプリ", "使用時間 (分)"]]
                )
                breakdown["カテゴリ"] = breakdown["カテゴリ"].map(
                    {"focus": "🟢 集中", "distraction": "🔴 気晴らし"}
                )
                st.dataframe(breakdown, use_container_width=True, hide_index=True)


# ════════════════════════════════════════════════════════════════
# TAB 5: 会議分析
# ════════════════════════════════════════════════════════════════

with tab_meeting:
    st.subheader("🤝 会議分析 — 会議が集中力に与える影響")

    categories = get_categories()
    meeting_apps = {a for a, c in categories.items() if c == "meeting"}

    if not meeting_apps:
        st.info("「⚙️ 設定」タブでアプリを「🤝 会議」に分類してください（Teams / Zoom など）。")
    elif not has_data:
        st.warning("この期間のデータがありません。")
    else:
        import numpy as np

        focus_apps      = {a for a, c in categories.items() if c == "focus"}
        distract_apps   = {a for a, c in categories.items() if c == "distraction"}

        def calc_score(f, d):
            return round(f / (f + d) * 100, 1) if (f + d) > 0 else None

        # 日別集計 (会議 / 集中 / 気晴らし)
        df_m = df.copy()
        df_m["cat"] = df_m["app_name"].map(lambda a: categories.get(a, "neutral"))

        daily = (
            df_m.groupby(["date", "cat"])["duration_seconds"]
            .sum().reset_index()
            .assign(minutes=lambda x: x["duration_seconds"] / 60)
        )
        dpivot = daily.pivot(index="date", columns="cat", values="minutes").fillna(0).reset_index()
        for c in ("meeting", "focus", "distraction"):
            if c not in dpivot.columns:
                dpivot[c] = 0.0
        dpivot["score"] = dpivot.apply(lambda r: calc_score(r["focus"], r["distraction"]), axis=1)

        # 会議のある日だけを使う（会議0分の日はスコア比較の外れ値になりがち）
        has_meeting = dpivot["meeting"] > 0

        # ── サマリー指標 ──────────────────────────────────────────
        avg_meeting     = dpivot.loc[has_meeting, "meeting"].mean()
        heavy_threshold = dpivot["meeting"].quantile(0.5)  # 中央値を閾値に

        heavy_days = dpivot[dpivot["meeting"] >= heavy_threshold].dropna(subset=["score"])
        light_days = dpivot[dpivot["meeting"] <  heavy_threshold].dropna(subset=["score"])

        heavy_score = heavy_days["score"].mean() if not heavy_days.empty else None
        light_score = light_days["score"].mean() if not light_days.empty else None
        score_diff  = (light_score - heavy_score) if (heavy_score and light_score) else None

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("平均会議時間/日",   f"{avg_meeting:.0f} 分" if not pd.isna(avg_meeting) else "—")
        c2.metric("会議多い日 平均スコア", f"{heavy_score:.1f}" if heavy_score else "—")
        c3.metric("会議少ない日 平均スコア", f"{light_score:.1f}" if light_score else "—")
        c4.metric("集中力への影響",
                  f"{score_diff:+.1f} 点" if score_diff else "—",
                  help="会議少ない日 − 会議多い日。プラスなら会議が少ない日のほうが集中できている")
        st.divider()

        # ── 日別 会議時間 + 生産性スコア 複合グラフ ──────────────
        st.subheader("日別 会議時間 と 生産性スコアの推移")

        fig_combo = go.Figure()
        fig_combo.add_bar(
            x=dpivot["date"].astype(str),
            y=dpivot["meeting"],
            name="会議時間 (分)",
            marker_color="#7E57C2",
            yaxis="y1",
        )
        fig_combo.add_scatter(
            x=dpivot["date"].astype(str),
            y=dpivot["score"],
            name="生産性スコア",
            mode="lines+markers",
            line=dict(color="#43A047", width=2),
            marker=dict(size=7),
            yaxis="y2",
        )
        fig_combo.update_layout(
            yaxis=dict(title="会議時間 (分)", side="left"),
            yaxis2=dict(title="生産性スコア", side="right", overlaying="y",
                        range=[0, 110]),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            height=380,
            hovermode="x unified",
        )
        st.plotly_chart(fig_combo, use_container_width=True)

        # ── 散布図: 会議時間 vs スコア ────────────────────────────
        st.subheader("会議時間 vs 生産性スコア（相関）")

        scatter_df = dpivot.dropna(subset=["score"]).copy()
        if len(scatter_df) >= 2:
            x_vals = scatter_df["meeting"].values
            y_vals = scatter_df["score"].values
            coef   = np.polyfit(x_vals, y_vals, 1)
            x_line = np.linspace(x_vals.min(), x_vals.max(), 100)
            y_line = np.polyval(coef, x_line)
            corr   = np.corrcoef(x_vals, y_vals)[0, 1]

            fig_scatter = px.scatter(
                scatter_df,
                x="meeting", y="score",
                hover_data={"date": True, "meeting": ":.0f", "score": ":.1f"},
                labels={"meeting": "会議時間 (分)", "score": "生産性スコア", "date": "日付"},
                color_discrete_sequence=["#7E57C2"],
            )
            fig_scatter.add_scatter(
                x=x_line, y=y_line,
                mode="lines",
                name=f"トレンド (相関係数 {corr:.2f})",
                line=dict(dash="dash", color="#E53935"),
            )
            fig_scatter.update_layout(height=380)
            st.plotly_chart(fig_scatter, use_container_width=True)

            direction = "下がる傾向" if coef[0] < 0 else "上がる傾向"
            st.caption(
                f"相関係数: **{corr:.2f}**　　会議時間が増えるとスコアが **{direction}** にあります"
                f"（1に近いほど正の相関、-1に近いほど負の相関）"
            )
        else:
            st.info("散布図を表示するにはスコアが算出できる日が 2 日以上必要です。")

        # ── 会議多い日 vs 少ない日 比較 ───────────────────────────
        st.subheader(f"会議多い日 vs 少ない日の比較（閾値: {heavy_threshold:.0f} 分/日）")

        compare_data = []
        for label, group in [("🟣 会議多い日", heavy_days), ("🟢 会議少ない日", light_days)]:
            if not group.empty:
                compare_data.append({
                    "区分": label,
                    "日数": len(group),
                    "平均会議 (分)": group["meeting"].mean(),
                    "平均集中 (分)": group["focus"].mean(),
                    "平均気晴らし (分)": group["distraction"].mean(),
                    "平均スコア": group["score"].mean(),
                })
        if compare_data:
            compare_df = pd.DataFrame(compare_data).set_index("区分")
            st.dataframe(compare_df.round(1), use_container_width=True)

            fig_compare = go.Figure()
            metrics = ["平均会議 (分)", "平均集中 (分)", "平均気晴らし (分)"]
            colors  = ["#7E57C2", "#1E88E5", "#E53935"]
            for metric, color in zip(metrics, colors):
                fig_compare.add_bar(
                    x=compare_df.index,
                    y=compare_df[metric],
                    name=metric,
                    marker_color=color,
                )
            fig_compare.update_layout(
                barmode="group",
                yaxis_title="時間 (分)",
                height=320,
                legend=dict(orientation="h", yanchor="bottom", y=1.02),
            )
            st.plotly_chart(fig_compare, use_container_width=True)

        # ── 時間帯別 会議分布 ──────────────────────────────────────
        st.subheader("時間帯別 会議分布")

        meeting_hourly = (
            df_m[df_m["cat"] == "meeting"]
            .groupby("hour")["duration_seconds"]
            .sum().reset_index()
            .assign(minutes=lambda x: (x["duration_seconds"] / 60).round(1))
        )
        all_hours_df = pd.DataFrame({"hour": range(24)})
        meeting_hourly = all_hours_df.merge(meeting_hourly, on="hour", how="left").fillna(0)

        fig_mhour = px.bar(
            meeting_hourly,
            x="hour", y="minutes",
            labels={"hour": "時間帯", "minutes": "会議時間 (分)"},
            color="minutes",
            color_continuous_scale="Purples",
            text="minutes",
        )
        fig_mhour.update_traces(texttemplate="%{text:.0f}", textposition="outside")
        fig_mhour.update_layout(
            xaxis=dict(tickmode="array", tickvals=list(range(24)),
                       ticktext=[f"{h}時" for h in range(24)]),
            coloraxis_showscale=False,
            height=300,
        )
        st.plotly_chart(fig_mhour, use_container_width=True)


# ════════════════════════════════════════════════════════════════
# TAB 6: 設定
# ════════════════════════════════════════════════════════════════

with tab_settings:
    st.subheader("⚙️ アプリカテゴリ設定")
    st.caption("集中: 生産性スコアを上げるアプリ　／　気晴らし: スコアを下げるアプリ　／　未分類: スコアに影響しない")

    all_apps_query_start = datetime.now() - timedelta(days=30)
    with sqlite3.connect(DB_PATH) as conn:
        all_apps_df = pd.read_sql_query(
            "SELECT DISTINCT app_name FROM activity WHERE timestamp >= ? ORDER BY app_name",
            conn,
            params=(all_apps_query_start.isoformat(timespec="seconds"),),
        )
    all_apps = all_apps_df["app_name"].tolist()

    if not all_apps:
        st.info("まだアプリの記録がありません。トラッカーを起動して数分待ってから再度開いてください。")
    else:
        current_cats = get_categories()
        CATEGORY_OPTIONS = {"未分類": "neutral", "🟢 集中": "focus", "🔴 気晴らし": "distraction", "🤝 会議": "meeting"}
        CATEGORY_LABELS  = {v: k for k, v in CATEGORY_OPTIONS.items()}

        # 会議アプリ候補を自動検出してワンクリック設定
        MEETING_KEYWORDS = ["teams", "zoom", "meet", "webex", "slack", "skype"]
        meeting_candidates = [
            a for a in all_apps
            if any(kw in a.lower() for kw in MEETING_KEYWORDS)
            and current_cats.get(a) != "meeting"
        ]
        if meeting_candidates:
            st.info(f"会議アプリの候補を検出しました: {', '.join(meeting_candidates)}")
            if st.button("🤝 まとめて「会議」に設定する"):
                for app in meeting_candidates:
                    set_category(app, "meeting")
                st.cache_data.clear()
                st.success("設定しました。")
                st.rerun()

        st.markdown(f"**直近 30 日間に使用したアプリ ({len(all_apps)} 件)**")

        if "cat_edits" not in st.session_state:
            st.session_state.cat_edits = {}

        cols_per_row = 3
        rows = [all_apps[i:i + cols_per_row] for i in range(0, len(all_apps), cols_per_row)]
        for row_apps in rows:
            cols = st.columns(cols_per_row)
            for col, app in zip(cols, row_apps):
                current       = current_cats.get(app, "neutral")
                current_label = CATEGORY_LABELS.get(current, "未分類")
                selected = col.selectbox(
                    app,
                    options=list(CATEGORY_OPTIONS.keys()),
                    index=list(CATEGORY_OPTIONS.keys()).index(current_label),
                    key=f"cat_{app}",
                )
                st.session_state.cat_edits[app] = CATEGORY_OPTIONS[selected]

        st.divider()
        if st.button("💾 保存する", type="primary"):
            for app_name, cat in st.session_state.cat_edits.items():
                set_category(app_name, cat)
            st.cache_data.clear()
            st.success("カテゴリを保存しました。")
            st.rerun()
