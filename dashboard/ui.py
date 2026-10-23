"""Shared look & feel: CSS, HTML components and Altair charts used by every page."""
from __future__ import annotations

import zlib
from html import escape
from typing import Iterable

import altair as alt
import pandas as pd
import streamlit as st

# Validated categorical order (blue, orange, aqua) + fixed status colours for charts.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
GOOD, WARNING, CRITICAL, NEUTRAL = "#0ca30c", "#fab219", "#d03b3b", "#b9b6c9"
BRAND, BRAND_DARK, MAGENTA = "#3d0a6b", "#1b0b3b", "#e6176f"
TEXT, TEXT_2, MUTED, GRID = "#14092b", "#4f4766", "#8a83a0", "#ebe8f2"

TH_DAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]
TH_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]

# Club colours: team_id -> (badge background, badge text)
TEAM_COLORS = {
    "arsenal": ("#ef0107", "#ffffff"), "aston-villa": ("#670e36", "#95bfe5"),
    "bournemouth": ("#da291c", "#111111"), "brentford": ("#e30613", "#ffffff"),
    "brighton": ("#0057b8", "#ffffff"), "burnley": ("#6c1d45", "#99d6ea"),
    "chelsea": ("#034694", "#ffffff"), "coventry-city": ("#6cabdd", "#0b2341"),
    "crystal-palace": ("#1b458f", "#ff6b7d"), "everton": ("#003399", "#ffffff"),
    "fulham": ("#1a1a1a", "#ffffff"), "hull-city": ("#f5a12d", "#111111"),
    "ipswich-town": ("#0044a9", "#ffffff"), "leeds-united": ("#1d428a", "#ffcd00"),
    "leicester-city": ("#003090", "#fdbe11"), "liverpool": ("#c8102e", "#ffffff"),
    "luton-town": ("#f78f1e", "#111111"), "manchester-city": ("#6cabdd", "#1c2c5b"),
    "manchester-united": ("#da291c", "#fbe122"), "middlesbrough": ("#e11b22", "#ffffff"),
    "newcastle-united": ("#241f20", "#ffffff"), "norwich-city": ("#00a650", "#fff200"),
    "nottingham-forest": ("#dd0000", "#ffffff"), "sheffield-united": ("#ee2737", "#ffffff"),
    "southampton": ("#d71920", "#ffffff"), "sunderland": ("#eb172b", "#ffffff"),
    "tottenham-hotspur": ("#132257", "#ffffff"), "watford": ("#fbee23", "#111111"),
    "west-bromwich-albion": ("#122f67", "#ffffff"), "west-ham-united": ("#7a263a", "#1bb1e7"),
    "wolverhampton-wanderers": ("#fdb913", "#111111"),
}
_FALLBACK = [("#3d0a6b", "#ffffff"), ("#0f6e8c", "#ffffff"), ("#8c2d0f", "#ffffff"), ("#1f6b3a", "#ffffff")]


def team_colors(team_id: str) -> tuple[str, str]:
    return TEAM_COLORS.get(team_id) or _FALLBACK[zlib.crc32(str(team_id).encode()) % len(_FALLBACK)]


CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Thai:wght@400;500;600;700&display=swap');

