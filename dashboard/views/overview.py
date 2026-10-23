"""League overview page: standings, results, fixtures and per-team analysis."""
from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

import ui
from db import query

ui.setup_page("Football Dashboard", "⚽")

COMPETITION_NAMES = {"PL": "Premier League", "ELC": "Championship", "PD": "La Liga",
                     "SA": "Serie A", "BL1": "Bundesliga", "FL1": "Ligue 1"}

try:
    options = query(
        """
        SELECT competition, season FROM football.matches
        UNION SELECT competition, season FROM football.standings
        ORDER BY season DESC, competition
        """
    )
except SQLAlchemyError as exc:
    st.error(f"เชื่อมต่อฐานข้อมูลไม่ได้: {exc.__class__.__name__}")
    st.stop()

if options.empty:
    ui.hero("Football Data Pipeline", "ยังไม่มีข้อมูล")
    st.info("เปิด Airflow (http://localhost:8080) แล้ว trigger DAG `football_pipeline`")
    st.stop()

# --- Sidebar ---------------------------------------------------------------------
with st.sidebar:
    ui.sidebar_brand("Football Hub", "Data Pipeline Dashboard")
    st.markdown("### เลือกลีก")
    labels = [f"{COMPETITION_NAMES.get(r.competition, r.competition)} {r.season}/{str(r.season + 1)[-2:]}"
              for r in options.itertuples()]
    choice = labels.index(st.selectbox("ลีก / ฤดูกาล", labels, label_visibility="collapsed"))
    comp, season = options.iloc[choice]["competition"], int(options.iloc[choice]["season"])

    st.divider()
    last = query("SELECT status, finished_at FROM football.pipeline_runs ORDER BY started_at DESC LIMIT 1")
    if not last.empty:
        st.markdown("**อัปเดตข้อมูลล่าสุด**")
        ui.html(ui.status_pill(last.status[0]))
        st.caption(ui.th_datetime(last.finished_at[0]) if pd.notna(last.finished_at[0]) else "กำลังรัน…")
    if st.button("🔄 โหลดข้อมูลใหม่", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- Data ----------------------------------------------------------------------
standings = query(
    """
    SELECT s.position, s.team_id, t.crest_url, t.name AS team, s.played, s.won, s.draw, s.lost,
           s.goals_for, s.goals_against, s.goal_difference, s.points
    FROM football.standings s JOIN football.teams t USING (team_id)
    WHERE s.competition = :c AND s.season = :s
    ORDER BY s.position NULLS LAST, s.points DESC
    """,
    c=comp, s=season,
)
matches = query(
    """
    SELECT m.matchday, m.utc_date, m.status,
           m.home_team_id, h.name AS home, h.crest_url AS home_crest, m.home_score,
           m.away_team_id, a.name AS away, a.crest_url AS away_crest, m.away_score
    FROM football.matches m
    JOIN football.teams h ON h.team_id = m.home_team_id
    JOIN football.teams a ON a.team_id = m.away_team_id
    WHERE m.competition = :c AND m.season = :s
    ORDER BY m.utc_date NULLS LAST, m.matchday
    """,
    c=comp, s=season,
)
finished = matches[(matches.status == "FINISHED") & matches.home_score.notna()].copy()
upcoming = matches[matches.status.isin(["SCHEDULED", "IN_PLAY", "POSTPONED"])].copy()


def team_results(team_id: str) -> pd.DataFrame:
    """Finished matches from one team's perspective, oldest first."""
    df = finished[(finished.home_team_id == team_id) | (finished.away_team_id == team_id)].copy()
    is_home = df.home_team_id == team_id
    df["gf"] = df.home_score.where(is_home, df.away_score).astype(int)
    df["ga"] = df.away_score.where(is_home, df.home_score).astype(int)
    df["opponent"] = df.away.where(is_home, df.home)
    df["venue"] = is_home.map({True: "เหย้า", False: "เยือน"})
    df["result"] = ["W" if f > a else "D" if f == a else "L" for f, a in zip(df.gf, df.ga)]
    return df.sort_values("utc_date")


team_ids = sorted(set(matches.home_team_id) | set(matches.away_team_id))
forms = {tid: team_results(tid).result.tail(5).tolist() for tid in team_ids}

# --- Header + KPIs -----------------------------------------------------------------
league = COMPETITION_NAMES.get(comp, comp)
played_rounds = int(finished.matchday.max()) if finished.matchday.notna().any() else 0
total_rounds = int(matches.matchday.max()) if matches.matchday.notna().any() else 0
goals = int(finished.home_score.sum() + finished.away_score.sum()) if len(finished) else 0
home_wins = int((finished.home_score > finished.away_score).sum())
leader = standings.iloc[0] if not standings.empty else None
positions = dict(zip(standings.team_id, standings.position.astype(int))) if not standings.empty else {}

chips = []
if total_rounds:
    chips.append(f"นัดที่ <b>{played_rounds}</b> / {total_rounds}")
if leader is not None:
    chips.append(f"จ่าฝูง <b>{escape(leader.team)}</b>")
if len(finished):
    chips.append(f"ล่าสุด {ui.th_datetime(finished.utc_date.max(), with_time=False)}")
ui.hero(f"ฤดูกาล {season}/{str(season + 1)[-2:]}", league,
        "ตารางคะแนน ผลการแข่งขัน และสถิติ อัปเดตอัตโนมัติจาก pipeline", chips)
ui.kpis([
    {"label": "จ่าฝูง", "value": leader.team if leader is not None else "–",
     "note": f"{leader.points} แต้ม จาก {leader.played} นัด" if leader is not None else None},
    {"label": "แมตช์ที่แข่งแล้ว", "value": f"{len(finished)}<span style='font-size:1rem;opacity:.75'> / {len(matches)}</span>",
     "progress": len(finished) / len(matches) if len(matches) else 0},
    {"label": "ประตูรวม", "value": goals,
     "note": f"เฉลี่ย {goals / len(finished):.2f} ประตู/นัด" if len(finished) else None},
    {"label": "เจ้าบ้านชนะ", "value": f"{home_wins / len(finished):.0%}" if len(finished) else "–",
     "note": f"{home_wins} จาก {len(finished)} นัด" if len(finished) else None},
])

# --- Big match of the next matchday: the fixture whose teams sit highest combined ---
if not upcoming.empty and positions:
    next_md = upcoming.matchday.dropna().min()
    pool = upcoming[upcoming.matchday == next_md] if pd.notna(next_md) else upcoming.head(10)
    rank = pool.home_team_id.map(positions).fillna(99) + pool.away_team_id.map(positions).fillna(99)
    ui.featured_match(pool.loc[rank.idxmin()], "บิ๊กแมตช์นัดถัดไป", positions)

tab_table, tab_results, tab_fixtures, tab_team = st.tabs(
    ["🏆  ตารางคะแนน", "⚽  ผลการแข่งขัน", "📅  โปรแกรมแข่ง", "📊  วิเคราะห์ทีม"])

# --- Standings -------------------------------------------------------------------
with tab_table:
    if standings.empty:
        st.info("ยังไม่มีตารางคะแนนสำหรับฤดูกาลนี้")
    else:
        ui.standings_table(standings, forms)
        ui.section("แต้มของแต่ละทีม", "ชี้ที่แท่งเพื่อดูรายละเอียด")
        st.altair_chart(ui.points_bar(standings), use_container_width=True)
        with st.expander("ดูเป็นตารางข้อมูล / ดาวน์โหลด"):
            st.dataframe(standings.drop(columns=["team_id", "crest_url"]), hide_index=True, use_container_width=True)

# --- Results ---------------------------------------------------------------------
with tab_results:
    rounds = sorted(int(x) for x in finished.matchday.dropna().unique())
    if not rounds:
        st.info("ยังไม่มีผลการแข่งขัน")
    else:
        rnd = st.select_slider("นัดที่", options=rounds, value=rounds[-1]) if len(rounds) > 1 else rounds[0]
        day = finished[finished.matchday == rnd]
        ui.section(f"ผลการแข่งขันนัดที่ {rnd}",
                   f"{len(day)} แมตช์ · {int(day.home_score.sum() + day.away_score.sum())} ประตู")
        ui.match_cards(day)

# --- Fixtures --------------------------------------------------------------------
with tab_fixtures:
    next_rounds = sorted(int(x) for x in upcoming.matchday.dropna().unique())
    if not next_rounds:
        st.info("ไม่มีโปรแกรมที่ยังไม่แข่ง")
    else:
        rnd = st.selectbox("นัดที่", next_rounds)
        day = upcoming[upcoming.matchday == rnd]
        ui.section(f"โปรแกรมนัดที่ {rnd}", "เวลาประเทศไทย")
        ui.match_cards(day)

# --- Team analysis -----------------------------------------------------------------
with tab_team:
    names = dict(zip(matches.home_team_id, matches.home)) | dict(zip(matches.away_team_id, matches.away))
    if not names:
        st.info("ยังไม่มีข้อมูลการแข่งขัน")
    else:
        default = list(names).index(leader.team_id) if leader is not None and leader.team_id in names else 0
        team_name = st.selectbox("เลือกทีม", list(names.values()), index=default)
        tid = next(k for k, v in names.items() if v == team_name)
        res = team_results(tid)
        row = standings[standings.team_id == tid]

        if res.empty:
            st.info("ทีมนี้ยังไม่ได้ลงแข่งในฤดูกาลนี้")
        else:
            res["points"] = res.result.map({"W": 3, "D": 1, "L": 0})
            res["cumulative_points"] = res.points.cumsum()
            wins, draws, losses = (res.result == "W").sum(), (res.result == "D").sum(), (res.result == "L").sum()
            crest = standings.loc[standings.team_id == tid, "crest_url"]
            ui.team_banner(tid, team_name, crest.iloc[0] if not crest.empty else None, [
                f"อันดับ <b>{int(row.position.iloc[0])}</b>" if not row.empty else "ยังไม่มีอันดับ",
                f"<b>{int(row.points.iloc[0])}</b> แต้ม" if not row.empty else f"{len(res)} นัด",
                f"ฟอร์ม {ui.form_badges(res.result.tail(5))}",
            ])
            home_pts = int(res.loc[res.venue == "เหย้า", "points"].sum())
            away_pts = int(res.loc[res.venue == "เยือน", "points"].sum())
            ui.kpis([
                {"label": "ชนะ / เสมอ / แพ้", "value": f"{wins} / {draws} / {losses}",
                 "note": f"อัตราชนะ {wins / len(res):.0%}"},
                {"label": "ประตูได้ / เสีย", "value": f"{res.gf.sum()} / {res.ga.sum()}",
                 "note": f"ผลต่าง {res.gf.sum() - res.ga.sum():+d} · เฉลี่ยยิง {res.gf.mean():.1f} ลูก/นัด"},
                {"label": "คลีนชีต", "value": int((res.ga == 0).sum()), "note": f"จาก {len(res)} นัด"},
                {"label": "แต้มเหย้า / เยือน", "value": f"{home_pts} / {away_pts}",
                 "note": f"เหย้า {int((res.venue == 'เหย้า').sum())} นัด · เยือน {int((res.venue == 'เยือน').sum())} นัด"},
            ])

            left, right = st.columns(2)
            with left:
                ui.section("แต้มสะสม")
                st.altair_chart(ui.cumulative_points(res), use_container_width=True)
            with right:
                ui.section("ประตูได้-เสีย รายนัด")
                st.altair_chart(ui.goals_per_match(res), use_container_width=True)

            ui.section("ผลงานล่าสุด")
            ui.match_cards(res.sort_values("utc_date", ascending=False).head(6))

        nxt = upcoming[(upcoming.home_team_id == tid) | (upcoming.away_team_id == tid)].head(3)
        if not nxt.empty:
            ui.section("นัดถัดไป", "เวลาประเทศไทย")
            ui.match_cards(nxt)
