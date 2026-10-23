"""Postgres helpers: connection, generic UPSERT, raw landing and run bookkeeping."""
from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

import pandas as pd
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import connection as PGConnection
from psycopg2.extras import Json, execute_values

log = logging.getLogger(__name__)


@contextmanager
def connect(dsn: str | None = None) -> Iterator[PGConnection]:
    """Commit on success, roll back on error, always close."""
    conn = psycopg2.connect(dsn or os.environ["FOOTBALL_DB_URL"])
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def run_sql_file(conn: PGConnection, path: str | Path) -> None:
    with conn.cursor() as cur:
        cur.execute(Path(path).read_text(encoding="utf-8"))


def _adapt(value: Any) -> Any:
    if isinstance(value, dict):
        return Json(value)
    if isinstance(value, (list, tuple)):
        return list(value)
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value.item() if hasattr(value, "item") else value  # numpy scalar -> python


def df_to_rows(df: pd.DataFrame, cols: Sequence[str]) -> list[dict[str, Any]]:
    return [{c: _adapt(v) for c, v in zip(cols, rec)} for rec in df[list(cols)].itertuples(index=False)]


def upsert(
    conn: PGConnection,
    table: str,
    rows: Sequence[dict[str, Any]],
    key_cols: Sequence[str],
    update_cols: Sequence[str] | None = None,
    touch_col: str | None = "updated_at",
    page_size: int = 500,
    guard: str | None = None,
) -> dict[str, int]:
    """INSERT ... ON CONFLICT DO UPDATE that only touches rows whose values changed.

    `guard` is an extra SQL condition (over `t.` = stored row and `EXCLUDED.` = incoming row)
    that must hold for an existing row to be updated.
    Returns counts of inserted / updated / unchanged rows.
    """
    if not rows:
        return {"inserted": 0, "updated": 0, "unchanged": 0}

    # Last row wins for duplicate keys inside one batch (Postgres rejects them otherwise).
    unique = list({tuple(r[k] for k in key_cols): r for r in rows}.values())
    cols = list(unique[0].keys())
    updates = [c for c in (update_cols or cols) if c not in key_cols]

    schema, name = table.split(".")
    ident = sql.Identifier
    query = sql.SQL("INSERT INTO {tbl} AS t ({cols}) VALUES %s ON CONFLICT ({keys}) ").format(
        tbl=ident(schema, name),
        cols=sql.SQL(", ").join(map(ident, cols)),
        keys=sql.SQL(", ").join(map(ident, key_cols)),
    )
    if updates:
        sets = [sql.SQL("{c} = EXCLUDED.{c}").format(c=ident(c)) for c in updates]
        if touch_col:
            sets.append(sql.SQL("{c} = now()").format(c=ident(touch_col)))
        query += sql.SQL("DO UPDATE SET {sets} WHERE ({old}) IS DISTINCT FROM ({new}){guard} "
                         "RETURNING (xmax = 0) AS inserted").format(
            sets=sql.SQL(", ").join(sets),
            old=sql.SQL(", ").join(sql.SQL("t.{}").format(ident(c)) for c in updates),
            new=sql.SQL(", ").join(sql.SQL("EXCLUDED.{}").format(ident(c)) for c in updates),
            guard=sql.SQL(f" AND ({guard})") if guard else sql.SQL(""),
        )
    else:
        query += sql.SQL("DO NOTHING RETURNING true AS inserted")

    values = [tuple(_adapt(r[c]) for c in cols) for r in unique]
    with conn.cursor() as cur:
        returned = execute_values(cur, query.as_string(conn), values, page_size=page_size, fetch=True)

    inserted = sum(1 for (flag,) in returned if flag)
    stats = {"inserted": inserted, "updated": len(returned) - inserted, "unchanged": len(unique) - len(returned)}
    log.info("upsert %s: %s", table, stats)
    return stats


# ---------------------------------------------------------------------------
# Canonical model
# ---------------------------------------------------------------------------
TEAM_LOAD_COLS = ["team_id", "name", "short_name", "tla", "founded", "venue", "crest_url", "website", "sources"]
# A run where the freshest source is down must not roll a played match back to "scheduled".
KEEP_FINISHED_RESULTS = "NOT (t.status = 'FINISHED' AND EXCLUDED.status <> 'FINISHED')"
MATCH_LOAD_COLS = ["match_id", "competition", "season", "matchday", "utc_date", "status", "home_team_id",
                   "away_team_id", "home_score", "away_score", "source", "source_match_id"]
STANDING_LOAD_COLS = ["competition", "season", "team_id", "position", "played", "won", "draw", "lost",
                      "goals_for", "goals_against", "goal_difference", "points", "source"]