:root {
  --surface: #f4f2f8; --card: #ffffff; --border: #e6e2ef;
  --text: #14092b; --text-2: #4f4766; --muted: #8a83a0;
  --brand: #3d0a6b; --brand-dark: #1b0b3b; --magenta: #e6176f; --lime: #3cff9e; --cyan: #29d3ff;
  --ucl: #2a78d6; --uel: #eb6834; --rel: #d03b3b;
  --win: #0e8a43; --draw: #7b7a75; --loss: #d12f3d;
}
html, body, [class*="css"], .stMarkdown, .stTabs, button, input, select {
  font-family: 'IBM Plex Sans Thai', 'Source Sans Pro', sans-serif !important;
}
.block-container { padding-top: 3.5rem; padding-bottom: 3rem; max-width: 1240px; }

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] { background: linear-gradient(180deg, #1b0b3b 0%, #2e0b5a 100%); }
section[data-testid="stSidebar"] .stMarkdown, section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] h3, section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] label p { color: #f1ecff !important; }
[data-testid="stSidebarNav"] a span { color: #d9d0f5 !important; font-weight: 500; }
[data-testid="stSidebarNav"] a[aria-current="page"] { background: rgba(60, 255, 158, .14) !important; }
[data-testid="stSidebarNav"] a[aria-current="page"] span { color: var(--lime) !important; font-weight: 700; }
section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.14); }
.side-brand { display: flex; align-items: center; gap: 10px; margin: 4px 0 6px; }
.side-brand .ball { width: 36px; height: 36px; border-radius: 10px; display: grid; place-items: center; font-size: 20px;
  background: linear-gradient(135deg, var(--magenta), #7b2ff7); }
.side-brand b { color: #fff; font-size: 1.05rem; } .side-brand small { color: #b9aee0; display: block; font-size: .72rem; }

/* ---------- Hero banner with pitch markings ---------- */
.hero { position: relative; overflow: hidden; border-radius: 22px; padding: 28px 32px; margin-bottom: 18px; color: #fff;
  background: radial-gradient(circle at 105% -20%, rgba(255,40,130,.55), transparent 45%),
              linear-gradient(120deg, #1b0b3b 0%, #3d0a6b 60%, #6a0f7d 100%); }
.hero.alt { background: radial-gradient(circle at 105% -20%, rgba(41,211,255,.45), transparent 45%),
              linear-gradient(120deg, #0b1a3b 0%, #12306b 60%, #0f5a7d 100%); }
.hero::before { content: ""; position: absolute; top: 0; bottom: 0; right: 22%; border-left: 2px solid rgba(255,255,255,.09); }
.hero::after { content: ""; position: absolute; width: 170px; height: 170px; right: calc(22% - 86px); top: 50%;
  transform: translateY(-50%); border: 2px solid rgba(255,255,255,.09); border-radius: 50%; }
.hero > * { position: relative; z-index: 1; }
.hero .eyebrow { color: var(--lime); font-weight: 700; font-size: .8rem; text-transform: uppercase; letter-spacing: .12em; }
.hero h1 { margin: .2rem 0 .3rem; font-size: 2.35rem; font-weight: 700; color: #fff; padding: 0; line-height: 1.15; }
.hero .sub { color: #d9d0f5; font-size: .95rem; }
.chips { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }
.chip { background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.18); color: #fff; border-radius: 999px;
  padding: 4px 12px; font-size: .8rem; font-weight: 500; }
.chip b { color: var(--lime); }

/* ---------- KPI tiles ---------- */
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; margin: 0 0 18px; }
.kpi { position: relative; overflow: hidden; border-radius: 18px; padding: 16px 18px; color: #fff;
  box-shadow: 0 6px 18px rgba(27, 11, 59, .12); }
.kpi::after { content: ""; position: absolute; right: -30px; top: -30px; width: 110px; height: 110px; border-radius: 50%;
  background: rgba(255,255,255,.10); }
.kpi.c1 { background: linear-gradient(135deg, #e6176f, #9b1062); }
.kpi.c2 { background: linear-gradient(135deg, #2a6fd0, #1b3f8f); }
.kpi.c3 { background: linear-gradient(135deg, #0f8f5b, #0a5c3b); }
.kpi.c4 { background: linear-gradient(135deg, #e8590c, #b23a07); }
.kpi .label { font-size: .82rem; font-weight: 500; opacity: .92; }
.kpi .value { font-size: 1.85rem; font-weight: 700; line-height: 1.15; margin-top: 4px; }
.kpi .note { font-size: .78rem; opacity: .88; margin-top: 3px; }
.kpi .bar { height: 6px; background: rgba(255,255,255,.25); border-radius: 4px; margin-top: 10px; overflow: hidden; }
.kpi .bar > span { display: block; height: 100%; background: var(--lime); border-radius: 4px; }

/* ---------- Section titles ---------- */
.section-title { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 1.12rem; margin: 1.4rem 0 .7rem; color: var(--text); }
.section-title::before { content: ""; width: 6px; height: 20px; border-radius: 3px; background: linear-gradient(180deg, var(--magenta), #7b2ff7); }
.hint { color: var(--muted); font-size: .8rem; font-weight: 500; }

/* ---------- Tabs as pills ---------- */
.stTabs [data-baseweb="tab-list"] { gap: 6px; background: #fff; padding: 6px; border-radius: 999px; border: 1px solid var(--border);
  width: fit-content; max-width: 100%; overflow-x: auto; box-shadow: 0 2px 8px rgba(27,11,59,.05); }
.stTabs [data-baseweb="tab"] { border-radius: 999px; padding: 8px 18px; height: auto; background: transparent; }
.stTabs [data-baseweb="tab"] p { font-weight: 600; color: var(--text-2); }
.stTabs [aria-selected="true"] { background: linear-gradient(120deg, #3d0a6b, #e6176f); }
.stTabs [aria-selected="true"] p { color: #fff !important; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none; }

/* ---------- Team badge (club colours) ---------- */
.badge { display: inline-flex; align-items: center; justify-content: center; flex: none; width: 28px; height: 28px; border-radius: 50%;
  font-size: .6rem; font-weight: 700; letter-spacing: .02em; margin-right: 10px; vertical-align: middle;
  box-shadow: 0 0 0 2px #fff, 0 2px 6px rgba(0,0,0,.15); }
.badge.lg { width: 64px; height: 64px; font-size: 1.05rem; margin: 0; box-shadow: 0 0 0 3px rgba(255,255,255,.85), 0 6px 18px rgba(0,0,0,.3); }
img.badge { object-fit: contain; background: #fff; }

/* ---------- Standings ---------- */
.table-wrap { overflow-x: auto; background: var(--card); border-radius: 18px; box-shadow: 0 6px 18px rgba(27,11,59,.08); }
table.standings { width: 100%; border-collapse: collapse; font-size: .93rem; min-width: 680px; }
table.standings thead th { background: var(--brand-dark); color: #d9d0f5; font-weight: 600; font-size: .76rem; padding: 12px 6px;
  text-align: center; text-transform: uppercase; letter-spacing: .05em; }
table.standings th.team { text-align: left; }
table.standings td { text-align: center; padding: 9px 6px; border-bottom: 1px solid #f1eef7; color: var(--text-2); }
table.standings tbody tr:nth-child(even) td { background: #fbfaff; }
table.standings tbody tr:hover td { background: #f3edff; }
table.standings td.team { text-align: left; color: var(--text); font-weight: 600; }
table.standings td.pts { font-weight: 800; color: var(--brand); font-size: 1.05rem; }
.pos { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 8px;
  font-weight: 700; color: var(--text); background: #efebf7; }
.pos.ucl { background: var(--ucl); color: #fff; } .pos.uel { background: var(--uel); color: #fff; } .pos.rel { background: var(--rel); color: #fff; }
.legend { display: flex; gap: 18px; flex-wrap: wrap; color: var(--text-2); font-size: .8rem; margin: 10px 4px 0; }
.legend i { display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }

/* ---------- Form: letter + colour ---------- */
.form { display: inline-flex; gap: 4px; }
.form b { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px; border-radius: 6px;
  font-size: .7rem; font-weight: 700; color: #fff; }
.form b.W { background: var(--win); } .form b.D { background: var(--draw); } .form b.L { background: var(--loss); }

/* ---------- Match cards ---------- */
.matches { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 12px; }
.match { background: var(--card); border-radius: 16px; padding: 12px 16px 14px; box-shadow: 0 4px 14px rgba(27,11,59,.07);
  border: 1px solid var(--border); transition: transform .15s ease, box-shadow .15s ease; }
.match:hover { transform: translateY(-2px); box-shadow: 0 10px 24px rgba(27,11,59,.12); }
.match .meta { display: flex; justify-content: space-between; align-items: center; color: var(--muted); font-size: .76rem; margin-bottom: 10px; }
.tag { border-radius: 6px; padding: 1px 8px; font-weight: 700; font-size: .7rem; }
.tag.md { background: #efe7ff; color: var(--brand); }
.tag.ft { background: #e3f7ec; color: #0b6b37; }
.tag.live { background: #ffe3ee; color: #b0104f; }
.match .row { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 10px; }
.match .side { display: flex; align-items: center; color: var(--text-2); font-size: .93rem; min-width: 0; }
.match .side .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.match .side.away { justify-content: flex-end; text-align: right; }
.match .side.away .badge { margin: 0 0 0 10px; order: 2; }
.match .side.win { color: var(--text); font-weight: 700; }
.match .side.lose { color: var(--muted); }
.score { font-weight: 700; font-size: 1.2rem; color: #fff; background: var(--brand-dark); border-radius: 10px;
  padding: 4px 12px; min-width: 70px; text-align: center; font-variant-numeric: tabular-nums; letter-spacing: .04em; }
.score.vs { font-size: .9rem; color: var(--brand); background: #efe7ff; }

/* ---------- Featured match / team banner ---------- */
.feature { position: relative; overflow: hidden; border-radius: 22px; padding: 22px 26px; color: #fff; margin-bottom: 8px;
  box-shadow: 0 10px 28px rgba(27,11,59,.22); }
.feature .top { display: flex; justify-content: space-between; align-items: center; font-size: .8rem; color: #e9e3ff; }
.feature .top .tag { background: var(--lime); color: #0b3b22; }
.feature .row { display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 16px; margin-top: 14px; }
.feature .side { display: flex; flex-direction: column; align-items: center; gap: 8px; text-align: center; }
.feature .side .name { font-weight: 700; font-size: 1.1rem; text-shadow: 0 1px 3px rgba(0,0,0,.45); }
.feature .side .info { font-size: .78rem; color: #e9e3ff; text-shadow: 0 1px 2px rgba(0,0,0,.45); }
.feature .mid { text-align: center; }
.feature .mid .big { font-size: 2rem; font-weight: 800; letter-spacing: .04em; }
.feature .mid .small { font-size: .8rem; color: #e9e3ff; }
.team-banner { display: flex; align-items: center; gap: 20px; }
.team-banner h2 { color: #fff; margin: 0; padding: 0; font-size: 1.7rem; text-shadow: 0 1px 3px rgba(0,0,0,.45); }

/* ---------- Pills & checklist ---------- */
.pill { display: inline-block; padding: 3px 12px; border-radius: 999px; font-size: .78rem; font-weight: 700; }
.pill.success { color: #0b5e2e; background: #c9f5dc; } .pill.partial { color: #6b4a00; background: #ffe7a8; }
.pill.failed { color: #8f1d2a; background: #ffd3d8; } .pill.running { color: #12306b; background: #d3e4ff; }
.checks { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 10px; }
.check { display: flex; gap: 10px; align-items: center; background: var(--card); border-radius: 12px; padding: 10px 14px;
  box-shadow: 0 3px 10px rgba(27,11,59,.06); border: 1px solid var(--border); font-size: .88rem; }
.check .ico { width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center; flex: none; font-weight: 800; color: #fff; background: var(--win); }
.check.warning .ico { background: #c98500; } .check.error .ico { background: var(--loss); }
.check .name { font-weight: 600; color: var(--text); } .check .meta { color: var(--muted); font-size: .76rem; }
</style>
"""


def setup_page(title: str, icon: str) -> None:
    st.set_page_config(page_title=title, page_icon=icon, layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def sidebar_brand(title: str, sub: str) -> None:
    html(f'<div class="side-brand"><div class="ball">⚽</div><div><b>{escape(title)}</b><small>{escape(sub)}</small></div></div>')


def hero(eyebrow: str, title: str, sub: str = "", chips: Iterable[str] = (), variant: str = "") -> None:
    chip_html = "".join(f'<span class="chip">{c}</span>' for c in chips)
    html(f'<div class="hero {variant}"><div class="eyebrow">{escape(eyebrow)}</div><h1>{escape(title)}</h1>'
         f'<div class="sub">{escape(sub)}</div>' + (f'<div class="chips">{chip_html}</div>' if chip_html else "") + "</div>")


def kpis(items: Iterable[dict]) -> None:
    """items: {label, value, note?, progress? (0..1)}; tile colours cycle c1..c4."""
    cards = []
    for i, it in enumerate(items):
        bar = ""
        if it.get("progress") is not None:
            bar = f'<div class="bar"><span style="width:{max(0, min(1, it["progress"])) * 100:.0f}%"></span></div>'
        note = f'<div class="note">{escape(str(it["note"]))}</div>' if it.get("note") else ""
        cards.append(f'<div class="kpi c{i % 4 + 1}"><div class="label">{escape(it["label"])}</div>'
                     f'<div class="value">{it["value"]}</div>{note}{bar}</div>')
    html(f'<div class="kpis">{"".join(cards)}</div>')


def section(title: str, hint: str = "") -> None:
    html(f'<div class="section-title">{escape(title)}' + (f'<span class="hint">{escape(hint)}</span>' if hint else "") + "</div>")


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def th_datetime(ts, with_time: bool = True) -> str:
    if ts is None or pd.isna(ts):
        return "ยังไม่กำหนดวัน"
    t = pd.Timestamp(ts)
    t = (t.tz_localize("UTC") if t.tzinfo is None else t).tz_convert("Asia/Bangkok")
    out = f"{TH_DAYS[t.weekday()]} {t.day} {TH_MONTHS[t.month - 1]}"
    return f"{out} · {t:%H:%M}" if with_time else out


def badge(team_id: str, name: str, crest_url=None, size: str = "") -> str:
    if isinstance(crest_url, str) and crest_url:
        return f'<img class="badge {size}" src="{escape(crest_url)}" alt="">'
    bg, fg = team_colors(team_id)
    initials = "".join(w[0] for w in str(name).replace("&", "").split()[:3]).upper()
    return f'<span class="badge {size}" style="background:{bg};color:{fg}">{escape(initials)}</span>'


def form_badges(results: Iterable[str]) -> str:
    return '<span class="form">' + "".join(f'<b class="{r}">{r}</b>' for r in results) + "</span>"


STATUS_LABEL = {"success": "สำเร็จ", "partial": "บางส่วน", "failed": "ล้มเหลว", "running": "กำลังรัน"}


def status_pill(status: str) -> str:
    return f'<span class="pill {escape(status)}">{STATUS_LABEL.get(status, escape(status))}</span>'


def zone(position, n: int) -> str:
    if pd.isna(position):
        return ""
    return "ucl" if position <= 4 else "uel" if position <= 6 else "rel" if position > n - 3 else ""


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------


def standings_table(df: pd.DataFrame, forms: dict[str, list[str]]) -> None:
    n = len(df)
    rows = []
    for r in df.itertuples():
        gd = int(r.goal_difference) if pd.notna(r.goal_difference) else 0
        rows.append(
            f'<tr><td><span class="pos {zone(r.position, n)}">{r.position}</span></td>'
            f'<td class="team">{badge(r.team_id, r.team, r.crest_url)}{escape(r.team)}</td>'
            f"<td>{r.played}</td><td>{r.won}</td><td>{r.draw}</td><td>{r.lost}</td>"
            f"<td>{r.goals_for}:{r.goals_against}</td><td>{gd:+d}</td>"
            f'<td class="pts">{r.points}</td><td>{form_badges(forms.get(r.team_id, []))}</td></tr>'
        )
    html(
        '<div class="table-wrap"><table class="standings"><thead><tr>'
        '<th>#</th><th class="team">ทีม</th><th>แข่ง</th><th>ชนะ</th><th>เสมอ</th><th>แพ้</th>'
        '<th>ได้:เสีย</th><th>+/-</th><th>แต้ม</th><th>ฟอร์ม 5 นัด</th>'
        f'</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
        '<div class="legend"><span><i style="background:var(--ucl)"></i>1–4 แชมเปียนส์ลีก</span>'
        '<span><i style="background:var(--uel)"></i>5–6 ฟุตบอลยุโรป</span>'
        '<span><i style="background:var(--rel)"></i>3 อันดับสุดท้าย ตกชั้น</span>'
        '<span>ฟอร์ม: W ชนะ · D เสมอ · L แพ้ (เก่า → ล่าสุด)</span></div>'
    )


def match_cards(df: pd.DataFrame) -> None:
    """df: matchday, utc_date, status, home_team_id, home, home_crest, away_team_id, away, away_crest, scores"""
    cards = []
    for m in df.itertuples():
        played = m.status == "FINISHED" and pd.notna(m.home_score)
        if played:
            hs, as_ = int(m.home_score), int(m.away_score)
            score = f'<div class="score">{hs} - {as_}</div>'
            home_cls = "win" if hs > as_ else "lose" if hs < as_ else ""
            away_cls = "win" if as_ > hs else "lose" if as_ < hs else ""
            tag = '<span class="tag ft">จบเกม</span>'
        else:
            label = {"POSTPONED": "เลื่อน", "IN_PLAY": "LIVE"}.get(m.status, th_datetime(m.utc_date)[-5:])
            score = f'<div class="score vs">{escape(label)}</div>'
            home_cls = away_cls = ""
            tag = '<span class="tag live">LIVE</span>' if m.status == "IN_PLAY" else ""
        md = f'<span class="tag md">นัดที่ {int(m.matchday)}</span> ' if pd.notna(m.matchday) else ""
        cards.append(
            f'<div class="match"><div class="meta"><span>{md}{th_datetime(m.utc_date, with_time=played)}</span>{tag}</div>'
            f'<div class="row"><div class="side {home_cls}">{badge(m.home_team_id, m.home, m.home_crest)}'
            f'<span class="name">{escape(m.home)}</span></div>{score}'
            f'<div class="side away {away_cls}">{badge(m.away_team_id, m.away, m.away_crest)}'
            f'<span class="name">{escape(m.away)}</span></div></div></div>'
        )
    html(f'<div class="matches">{"".join(cards)}</div>')


def featured_match(m, title: str, positions: dict[str, int]) -> None:
    """Big banner for one match, fading from the home club's colour to the away club's."""
    played = m.status == "FINISHED" and pd.notna(m.home_score)
    mid = (f'<div class="big">{int(m.home_score)} - {int(m.away_score)}</div><div class="small">จบเกม</div>' if played else
           f'<div class="big">{th_datetime(m.utc_date)[-5:]}</div>'
           f'<div class="small">{th_datetime(m.utc_date, False)} · เวลาไทย</div>')

    def side(tid, name, crest):
        pos = positions.get(tid)
        return (f'<div class="side">{badge(tid, name, crest, "lg")}<div class="name">{escape(name)}</div>'
                f'<div class="info">{f"อันดับ {pos}" if pos else ""}</div></div>')

    gradient = (f"background: linear-gradient(100deg, {team_colors(m.home_team_id)[0]} 0%, #1b0b3b 38%, "
                f"#1b0b3b 62%, {team_colors(m.away_team_id)[0]} 100%);")
    md = int(m.matchday) if pd.notna(m.matchday) else "-"
    html(f'<div class="feature" style="{gradient}">'
         f'<div class="top"><span class="tag">{escape(title)}</span><span>นัดที่ {md}</span></div>'
         f'<div class="row">{side(m.home_team_id, m.home, m.home_crest)}<div class="mid">{mid}</div>'
         f'{side(m.away_team_id, m.away, m.away_crest)}</div></div>')


def team_banner(team_id: str, name: str, crest_url, chips: Iterable[str]) -> None:
    color = team_colors(team_id)[0]
    chip_html = "".join(f'<span class="chip">{c}</span>' for c in chips)
    html(f'<div class="feature" style="background: linear-gradient(110deg, {color} 0%, #1b0b3b 70%);">'
         f'<div class="team-banner">{badge(team_id, name, crest_url, "lg")}<div><h2>{escape(name)}</h2>'
         f'<div class="chips" style="margin-top:8px">{chip_html}</div></div></div></div>')


def checklist(dq: pd.DataFrame) -> None:
    items = []
    for r in dq.itertuples():
        if r.passed:
            cls, icon, verdict = "", "✓", "ผ่าน"
        elif r.severity == "error":
            cls, icon, verdict = "error", "✕", f"ไม่ผ่าน · {r.failed_rows} แถว (หยุดการโหลด)"
        else:
            cls, icon, verdict = "warning", "!", f"เตือน · {r.failed_rows} แถว"
        items.append(f'<div class="check {cls}"><div class="ico">{icon}</div><div>'
                     f'<div class="name">{escape(r.entity)} · {escape(r.check_name)}</div>'
                     f'<div class="meta">{verdict}</div></div></div>')
    html(f'<div class="checks">{"".join(items)}</div>')


# ---------------------------------------------------------------------------
# Charts (recessive axes, thin marks, hover tooltips)
# ---------------------------------------------------------------------------


def _style(chart: alt.Chart, height: int) -> alt.Chart:
    return (
        chart.properties(height=height, background="transparent")
        .configure(font="IBM Plex Sans Thai")
        .configure_view(strokeWidth=0)
        .configure_axis(gridColor=GRID, domain=False, tickColor=GRID, labelColor=TEXT_2,
                        titleColor=TEXT_2, labelFontSize=12, titleFontSize=12, titleFontWeight=500)
        .configure_legend(labelColor=TEXT_2, titleColor=TEXT_2, orient="top", labelFontSize=12)
    )


ZONE_LABELS = {"ucl": "แชมเปียนส์ลีก", "uel": "ฟุตบอลยุโรป", "": "กลางตาราง", "rel": "โซนตกชั้น"}


def points_bar(df: pd.DataFrame) -> alt.Chart:
    d = df.assign(zone=[ZONE_LABELS[zone(p, len(df))] for p in df.position])
    order = list(ZONE_LABELS.values())
    base = alt.Chart(d).encode(
        y=alt.Y("team:N", sort=alt.EncodingSortField("points", order="descending"), title=None,
                axis=alt.Axis(labelLimit=240)),
        x=alt.X("points:Q", title="แต้ม"),
        tooltip=[alt.Tooltip("team:N", title="ทีม"), alt.Tooltip("points:Q", title="แต้ม"),
                 alt.Tooltip("played:Q", title="แข่ง"), alt.Tooltip("goal_difference:Q", title="+/-"),
                 alt.Tooltip("zone:N", title="โซน")],
    )
    bars = base.mark_bar(cornerRadiusEnd=4, height={"band": 0.72}).encode(
        color=alt.Color("zone:N", title=None, sort=order,
                        scale=alt.Scale(domain=order, range=[SERIES[0], SERIES[1], NEUTRAL, CRITICAL])))
    labels = base.mark_text(align="left", dx=6, color=TEXT_2, fontSize=11, fontWeight=600).encode(text="points:Q")
    return _style(bars + labels, height=max(220, 26 * len(df)))


def cumulative_points(df: pd.DataFrame) -> alt.Chart:
    """df: matchday, opponent, result, cumulative_points"""
    hover = alt.selection_point(fields=["matchday"], nearest=True, on="pointerover", empty=False)
    base = alt.Chart(df).encode(x=alt.X("matchday:O", title="นัดที่", axis=alt.Axis(labelAngle=0)),
                                y=alt.Y("cumulative_points:Q", title="แต้มสะสม"))
    area = base.mark_area(color=alt.Gradient(
        gradient="linear", x1=1, x2=1, y1=1, y2=0,
        stops=[alt.GradientStop(color="rgba(230,23,111,0)", offset=0),
               alt.GradientStop(color="rgba(230,23,111,0.28)", offset=1)]))
    line = base.mark_line(color=MAGENTA, strokeWidth=2.5)
    dots = base.mark_circle(color=MAGENTA, size=70, stroke="#ffffff", strokeWidth=2).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0.55)),
        tooltip=[alt.Tooltip("matchday:O", title="นัดที่"), alt.Tooltip("opponent:N", title="คู่แข่ง"),
                 alt.Tooltip("result:N", title="ผล"), alt.Tooltip("cumulative_points:Q", title="แต้มสะสม")],
    ).add_params(hover)
    rule = base.mark_rule(color=MUTED, strokeDash=[3, 3]).encode(
        opacity=alt.condition(hover, alt.value(0.8), alt.value(0)))
    return _style(area + line + rule + dots, height=260)


def goals_per_match(df: pd.DataFrame) -> alt.Chart:
    """df: matchday, opponent, gf, ga -> grouped bars (ได้ vs เสีย)."""
    long = df.melt(id_vars=["matchday", "opponent"], value_vars=["gf", "ga"], var_name="kind", value_name="goals")
    long["kind"] = long["kind"].map({"gf": "ประตูได้", "ga": "ประตูเสีย"})
    chart = alt.Chart(long).mark_bar(cornerRadiusEnd=4, stroke="#f4f2f8", strokeWidth=2).encode(
        x=alt.X("matchday:O", title="นัดที่", axis=alt.Axis(labelAngle=0)),
        xOffset=alt.XOffset("kind:N", sort=["ประตูได้", "ประตูเสีย"]),
        y=alt.Y("goals:Q", title="ประตู", axis=alt.Axis(tickMinStep=1)),
        color=alt.Color("kind:N", sort=["ประตูได้", "ประตูเสีย"], title=None, scale=alt.Scale(range=SERIES[:2])),
        tooltip=[alt.Tooltip("matchday:O", title="นัดที่"), alt.Tooltip("opponent:N", title="คู่แข่ง"),
                 alt.Tooltip("kind:N", title=" "), alt.Tooltip("goals:Q", title="ประตู")],
    )
    return _style(chart, height=260)


def ingestion_lines(df: pd.DataFrame) -> alt.Chart:
    """df: fetched_at, source, records"""
    sources = sorted(df["source"].unique())
    hover = alt.selection_point(fields=["fetched_at"], nearest=True, on="pointerover", empty=False)
    base = alt.Chart(df).encode(
        x=alt.X("fetched_at:T", title=None),
        y=alt.Y("records:Q", title="จำนวนรายการ"),
        color=alt.Color("source:N", title=None, sort=sources, scale=alt.Scale(domain=sources, range=SERIES)),
    )
    lines = base.mark_line(strokeWidth=2)
    dots = base.mark_circle(size=64).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0)),
        tooltip=[alt.Tooltip("fetched_at:T", title="เวลา", format="%d %b %H:%M"),
                 alt.Tooltip("source:N", title="แหล่ง"), alt.Tooltip("records:Q", title="รายการ")],
    ).add_params(hover)
    return _style(lines + dots, height=260)


def run_durations(df: pd.DataFrame) -> alt.Chart:
    """df: started_at, duration_s, status"""
    d = df.assign(สถานะ=df.status.map(STATUS_LABEL))
    order = [STATUS_LABEL[s] for s in ("success", "partial", "failed")]
    chart = alt.Chart(d).mark_bar(cornerRadiusEnd=4, size=12).encode(
        x=alt.X("started_at:T", title=None),
        y=alt.Y("duration_s:Q", title="วินาที"),
        color=alt.Color("สถานะ:N", title=None, sort=order,
                        scale=alt.Scale(domain=order, range=[GOOD, WARNING, CRITICAL])),
        tooltip=[alt.Tooltip("started_at:T", title="เริ่ม", format="%d %b %H:%M"),
                 alt.Tooltip("duration_s:Q", title="วินาที", format=".0f"), alt.Tooltip("สถานะ:N")],
    )
    return _style(chart, height=220)
