# Football Data Pipeline

Pipeline ดึงข้อมูลฟุตบอลจาก 3 แหล่ง → แปลงเป็น schema กลาง → ตรวจคุณภาพข้อมูล → UPSERT ลง PostgreSQL → แสดงผลบน Streamlit dashboard โดยมี Airflow เป็นตัว orchestrate

```
              ┌ TaskGroup "extract" (ขนาน) ┐
              │ thesportsdb     (API)      │                                    ┌─► load (UPSERT) ──┐
start_run ───►│ openfootball (open data)   ├─► transform ─► quality_checks ─► route                  ├─► finish_run
              │ wikipedia (web scraping)   │   (schema กลาง,                    └─► quarantine ─────┘
              └────────────────────────────┘    dedup)                         (branch: ผ่าน/ไม่ผ่าน DQ)
```

## เริ่มใช้งาน

```bash
cp .env.example .env          # ไม่ต้องใช้ API key เพิ่ม (TheSportsDB ใช้ key สาธารณะ "123")
docker compose up -d
```

| Service       | URL                     | Login         |
|---------------|-------------------------|---------------|
| Airflow       | http://localhost:8080   | admin / admin |
| Dashboard     | http://localhost:8501   | –             |
| Postgres      | localhost:5433          | airflow / airflow (schema `football`) |

DAG `football_pipeline` จะรันตาม `PIPELINE_SCHEDULE` (ค่าเริ่มต้นทุก 6 ชม.) หรือกด ▶ Trigger ใน Airflow UI ได้เลย

### แหล่งข้อมูล (ไม่ต้องสมัคร / ไม่ต้องใช้ key ส่วนตัว)

