"""Football data pipeline.

                 ┌─ extract.thesportsdb ───┐                                  ┌─ load ───────┐
start_run ──────►├─ extract.openfootball ──┼─► transform ─► quality_checks ─► route ─┤              ├─► finish_run
                 └─ extract.wikipedia ─────┘   (TaskGroup, parallel)            └─ quarantine ─┘

* Extract tasks run in parallel inside the `extract` TaskGroup and land raw payloads in
  football.raw_ingest (no big XComs).
* transform runs if at least one source produced data (one source down = "partial" run).
* route (branch): data that passes every error-severity check goes to `load`; otherwise it goes to
  `quarantine`, which stores the rejected rows in football.quarantine and never touches the warehouse.
* finish_run always runs and records the final status in football.pipeline_runs.

Demo params (Trigger DAG w/ config) to show the fault-tolerant paths:
    {"simulate_source_down": "thesportsdb"}  -> that extractor fails, the rest is still loaded ("partial")
    {"simulate_bad_data": true}              -> duplicated/negative-score rows -> quarantine branch
"""
from __future__ import annotations

import logging
import os
import re
import shutil
from datetime import timedelta
from pathlib import Path

import pendulum
from airflow.decorators import dag, task
from airflow.exceptions import AirflowFailException
from airflow.models.param import Param
from airflow.operators.python import get_current_context
from airflow.utils.state import TaskInstanceState
from airflow.utils.task_group import TaskGroup
from airflow.utils.trigger_rule import TriggerRule

log = logging.getLogger(__name__)

COMPETITION = os.getenv("COMPETITION_CODE", "PL")
SEASON = int(os.getenv("SEASON", "2026"))
SCHEDULE = os.getenv("PIPELINE_SCHEDULE", "0 */6 * * *")
DATA_DIR = Path(os.getenv("PIPELINE_DATA_DIR", "/opt/airflow/data"))
SCHEMA_SQL = Path(__file__).resolve().parents[1] / "include" / "sql" / "schema.sql"

SOURCES = ("thesportsdb", "openfootball", "wikipedia")
CORE_TASKS = {"start_run", "transform", "quality_checks", "route", "load", "quarantine"}


def _staging_dir(run_id: str) -> Path:
    return DATA_DIR / "staging" / re.sub(r"[^A-Za-z0-9_.-]", "_", run_id)


