"""Pipeline health: run history, data quality results and ingestion volume per source."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import ui
from db import query

ui.setup_page("Pipeline Status", "🛠️")
with st.sidebar:
    ui.sidebar_brand("Football Hub", "Data Pipeline Dashboard")
ui.hero("Data Pipeline", "สถานะ Pipeline", "ประวัติการรัน ผลตรวจคุณภาพข้อมูล และปริมาณข้อมูลจากแต่ละแหล่ง",
        ["Airflow · ทุก 6 ชั่วโมง", "แหล่งข้อมูล <b>3</b> แหล่ง"], variant="alt")

runs = query(
    """
    SELECT run_id, status, competition, season, started_at, finished_at,
           EXTRACT(EPOCH FROM finished_at - started_at) AS duration_s,
           rows_extracted, rows_loaded, failed_tasks, error
    FROM football.pipeline_runs
    ORDER BY started_at DESC
    LIMIT 100
    """
)
if runs.empty:
    st.info("ยังไม่มีการรัน pipeline")
    st.stop()

# --- KPIs ----------------------------------------------------------------------
recent = runs.head(20)
done = recent[recent.status != "running"]
last_success = runs.loc[runs.status == "success", "finished_at"]
ok_rate = (done.status == "success").mean() if len(done) else None
ui.kpis([
    {"label": "รอบล่าสุด", "value": ui.status_pill(runs.status[0]), "note": ui.th_datetime(runs.started_at[0])},
    {"label": "อัตราสำเร็จ (20 รอบล่าสุด)", "value": f"{ok_rate:.0%}" if ok_rate is not None else "–",
     "progress": ok_rate},
    {"label": "เวลารันเฉลี่ย", "value": f"{done.duration_s.mean():.0f} วิ" if done.duration_s.notna().any() else "–"},
    {"label": "สำเร็จล่าสุดเมื่อ", "value": ui.th_datetime(last_success.iloc[0], with_time=False)
     if not last_success.empty else "ยังไม่เคย",
     "note": ui.th_datetime(last_success.iloc[0])[-5:] + " น." if not last_success.empty else None},
])

tab_dq, tab_history, tab_volume = st.tabs(["✅  คุณภาพข้อมูล", "🕒  ประวัติการรัน", "📥  ปริมาณข้อมูล"])

# --- Data quality for a selected run -------------------------------------------------
with tab_dq:
    run_id = st.selectbox(
        "รอบที่ต้องการดู", runs.run_id,
        format_func=lambda r: f"{ui.th_datetime(runs.set_index('run_id').started_at[r])} — "
                              f"{ui.STATUS_LABEL.get(runs.set_index('run_id').status[r], '')}",
    )
    run = runs[runs.run_id == run_id].iloc[0]
    if run.failed_tasks:
        st.error(f"Task ที่ล้ม: {', '.join(run.failed_tasks)}")
    quarantined = query(
        "SELECT entity, record_count, failed_checks FROM football.quarantine WHERE run_id = :r ORDER BY entity",
        r=run_id,
    )
    if not quarantined.empty:
        st.warning(
            "🚧 ข้อมูลรอบนี้ไม่ผ่านการตรวจคุณภาพ จึงถูกส่งเข้า **quarantine** (ไม่ถูกโหลดเข้าตารางหลัก) · "
            f"ตรวจไม่ผ่าน: {', '.join(quarantined.failed_checks.iloc[0])} · "
            + ", ".join(f"{r.entity} {r.record_count} แถว" for r in quarantined.itertuples())
        )

    dq = query(
        """
        SELECT entity, check_name, severity, passed, failed_rows, details
        FROM football.dq_results WHERE run_id = :r
        ORDER BY passed, severity, entity, check_name
        """,
        r=run_id,
    )
    if dq.empty:
        st.info("ไม่มีผลตรวจคุณภาพสำหรับรอบนี้ (อาจล้มก่อนถึงขั้น quality_checks)")
    else:
        errors = int((~dq.passed & (dq.severity == "error")).sum())
        warnings = int((~dq.passed & (dq.severity == "warning")).sum())
        ui.section("ผลตรวจคุณภาพข้อมูล",
                   f"ผ่าน {int(dq.passed.sum())}/{len(dq)} · ไม่ผ่าน {errors} · เตือน {warnings}")
        ui.checklist(dq)
        for row in dq[~dq.passed].itertuples():
            with st.expander(f"รายละเอียด: {row.entity}.{row.check_name} ({row.failed_rows} แถว)"):
                st.json(row.details)

    ui.section("จำนวนข้อมูลของรอบนี้")
    c1, c2 = st.columns(2)
    with c1:
        st.caption("ดึงมาได้ (แยกตามแหล่ง)")
        extracted = pd.DataFrame(run.rows_extracted or {}).T.fillna(0).astype(int)
        st.dataframe(extracted, use_container_width=True)
    with c2:
        st.caption("โหลดเข้าฐานข้อมูล")
        loaded = pd.DataFrame(run.rows_loaded or {}).T
        st.dataframe(loaded.rename(columns={"inserted": "เพิ่มใหม่", "updated": "อัปเดต", "unchanged": "ไม่เปลี่ยน"}),
                     use_container_width=True)

# --- Run history -----------------------------------------------------------------
with tab_history:
    ui.section("เวลาที่ใช้ต่อรอบ")
    timed = runs.dropna(subset=["duration_s"])
    if not timed.empty:
        st.altair_chart(ui.run_durations(timed), use_container_width=True)
    ui.section("ประวัติทั้งหมด")
    history = runs.assign(
        สถานะ=runs.status.map(lambda s: {"success": "✅ สำเร็จ", "partial": "⚠️ บางส่วน",
                                         "failed": "❌ ล้มเหลว", "running": "🔵 กำลังรัน"}.get(s, s)),
        เริ่ม=runs.started_at.map(ui.th_datetime),
    )
    st.dataframe(
        history[["เริ่ม", "สถานะ", "duration_s", "failed_tasks", "run_id"]],
        hide_index=True, use_container_width=True,
        column_config={"duration_s": st.column_config.NumberColumn("ใช้เวลา (วิ)", format="%.0f"),
                       "failed_tasks": "Task ที่ล้ม", "run_id": "Run ID"},
    )

# --- Ingestion volume ------------------------------------------------------------
with tab_volume:
    volume = query(
        """
        SELECT date_trunc('hour', fetched_at) AS fetched_at, source, SUM(record_count) AS records
        FROM football.raw_ingest
        WHERE fetched_at > now() - interval '14 days'
        GROUP BY 1, 2 ORDER BY 1
        """
    )
    if volume.empty:
        st.info("ยังไม่มีข้อมูล")
    else:
        ui.section("จำนวนรายการที่ดึงได้ต่อแหล่ง", "14 วันล่าสุด")
        st.altair_chart(ui.ingestion_lines(volume), use_container_width=True)
        with st.expander("ดูเป็นตาราง"):
            st.dataframe(volume.pivot_table(index="fetched_at", columns="source", values="records", aggfunc="sum"),
                         use_container_width=True)