def load_dataset(conn: PGConnection, frames: dict[str, pd.DataFrame]) -> dict[str, dict[str, int]]:
    """Load in FK order: teams -> aliases -> matches -> standings (one transaction)."""
    return {
        "teams": upsert(conn, "football.teams", df_to_rows(frames["teams"], TEAM_LOAD_COLS), ["team_id"]),
        "team_aliases": upsert(conn, "football.team_aliases",
                               df_to_rows(frames["aliases"], ["alias", "source", "team_id"]), ["alias", "source"]),
        "matches": upsert(conn, "football.matches", df_to_rows(frames["matches"], MATCH_LOAD_COLS), ["match_id"],
                          guard=KEEP_FINISHED_RESULTS),
        "standings": upsert(conn, "football.standings", df_to_rows(frames["standings"], STANDING_LOAD_COLS),
                            ["competition", "season", "team_id"]),
    }


# ---------------------------------------------------------------------------
# Raw landing zone
# ---------------------------------------------------------------------------


def save_raw(conn: PGConnection, run_id: str, source: str, payload: dict[str, list[Any]]) -> dict[str, int]:
    counts = {}
    with conn.cursor() as cur:
        for entity, records in payload.items():
            cur.execute(
                """
                INSERT INTO football.raw_ingest (run_id, source, entity, record_count, payload)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (run_id, source, entity) DO UPDATE
                SET record_count = EXCLUDED.record_count, payload = EXCLUDED.payload, fetched_at = now()
                """,
                (run_id, source, entity, len(records), Json(records)),
            )
            counts[entity] = len(records)
    return counts


def fetch_raw(conn: PGConnection, run_id: str) -> dict[str, dict[str, list[Any]]]:
    with conn.cursor() as cur:
        cur.execute("SELECT source, entity, payload FROM football.raw_ingest WHERE run_id = %s", (run_id,))
        raw: dict[str, dict[str, list[Any]]] = {}
        for source, entity, payload in cur.fetchall():
            raw.setdefault(source, {})[entity] = payload
    return raw


# ---------------------------------------------------------------------------
# Run bookkeeping
# ---------------------------------------------------------------------------


def start_run(conn: PGConnection, run_id: str, competition: str, season: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO football.pipeline_runs (run_id, competition, season, status, started_at)
            VALUES (%s, %s, %s, 'running', now())
            ON CONFLICT (run_id) DO UPDATE
            SET status = 'running', started_at = now(), finished_at = NULL, failed_tasks = NULL, error = NULL
            """,
            (run_id, competition, season),
        )


def update_run(conn: PGConnection, run_id: str, *, rows_extracted: dict | None = None,
               rows_loaded: dict | None = None) -> None:
    with conn.cursor() as cur:
        if rows_extracted is not None:
            cur.execute("UPDATE football.pipeline_runs SET rows_extracted = %s WHERE run_id = %s",
                        (Json(rows_extracted), run_id))
        if rows_loaded is not None:
            cur.execute("UPDATE football.pipeline_runs SET rows_loaded = %s WHERE run_id = %s",
                        (Json(rows_loaded), run_id))


def finish_run(conn: PGConnection, run_id: str, status: str, failed_tasks: list[str],
               error: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO football.pipeline_runs (run_id, status, finished_at, failed_tasks, error)
            VALUES (%s, %s, now(), %s, %s)
            ON CONFLICT (run_id) DO UPDATE
            SET status = EXCLUDED.status, finished_at = now(),
                failed_tasks = EXCLUDED.failed_tasks, error = EXCLUDED.error
            """,
            (run_id, status, failed_tasks or None, error),
        )


def save_dq_results(conn: PGConnection, run_id: str, results: Sequence[Any]) -> None:
    """Replace this run's DQ results (task retries must not duplicate them)."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM football.dq_results WHERE run_id = %s", (run_id,))
        execute_values(
            cur,
            "INSERT INTO football.dq_results (run_id, check_name, entity, severity, passed, failed_rows, details) "
            "VALUES %s",
            [(run_id, r.check_name, r.entity, r.severity, r.passed, r.failed_rows, Json(r.details))
             for r in results],
        )


def save_quarantine(conn: PGConnection, run_id: str, frames: dict[str, pd.DataFrame],
                    failed_checks: Sequence[str]) -> dict[str, int]:
    """Store the rejected dataset of a run (one row per entity) for later inspection."""
    counts = {}
    with conn.cursor() as cur:
        for entity, df in frames.items():
            records = json.loads(df.to_json(orient="records", date_format="iso", default_handler=str))
            cur.execute(
                """
                INSERT INTO football.quarantine (run_id, entity, failed_checks, record_count, records)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (run_id, entity) DO UPDATE
                SET failed_checks = EXCLUDED.failed_checks, record_count = EXCLUDED.record_count,
                    records = EXCLUDED.records, quarantined_at = now()
                """,
                (run_id, entity, list(failed_checks), len(records), Json(records)),
            )
            counts[entity] = len(records)
    return counts