@dag(
    dag_id="football_pipeline",
    schedule=SCHEDULE,
    start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={"owner": "data-eng", "retries": 1, "retry_delay": timedelta(minutes=2)},
    params={
        "simulate_source_down": Param("", type="string", enum=["", *SOURCES],
                                      description="Demo: make this source's extractor fail"),
        "simulate_bad_data": Param(False, type="boolean",
                                   description="Demo: inject invalid rows so data quality fails"),
    },
    tags=["football", "etl"],
    doc_md=__doc__,
)
def football_pipeline():
    @task
    def start_run() -> str:
        from include.load import connect, run_sql_file, start_run as start_run_record

        pipeline_run_id = get_current_context()["run_id"]
        with connect() as conn:
            run_sql_file(conn, SCHEMA_SQL)
            start_run_record(conn, pipeline_run_id, COMPETITION, SEASON)
        return pipeline_run_id

    @task(retries=3, retry_delay=timedelta(minutes=1), retry_exponential_backoff=True)
    def extract(source: str, pipeline_run_id: str) -> dict[str, int]:
        from include.extractors import get_extractor
        from include.load import connect, save_raw

        if get_current_context()["params"].get("simulate_source_down") == source:
            raise AirflowFailException(f"simulated outage of source {source!r}")

        payload = get_extractor(source, COMPETITION, SEASON).extract()
        with connect() as conn:
            counts = save_raw(conn, pipeline_run_id, source, payload)
        log.info("%s extracted: %s", source, counts)
        return counts

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def transform(pipeline_run_id: str) -> dict[str, int]:
        from include.load import connect, fetch_raw, update_run
        from include.transform import build_dataset, inject_bad_rows, save_frames

        with connect() as conn:
            raw = fetch_raw(conn, pipeline_run_id)
            update_run(conn, pipeline_run_id, rows_extracted={
                src: {entity: len(records) for entity, records in entities.items()}
                for src, entities in raw.items()
            })
        if not any(records for entities in raw.values() for records in entities.values()):
            raise AirflowFailException("no source returned any data")

        frames = build_dataset(raw, COMPETITION, SEASON)
        if get_current_context()["params"].get("simulate_bad_data"):
            log.warning("simulate_bad_data=true: injecting invalid rows")
            frames = inject_bad_rows(frames)
        save_frames(frames, _staging_dir(pipeline_run_id))
        return {name: len(df) for name, df in frames.items()}

    @task
    def quality_checks(pipeline_run_id: str) -> list[str]:
        """Runs every check, stores the results, returns the blocking (error) failures."""
        from include.load import connect, save_dq_results
        from include.quality import run_all_checks
        from include.transform import load_frames

        results = run_all_checks(load_frames(_staging_dir(pipeline_run_id)))
        with connect() as conn:
            save_dq_results(conn, pipeline_run_id, results)

        for r in results:
            level = logging.INFO if r.passed else (logging.ERROR if r.blocking else logging.WARNING)
            log.log(level, "[%s] %s.%s failed_rows=%d %s", r.severity, r.entity, r.check_name,
                    r.failed_rows, "" if r.passed else r.details)
        return [f"{r.entity}.{r.check_name}" for r in results if r.blocking]

    @task.branch
    def route(blocking: list[str]) -> str:
        if blocking:
            log.error("data quality failed %s -> quarantine", blocking)
            return "quarantine"
        return "load"

    @task
    def load(pipeline_run_id: str) -> dict[str, dict[str, int]]:
        from include.load import connect, load_dataset, update_run
        from include.transform import load_frames

        frames = load_frames(_staging_dir(pipeline_run_id))
        with connect() as conn:
            stats = load_dataset(conn, frames)
            update_run(conn, pipeline_run_id, rows_loaded=stats)
        return stats

    @task
    def quarantine(pipeline_run_id: str, blocking: list[str]) -> dict[str, int]:
        """Rejected data is kept for inspection but never loaded into the warehouse tables."""
        from include.load import connect, save_quarantine
        from include.transform import load_frames

        frames = load_frames(_staging_dir(pipeline_run_id))
        with connect() as conn:
            counts = save_quarantine(conn, pipeline_run_id, frames, blocking)
        log.warning("quarantined %s because of %s", counts, blocking)
        return counts

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def finish_run() -> None:
        from include.load import connect, finish_run as finish_run_record

        dag_run = get_current_context()["dag_run"]
        states = {ti.task_id: ti.state for ti in dag_run.get_task_instances() if ti.task_id != "finish_run"}
        failed = sorted(t for t, s in states.items()
                        if s in (TaskInstanceState.FAILED, TaskInstanceState.UPSTREAM_FAILED))
        quarantined = states.get("quarantine") == TaskInstanceState.SUCCESS

        error = f"failed tasks: {', '.join(failed)}" if failed else None
        if quarantined:
            status, error = "failed", "data quality failed: data sent to quarantine, not loaded"
        elif not failed:
            status = "success"
        elif CORE_TASKS & set(failed):
            status = "failed"
        else:
            status = "partial"  # some extractor failed but the rest loaded fine

        with connect() as conn:
            finish_run_record(conn, dag_run.run_id, status, failed, error=error)

        shutil.rmtree(_staging_dir(dag_run.run_id), ignore_errors=True)
        if status == "failed":
            raise AirflowFailException(error)

    pipeline_run_id = start_run()
    with TaskGroup("extract", tooltip="Extract every source in parallel") as extract_group:
        for source in SOURCES:
            extract.override(task_id=source)(source=source, pipeline_run_id=pipeline_run_id)

    transformed = transform(pipeline_run_id)
    blocking = quality_checks(pipeline_run_id)
    branch = route(blocking)
    loaded = load(pipeline_run_id)
    rejected = quarantine(pipeline_run_id, blocking)

    extract_group >> transformed >> blocking
    branch >> [loaded, rejected]
    [loaded, rejected] >> finish_run()


football_pipeline()