| แหล่ง | ประเภท | ข้อมูลที่ได้ |
|---|---|---|
| [TheSportsDB](https://www.thesportsdb.com/free_sports_api) | REST API (key สาธารณะ `123`) | แมตช์ทั้งฤดูกาล + สกอร์, ตารางคะแนน (5 อันดับแรก) |
| [openfootball/football.json](https://github.com/openfootball/football.json) | Open data JSON (public domain) | แมตช์ทั้งฤดูกาล + สกอร์ |
| [Wikipedia](https://en.wikipedia.org/) | Web scraping (requests + BeautifulSoup) | ตารางคะแนนครบทุกทีม |

## โครงสร้าง

```
dags/football_pipeline_dag.py   DAG: start_run → TaskGroup extract×3 → transform → quality_checks → route → load | quarantine → finish_run
include/extractors/             ดึง raw payload จากแต่ละแหล่ง (retry 429/5xx อัตโนมัติ)
include/transform.py            normalize → schema กลาง, team-name mapping, dedup ข้ามแหล่ง
include/quality.py              data quality checks (error / warning)
include/load.py                 UPSERT helpers, raw landing, บันทึกสถานะการรัน
include/sql/schema.sql          DDL (idempotent)
dashboard/app.py                เมนูนำทาง (st.navigation)
dashboard/views/overview.py     ตารางคะแนน, ผลการแข่ง, โปรแกรม, วิเคราะห์ทีม
dashboard/ui.py                 ธีม, CSS, การ์ด และกราฟ (Altair) ที่ใช้ร่วมกัน
dashboard/views/pipeline_status.py  ประวัติการรัน, ผล DQ, ปริมาณข้อมูลต่อแหล่ง
tests/                          unit tests: transform, quality, dedup, compliance (PDPA / robots.txt / quarantine)
```

## หลักการออกแบบ

**Raw landing** — extract task เก็บ payload ดิบลง `football.raw_ingest` (ไม่ส่งข้อมูลก้อนใหญ่ผ่าน XCom) ทำให้ replay/debug ย้อนหลังได้

**Team-name mapping** — แต่ละแหล่งเรียกชื่อทีมต่างกัน (`Manchester United FC`, `Man United`, `Man Utd`)
`normalize_team_name()` ตัด accent, เครื่องหมาย, footnote `[a]`, marker `(C)`, คำว่า FC/AFC แล้วเทียบกับ `CANONICAL_TEAMS`
ทีมที่ไม่รู้จักจะได้ slug อัตโนมัติ และถูกแจ้งเป็น warning `unmapped_team_names` → เพิ่มลง `CANONICAL_TEAMS` ได้เลย
ทุกชื่อที่เคยเห็นถูกเก็บใน `football.team_aliases` ไว้ตรวจสอบย้อนหลัง

**Dedup ข้ามแหล่ง**
- `match_id = <comp>-<season>-<home>-vs-<away>` — ในลีกแต่ละคู่เหย้า/เยือนเจอกันครั้งเดียวต่อฤดูกาล key จึงไม่เปลี่ยนแม้เลื่อนวันแข่ง
- ถ้าแหล่งหนึ่งมีผล FINISHED แล้วจะชนะแหล่งที่ยังเป็น SCHEDULED, นอกนั้นใช้ลำดับ `thesportsdb > openfootball > wikipedia`
- ข้อมูลทีม merge ราย column (ค่าที่แหล่งหนึ่งไม่มีจะเติมจากอีกแหล่ง)

**Data quality + branching** — task `route` (`@task.branch`) แตกเส้นทาง: ผ่านทุก check ระดับ `error` → `load`,
ไม่ผ่าน → `quarantine` (เก็บข้อมูลที่ถูกปฏิเสธไว้ใน `football.quarantine` และไม่แตะตารางหลัก) ส่วน `warning` แค่บันทึกและแสดงบน dashboard

| Check | Severity |
|---|---|
| row count, not null, unique key | error |
| status ถูกต้อง, คะแนนครบและไม่ติดลบ, ทีมเหย้า ≠ ทีมเยือน, FK ทีม | error |
| standings: P = W+D+L, GD = GF−GA | error |
| Pts = 3W+D (อาจผิดได้จริงเมื่อโดนตัดแต้ม) | warning |
| ตำแหน่ง 1..n ไม่ซ้ำ, แข่งยังไม่จบแต่มีสกอร์ | warning |
| แต้มต่างกันระหว่างแหล่ง (เทียบเฉพาะที่จำนวนนัดเท่ากัน) | warning |
| ชื่อทีมที่ map ไม่ได้ | warning |

**UPSERT** — `INSERT … ON CONFLICT DO UPDATE … WHERE (old) IS DISTINCT FROM (new)` อัปเดต `updated_at` เฉพาะแถวที่ค่าเปลี่ยนจริง และรายงานจำนวน inserted / updated / unchanged ลง `pipeline_runs.rows_loaded`

**สถานะการรัน** — `finish_run` รันเสมอ: `success`, `partial` (บางแหล่งล้มแต่ที่เหลือโหลดได้), `failed` (ขั้น transform/load ล้ม หรือข้อมูลถูกส่งเข้า quarantine)

**ทนต่อแหล่งข้อมูลล่ม** — extract แต่ละแหล่งเป็น task แยกใน TaskGroup, `transform` ใช้ `trigger_rule=ALL_DONE`
จึงรวมข้อมูลจากแหล่งที่เหลือต่อได้ และรอบนั้นถูกบันทึกเป็น `partial`

## การปฏิบัติตามข้อกำหนด

- **Web scraping ไม่ใช้ Selenium** — Wikipedia ใช้ `requests` + `BeautifulSoup` เท่านั้น
- **robots.txt** — `check_robots()` ใน `include/extractors/wikipedia_scraper.py` (ใช้กับ Wikipedia และ openfootball) อ่าน `robots.txt` ด้วย `urllib.robotparser`
  ก่อนดึงทุกครั้ง ถ้า URL ไม่ได้รับอนุญาตสำหรับ User-Agent `football-pipeline/1.0` จะหยุดโดยไม่ request หน้านั้น
  ทุก request ระบุ User-Agent ชัดเจน และดึงเพียง 1 หน้าต่อรอบ
- **PDPA** — เก็บเฉพาะข้อมูลระดับสโมสร/แมตช์ (ชื่อทีม สนาม สกอร์ ตารางคะแนน) ฟิลด์ที่ระบุตัวบุคคล
  (`strReferee`, `strManager`, lineup, ผู้ทำประตู `goals1`/`goals2` ฯลฯ — ดู `PERSONAL_FIELDS`)
  ถูกตัดทิ้งใน extractor **ก่อน**บันทึก แม้แต่ในตาราง raw
- **ข้อมูล ≥ 100 รายการ** — แมตช์ทั้งฤดูกาล 380 รายการ + ทีม 20 + ตารางคะแนน 20
- **Dashboard อ่าน PostgreSQL โดยตรง** — Streamlit query ผ่าน SQLAlchemy

## สาธิตกรณีผิดปกติ (Trigger DAG w/ config)

| config | ผลที่คาดหวัง |
|---|---|
| `{"simulate_source_down": "wikipedia"}` | `extract.wikipedia` ล้ม แต่ DAG รวมข้อมูลจากแหล่งที่เหลือและ load ต่อ → สถานะ `partial` |
| `{"simulate_source_down": "thesportsdb"}` | เหมือนกัน — แมตช์ยังได้จาก openfootball (ผลบางนัดอาจยังไม่อัปเดตเพราะแหล่งนี้ช้ากว่า) |
| `{"simulate_bad_data": true}` | ใส่แถวซ้ำ/สกอร์ติดลบ → DQ ไม่ผ่าน → `route` เลือก `quarantine` (`load` ถูก skip) |

## Tests

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt     # Linux/macOS: .venv/bin/pip
.venv/Scripts/python -m pytest -q tests
```

## ข้อจำกัดที่ควรรู้

- **TheSportsDB free key (`123`)**: `lookup_all_teams` คืนลีกตัวอย่างตายตัว (extractor กรองทิ้งให้แล้ว), ตารางคะแนนได้แค่ 5 แถว และจำกัดจำนวน request ต่อนาที (รอบปกติใช้เวลาราว 3–8 นาทีเพราะต้องดึงทีละ matchday)
- **openfootball**: อัปเดตโดยอาสาสมัคร ผลบางนัดอาจช้ากว่า TheSportsDB 1–2 วัน (dedup จะเลือกแถวที่จบแล้วให้อัตโนมัติ)
- **Wikipedia**: ขึ้นกับโครงสร้างหน้าเว็บ ถ้าหาตารางไม่เจอจะได้ 0 แถวและมี log เตือน
- `raw_ingest` โตขึ้นทุกรอบ ควรตั้ง retention เช่น `DELETE FROM football.raw_ingest WHERE fetched_at < now() - interval '30 days'`
- `_PIP_ADDITIONAL_REQUIREMENTS` เหมาะกับ dev เท่านั้น production ควร build image เอง
