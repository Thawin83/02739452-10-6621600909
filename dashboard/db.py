"""Shared DB access for the Streamlit pages."""
from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


@st.cache_resource
def get_engine() -> Engine:
    url = os.getenv("FOOTBALL_DB_URL", "postgresql://airflow:airflow@localhost:5433/airflow")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return create_engine(url, pool_pre_ping=True)


@st.cache_data(ttl=120, show_spinner=False)
def query(sql: str, **params) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


STATUS_BADGE = {"success": "🟢 success", "partial": "🟡 partial", "failed": "🔴 failed", "running": "🔵 running"}
