"""Streamlit dashboard for the local data intelligence platform."""

from __future__ import annotations

import logging
from html import escape
from typing import Any

import httpx
import pandas as pd
import streamlit as st
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.db.connection import create_database_engine

LOGGER = logging.getLogger(__name__)


class DashboardSettings(BaseSettings):
    """Dashboard configuration loaded from the environment or project .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_base_url: str = "http://127.0.0.1:8000"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"


@st.cache_resource
def get_engine() -> Engine:
    """Create one reusable PostgreSQL engine for this Streamlit process."""
    return create_database_engine()


def load_dashboard_data(engine: Engine) -> dict[str, Any]:
    """Load bounded dashboard aggregates and recent metadata from PostgreSQL."""
    statements = {
        "sources": text(
            "SELECT count(*) FROM source_registry WHERE enabled = TRUE"
        ),
        "batches_total": text("SELECT count(*) FROM import_batches"),
        "batches_completed": text(
            "SELECT count(*) FROM import_batches WHERE status = 'completed'"
        ),
        "records_loaded": text(
            "SELECT coalesce(sum(records_loaded), 0) FROM import_batches"
        ),
        "results_total": text("SELECT count(*) FROM correlation_results"),
        "results_unreviewed": text(
            "SELECT count(*) FROM correlation_results "
            "WHERE review_status = 'unreviewed'"
        ),
        "batches": text(
            """
            SELECT b.id::text AS batch_id, s.source_name, b.status,
                   b.records_loaded, b.records_rejected, b.created_at
            FROM import_batches AS b
            JOIN source_registry AS s ON s.id = b.source_id
            ORDER BY b.created_at DESC
            LIMIT 6
            """
        ),
        "source_list": text(
            """
            SELECT source_code, source_name, source_type, enabled, authorized_purpose
            FROM source_registry
            ORDER BY source_name
            LIMIT 30
            """
        ),
        "rules": text(
            """
            SELECT rule_code, rule_name, rule_version, enabled
            FROM correlation_rules
            ORDER BY rule_code
            LIMIT 8
            """
        ),
        "audit": text(
            """
            SELECT action, source_code, outcome, created_at
            FROM analysis_audit
            ORDER BY created_at DESC
            LIMIT 20
            """
        ),
        "results": text(
            """
            SELECT left_source, left_record_ref, right_source, right_record_ref,
                   match_method, review_status, created_at
            FROM correlation_results
            ORDER BY created_at DESC
            LIMIT 8
            """
        ),
    }

    with engine.connect() as connection:
        return {
            "sources": connection.execute(statements["sources"]).scalar_one(),
            "batches_total": connection.execute(
                statements["batches_total"]
            ).scalar_one(),
            "batches_completed": connection.execute(
                statements["batches_completed"]
            ).scalar_one(),
            "records_loaded": connection.execute(
                statements["records_loaded"]
            ).scalar_one(),
            "results_total": connection.execute(
                statements["results_total"]
            ).scalar_one(),
            "results_unreviewed": connection.execute(
                statements["results_unreviewed"]
            ).scalar_one(),
            "batches": pd.read_sql(statements["batches"], connection),
            "source_list": pd.read_sql(statements["source_list"], connection),
            "rules": pd.read_sql(statements["rules"], connection),
            "audit": pd.read_sql(statements["audit"], connection),
            "results": pd.read_sql(statements["results"], connection),
        }


def check_service(url: str, path: str = "/health") -> bool:
    """Return whether a local HTTP service responds successfully."""
    try:
        response = httpx.get(f"{url.rstrip('/')}{path}", timeout=1.5)
        return response.is_success
    except httpx.HTTPError:
        return False


def filter_by_time(frame: pd.DataFrame, column: str, time_range: str) -> pd.DataFrame:
    """Filter a bounded result set by its timestamp column."""
    days_by_range = {"24 jam": 1, "7 hari": 7, "30 hari": 30}
    days = days_by_range.get(time_range)
    if days is None or frame.empty:
        return frame

    timestamps = pd.to_datetime(frame[column], utc=True, errors="coerce")
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    return frame.loc[timestamps >= cutoff]


def metric(label: str, value: str, note: str, accent: str = "green") -> None:
    st.markdown(
        f"""
        <div class="metric-card">
          <div class="metric-label">{label}</div>
          <div class="metric-value {accent}">{value}</div>
          <div class="metric-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    settings = DashboardSettings()
    st.set_page_config(
        page_title="Local Intelligence Platform",
        page_icon="✳",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(
        """
        <style>
        :root {
          color-scheme: dark;
          --bg: #080f1c;
          --panel: #0e1929;
          --panel-2: #111f31;
          --border: #20334a;
          --text: #e4edf7;
          --muted: #8296ad;
          --green: #27e0ae;
          --blue: #66b9ff;
          --amber: #eebf62;
        }
        .stApp { background: var(--bg); color: var(--text); }
        [data-testid="stHeader"] { background: rgba(8,15,28,.92); }
        [data-testid="stSidebar"] {
          background: #0d1727;
          border-right: 1px solid var(--border);
        }
        [data-testid="stSidebar"] > div { padding-top: 1rem; }
        .block-container { max-width: 1800px; padding: 1rem 1.4rem 2rem; }
        h1, h2, h3 { color: var(--text) !important; letter-spacing: -.025em; }
        h1 { font-size: 1.32rem !important; }
        h2 { font-size: 1.05rem !important; }
        h3 { font-size: .91rem !important; }
        p, label, [data-testid="stMarkdownContainer"] { color: var(--text); }
        .brand { font-size: 1.08rem; line-height: 1.05; font-weight: 750; color: #f0f7ff; }
        .brand span { color: var(--green); }
        .eyebrow, .muted { color: var(--muted) !important; font-size: .75rem; }
        .topbar, .panel, .metric-card, .chat-card, .rule-card {
          background: var(--panel);
          border: 1px solid var(--border);
          border-radius: 10px;
        }
        .topbar {
          display:flex; align-items:center; justify-content:space-between;
          gap:1rem; padding:.7rem 1rem; margin:.1rem 0 1rem;
        }
        .topbar-title { font-weight:700; font-size:.94rem; }
        .topbar-meta { color:var(--muted); font-size:.72rem; margin-top:.16rem; }
        .pill {
          display:inline-flex; align-items:center; gap:.35rem; padding:.28rem .55rem;
          border:1px solid var(--border); border-radius:999px; font-size:.7rem;
          color:#b8c9dc; white-space:nowrap; margin-left:.25rem;
        }
        .dot { width:7px; height:7px; border-radius:50%; display:inline-block; background:var(--green); }
        .dot.off { background:#77869a; }
        .panel { padding:.9rem 1rem; margin-bottom:.8rem; }
        .panel-title { display:flex; justify-content:space-between; gap:.6rem; align-items:center; margin-bottom:.65rem; }
        .panel-title strong { font-size:.9rem; }
        .metric-card { padding:.8rem .85rem; min-height:104px; }
        .metric-label { font-size:.72rem; color:var(--muted); }
        .metric-value { font-size:1.55rem; font-weight:750; margin:.18rem 0; }
        .metric-value.green { color:var(--green); }
        .metric-value.blue { color:var(--blue); }
        .metric-value.amber { color:var(--amber); }
        .metric-note { color:var(--muted); font-size:.68rem; }
        .chat-card { background:var(--panel-2); padding:.85rem; margin:.55rem 0; }
        .chat-role { color:var(--green); font-size:.68rem; font-weight:700; margin-bottom:.3rem; }
        .chat-copy { color:#cad7e5; font-size:.78rem; line-height:1.55; }
        .rule-card { padding:.7rem .8rem; margin:.45rem 0; }
        .rule-code { color:var(--blue); font-size:.7rem; font-weight:700; }
        .rule-name { font-size:.78rem; margin:.22rem 0; }
        .rule-note { color:var(--muted); font-size:.68rem; }
        div[data-testid="stDataFrame"] { border:1px solid var(--border); border-radius:8px; overflow:hidden; }
        div[data-testid="stFileUploader"] { background:var(--panel-2); border:1px dashed #2b4560; border-radius:8px; }
        .stButton button, .stDownloadButton button { border-radius:7px; }
        .stButton button[kind="primary"] { background:#087e67; border-color:#10bd96; }
        hr { border-color:var(--border); }
        @media (max-width: 800px) {
          .block-container { padding: .8rem .8rem 2rem; }
          .topbar { align-items:flex-start; flex-direction:column; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    app_online = check_service(settings.app_base_url)
    ollama_online = check_service(settings.ollama_base_url, "/api/tags")
    db_data: dict[str, Any] | None = None
    db_error = ""
    try:
        db_data = load_dashboard_data(get_engine())
    except (SQLAlchemyError, ValueError) as exc:
        LOGGER.error("Dashboard PostgreSQL query failed (%s)", type(exc).__name__)
        db_error = (
            "PostgreSQL belum dapat diakses atau migrasi SRS belum diterapkan. "
            "Periksa layanan database dan konfigurasi POSTGRES_*."
        )

    with st.sidebar:
        st.markdown(
            '<div class="brand"><span>✳</span> Local<br>Intelligence</div>',
            unsafe_allow_html=True,
        )
        st.caption("PLATFORM ANALISIS LOKAL")
        st.markdown("---")
        section = st.radio(
            "NAVIGASI",
            ["✳  AI Chat & Analisis", "▤  Input & Knowledge Base", "⌘  Aturan & Audit", "◉  Audit & Status Sistem"],
            label_visibility="visible",
        )
        st.markdown("---")
        st.markdown("**FILTER ANALISIS**")
        time_range = st.selectbox("Rentang waktu", ["Semua waktu", "24 jam", "7 hari", "30 hari"])
        review_filter = st.selectbox(
            "Status review", ["Semua status", "Belum direview", "Dikonfirmasi", "Ditolak"]
        )
        st.markdown("---")
        st.markdown("**STATUS NODE**")
        st.markdown(
            f'<div class="muted">PostgreSQL &nbsp; <span style="color:{"#27e0ae" if db_data else "#eebf62"}">{"TERHUBUNG" if db_data else "BELUM TERHUBUNG"}</span></div>'
            f'<div class="muted">FastAPI &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <span style="color:{"#27e0ae" if app_online else "#eebf62"}">{"ONLINE" if app_online else "OFFLINE"}</span></div>'
            f'<div class="muted">Ollama &nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <span style="color:{"#27e0ae" if ollama_online else "#eebf62"}">{"ONLINE" if ollama_online else "OFFLINE"}</span></div>',
            unsafe_allow_html=True,
        )
        st.caption(f"Model lokal: {settings.ollama_model}")
        st.caption("Mode lokal · data tidak dikirim ke cloud")

    st.markdown(
        f"""
        <div class="topbar">
          <div>
            <div class="topbar-title">{section.split('  ', 1)[-1]}</div>
            <div class="topbar-meta">Workspace analisis lokal &nbsp;·&nbsp; {time_range}</div>
          </div>
          <div>
            <span class="pill"><i class="dot {' ' if db_data else 'off'}"></i> PostgreSQL</span>
            <span class="pill"><i class="dot {' ' if app_online else 'off'}"></i> API</span>
            <span class="pill"><i class="dot {' ' if ollama_online else 'off'}"></i> Ollama</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if db_error:
        st.warning(db_error)

    if db_data is None:
        sources = batches_total = batches_completed = records_loaded = 0
        results_total = results_unreviewed = 0
        batches = pd.DataFrame(
            columns=["batch_id", "source_name", "status", "records_loaded", "records_rejected", "created_at"]
        )
        rules = pd.DataFrame(columns=["rule_code", "rule_name", "rule_version", "enabled"])
        source_list = pd.DataFrame(
            columns=["source_code", "source_name", "source_type", "enabled", "authorized_purpose"]
        )
        audit = pd.DataFrame(columns=["action", "source_code", "outcome", "created_at"])
        results = pd.DataFrame(
            columns=["left_source", "left_record_ref", "right_source", "right_record_ref", "match_method", "review_status", "created_at"]
        )
    else:
        sources = db_data["sources"]
        batches_total = db_data["batches_total"]
        batches_completed = db_data["batches_completed"]
        records_loaded = db_data["records_loaded"]
        results_total = db_data["results_total"]
        results_unreviewed = db_data["results_unreviewed"]
        batches = db_data["batches"]
        source_list = db_data["source_list"]
        rules = db_data["rules"]
        audit = db_data["audit"]
        results = db_data["results"]

    if section.startswith("▤"):
        source_col, import_col = st.columns([1.2, 1], gap="medium")
        with source_col:
            st.subheader("Sumber data terdaftar")
            if source_list.empty:
                st.info("Belum ada sumber data di PostgreSQL.")
            else:
                st.dataframe(
                    source_list.rename(
                        columns={
                            "source_code": "Kode",
                            "source_name": "Nama sumber",
                            "source_type": "Tipe",
                            "enabled": "Aktif",
                            "authorized_purpose": "Tujuan terotorisasi",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            st.subheader("Riwayat batch impor")
            if batches.empty:
                st.info("Belum ada batch impor.")
            else:
                st.dataframe(batches, use_container_width=True, hide_index=True)
        with import_col:
            st.subheader("Input dataset")
            st.file_uploader(
                "Pilih CSV, XLSX, atau JSON",
                type=["csv", "xlsx", "json"],
                disabled=True,
                help="Endpoint import belum tersedia; file belum dapat diproses.",
            )
            st.button("Pilih sumber & impor", disabled=True, use_container_width=True)
            st.caption("Upload dinonaktifkan sampai validasi dan endpoint API tersedia.")
        return

    if section.startswith("⌘"):
        rules_col, audit_col = st.columns(2, gap="medium")
        with rules_col:
            st.subheader("Aturan korelasi")
            if rules.empty:
                st.info("Belum ada aturan korelasi di PostgreSQL.")
            else:
                st.dataframe(rules, use_container_width=True, hide_index=True)
        with audit_col:
            st.subheader("Aktivitas audit terbaru")
            if audit.empty:
                st.info("Belum ada aktivitas audit.")
            else:
                st.dataframe(audit, use_container_width=True, hide_index=True)
        st.caption("Korelasi adalah keterkaitan berbasis aturan; keputusan tetap pada analis.")
        return

    if section.startswith("◉"):
        st.subheader("Status layanan")
        st.dataframe(
            pd.DataFrame(
                [
                    {"Layanan": "PostgreSQL", "Status": "Terhubung" if db_data else "Belum terhubung"},
                    {"Layanan": "FastAPI", "Status": "Online" if app_online else "Offline"},
                    {"Layanan": "Ollama", "Status": "Online" if ollama_online else "Offline"},
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"Model lokal yang dikonfigurasi: {settings.ollama_model}")
        st.subheader("Audit terbaru")
        if audit.empty:
            st.info("Belum ada aktivitas audit di PostgreSQL.")
        else:
            st.dataframe(audit, use_container_width=True, hide_index=True)
        return

    left, right = st.columns([1.62, 1], gap="medium")
    with left:
        metric_cols = st.columns(3, gap="small")
        with metric_cols[0]:
            metric("SUMBER AKTIF", str(sources), "Terdaftar di PostgreSQL", "green")
        with metric_cols[1]:
            metric("BATCH SELESAI", str(batches_completed), f"Dari {batches_total} batch", "blue")
        with metric_cols[2]:
            metric("HASIL KORELASI", str(results_total), f"{results_unreviewed} perlu ditinjau", "amber")

        st.markdown(
            '<div class="panel"><div class="panel-title"><strong>✳ &nbsp;Asisten Intelijen Lokal</strong><span class="muted">Analisis berbasis hasil terverifikasi</span></div></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            """
            <div class="chat-card">
              <div class="chat-role">ASISTEN · PRATINJAU</div>
              <div class="chat-copy">
                Tanyakan ringkasan batch atau hasil korelasi yang tersimpan di PostgreSQL.
                Asisten hanya boleh menjelaskan ringkasan yang sudah diverifikasi, bukan
                menyimpulkan identitas atau sebab-akibat.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.text_input(
            "Pertanyaan",
            placeholder="Contoh: Ringkas hasil korelasi yang perlu ditinjau...",
            disabled=True,
            label_visibility="collapsed",
        )
        st.button("Kirim pertanyaan", type="primary", disabled=True, use_container_width=True)
        st.caption("Chat AI menunggu endpoint FastAPI yang aman; pertanyaan belum dikirim.")

        st.markdown("#### Hasil korelasi terbaru")
        if results.empty:
            st.info("Belum ada hasil korelasi tersimpan di PostgreSQL.")
        else:
            filtered_results = results
            filtered_results = filter_by_time(
                filtered_results, "created_at", time_range
            )
            if review_filter != "Semua status":
                status_map = {
                    "Belum direview": "unreviewed",
                    "Dikonfirmasi": "confirmed",
                    "Ditolak": "rejected",
                }
                filtered_results = results[
                    results["review_status"] == status_map[review_filter]
                ]
            st.dataframe(
                filtered_results.rename(
                    columns={
                        "left_source": "Sumber A",
                        "left_record_ref": "Referensi A",
                        "right_source": "Sumber B",
                        "right_record_ref": "Referensi B",
                        "match_method": "Metode",
                        "review_status": "Review",
                        "created_at": "Waktu",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
        st.caption(
            "Korelasi bukan bukti identitas, kausalitas, atau pelanggaran. "
            f"Total record dimuat: {records_loaded}."
        )

    with right:
        st.markdown("#### Input & Knowledge Base")
        st.caption("Dataset terotorisasi · tersimpan di PostgreSQL")
        st.file_uploader(
            "Pilih CSV, XLSX, atau JSON",
            type=["csv", "xlsx", "json"],
            disabled=True,
            help="Endpoint import belum tersedia; file belum dapat diproses.",
        )
        st.button("Pilih sumber & impor", disabled=True, use_container_width=True)
        st.caption("Impor akan diaktifkan setelah API dan validasi tersedia.")

        st.markdown("#### Batch terbaru")
        if batches.empty:
            st.info("Belum ada batch impor di PostgreSQL.")
        else:
            display_batches = batches.copy()
            display_batches["created_at"] = pd.to_datetime(
                display_batches["created_at"], errors="coerce"
            ).dt.strftime("%Y-%m-%d %H:%M")
            st.dataframe(
                display_batches.rename(
                    columns={
                        "batch_id": "ID batch",
                        "source_name": "Sumber",
                        "status": "Status",
                        "records_loaded": "Dimuat",
                        "records_rejected": "Ditolak",
                        "created_at": "Waktu",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )

        st.markdown("#### Aturan korelasi terverifikasi")
        if rules.empty:
            st.info("Belum ada aturan korelasi terdaftar di PostgreSQL.")
        else:
            for rule in rules.itertuples(index=False):
                status = "AKTIF" if rule.enabled else "NONAKTIF"
                rule_code = escape(str(rule.rule_code))
                rule_name = escape(str(rule.rule_name))
                st.markdown(
                    f"""
                    <div class="rule-card">
                      <div class="panel-title">
                        <span class="rule-code">{rule_code} · v{rule.rule_version}</span>
                        <span class="muted">{status}</span>
                      </div>
                      <div class="rule-name">{rule_name}</div>
                      <div class="rule-note">Aturan terdaftar · keputusan tetap pada analis</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    with st.expander("Status layanan dan konfigurasi"):
        st.write(
            {
                "PostgreSQL": "connected" if db_data else "not connected",
                "FastAPI": "online" if app_online else "offline",
                "Ollama": "online" if ollama_online else "offline",
                "Ollama model": settings.ollama_model,
            }
        )
        if not db_data:
            st.caption("Detail koneksi tidak ditampilkan agar kredensial database tidak bocor.")


if __name__ == "__main__":
    main()
