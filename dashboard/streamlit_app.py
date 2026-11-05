"""Authenticated Streamlit dashboard backed by FastAPI and PostgreSQL."""

from __future__ import annotations

import logging
from html import escape
from typing import Any

import httpx
import pandas as pd
import streamlit as st
from pydantic_settings import BaseSettings, SettingsConfigDict

LOGGER = logging.getLogger(__name__)


class DashboardSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_base_url: str = "http://127.0.0.1:8000"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"


class ApiError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def api_request(
    method: str,
    path: str,
    *,
    data: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
) -> Any:
    credentials = st.session_state.get("api_credentials")
    if credentials is None:
        raise ApiError(401, "Silakan masuk terlebih dahulu.")
    try:
        response = httpx.request(
            method,
            f"{DashboardSettings().app_base_url.rstrip('/')}{path}",
            auth=credentials,
            json=data if files is None else None,
            data=data if files is not None else None,
            files=files,
            timeout=130,
        )
    except httpx.HTTPError as exc:
        LOGGER.error("Dashboard API request failed (%s)", type(exc).__name__)
        raise ApiError(503, "API belum dapat dihubungi.") from exc

    if not response.is_success:
        try:
            body = response.json()
            detail = body.get("detail", "Permintaan tidak berhasil.")
            if isinstance(detail, dict):
                detail = detail.get("error", str(detail))
        except ValueError:
            detail = "Permintaan tidak berhasil."
        raise ApiError(response.status_code, str(detail))
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def service_status(url: str) -> bool:
    try:
        return httpx.get(url, timeout=2).is_success
    except httpx.HTTPError:
        return False


def show_error(error: ApiError) -> None:
    st.error(f"{error.detail} (HTTP {error.status_code})")


def metric(label: str, value: str, note: str, accent: str) -> None:
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


def show_login(settings: DashboardSettings) -> bool:
    intro, login = st.columns([1.05, 0.95], gap="large")
    with intro:
        st.markdown(
            """
            <div class="login-intro">
              <div class="login-mark">✳</div>
              <div class="login-eyebrow">LOCAL AI DATA INTELLIGENCE</div>
              <h1>Analisis yang tetap<br><span>di lingkungan lokal.</span></h1>
              <p>Kelola sumber, tinjau korelasi, dan jelajahi ringkasan
              analisis dalam satu ruang kerja yang terkontrol.</p>
              <div class="login-badges">
                <span>PostgreSQL</span><span>Ollama lokal</span><span>Akses berbasis peran</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with login:
        st.markdown(
            """
            <div class="login-heading">
              <div class="login-eyebrow">SELAMAT DATANG</div>
              <h2>Masuk ke ruang kerja</h2>
              <p>Gunakan akun yang diberikan administrator.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("login_form"):
            username = st.text_input(
                "Nama pengguna", placeholder="Masukkan nama pengguna"
            )
            password = st.text_input(
                "Kata sandi", type="password", placeholder="Masukkan kata sandi"
            )
            submitted = st.form_submit_button(
                "Masuk dengan aman  →", type="primary", use_container_width=True
            )
    if submitted:
        try:
            response = httpx.get(
                f"{settings.app_base_url.rstrip('/')}/auth/me",
                auth=(username, password),
                timeout=5,
            )
            if response.is_success:
                st.session_state["api_credentials"] = (username, password)
                st.session_state["api_user"] = response.json()
                st.rerun()
            elif response.status_code == 401:
                st.error("Nama pengguna atau kata sandi tidak valid.")
            else:
                st.error(f"API mengembalikan HTTP {response.status_code}.")
        except httpx.HTTPError as exc:
            LOGGER.error("Dashboard login check failed (%s)", type(exc).__name__)
            st.error("API belum dapat dihubungi.")
    return False


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
          --bg:#080f1c;--panel:#0e1929;--panel2:#111f31;
          --border:#20334a;--text:#e4edf7;--muted:#8296ad;
          --green:#27e0ae;--blue:#66b9ff;--amber:#eebf62;
        }
        .stApp{background:var(--bg);color:var(--text)}
        [data-testid="stHeader"]{background:rgba(8,15,28,.92)}
        [data-testid="stSidebar"]{background:#0d1727;border-right:1px solid var(--border)}
        .block-container{max-width:1800px;padding:1rem 1.4rem 2rem}
        h1,h2,h3{color:var(--text)!important;letter-spacing:-.02em}
        h1{font-size:1.3rem!important}h2{font-size:1.05rem!important}
        .brand{font-size:1.08rem;line-height:1.05;font-weight:750;color:#f0f7ff}
        .brand span,.green{color:var(--green)}
        .muted,.metric-label,.metric-note{color:var(--muted)!important}
        .topbar,.metric-card,.chat-card,.rule-card{
          background:var(--panel);border:1px solid var(--border);border-radius:10px
        }
        .topbar{display:flex;justify-content:space-between;align-items:center;
          gap:1rem;padding:.7rem 1rem;margin:.1rem 0 1rem}
        .topbar-title{font-weight:700;font-size:.94rem}
        .metric-card{padding:.8rem .85rem;min-height:100px}
        .metric-label,.metric-note{font-size:.72rem}
        .metric-value{font-size:1.5rem;font-weight:750;margin:.2rem 0}
        .metric-value.green{color:var(--green)}.metric-value.blue{color:var(--blue)}
        .metric-value.amber{color:var(--amber)}
        .chat-card,.rule-card{background:var(--panel2);padding:.8rem;margin:.5rem 0}
        .chat-role,.rule-code{color:var(--green);font-size:.72rem;font-weight:700}
        .stButton button,.stFormSubmitButton button{border-radius:7px}
        div[data-testid="stDataFrame"]{border:1px solid var(--border);border-radius:8px}
        .login-intro{padding:clamp(1.5rem,5vw,4rem) 1rem 2rem 0}
        .login-mark{display:grid;place-items:center;width:48px;height:48px;
          margin-bottom:2rem;border:1px solid #285147;border-radius:14px;
          background:#102a29;color:var(--green);font-size:1.55rem}
        .login-eyebrow{color:var(--green);font-size:.72rem;font-weight:750;
          letter-spacing:.14em}
        .login-intro h1{margin:.8rem 0 1rem;font-size:clamp(2rem,4vw,3.35rem)!important;
          line-height:1.08;letter-spacing:-.045em}
        .login-intro h1 span{color:var(--green)}
        .login-intro p,.login-heading p{max-width:34rem;color:var(--muted);
          line-height:1.7;font-size:.95rem}
        .login-badges{display:flex;flex-wrap:wrap;gap:.55rem;margin-top:1.5rem}
        .login-badges span{padding:.45rem .7rem;border:1px solid var(--border);
          border-radius:999px;background:#0d1827;color:#b8c8d9;font-size:.72rem}
        .login-heading{padding:1rem 0 .4rem}
        .login-heading h2{margin:.45rem 0;font-size:1.65rem!important}
        div[data-testid="stForm"]{padding:1.35rem;border:1px solid var(--border);
          border-radius:16px;background:linear-gradient(145deg,#101d2e,#0c1625);
          box-shadow:0 24px 70px rgba(0,0,0,.24)}
        div[data-testid="stForm"] label{font-size:.84rem;font-weight:600}
        div[data-testid="stForm"] input{min-height:2.9rem;border-radius:9px}
        div[data-testid="stForm"] button{min-height:2.9rem;border-radius:9px;
          font-weight:700}
        @media(max-width:800px){
          .block-container{padding:1rem}
          .login-intro{padding:1rem 0 .5rem}
          .login-mark{margin-bottom:1.1rem}
          .login-intro h1{font-size:2rem!important}
          div[data-testid="stForm"]{padding:1rem}
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if "api_credentials" not in st.session_state:
        show_login(settings)
        return

    try:
        user = api_request("GET", "/auth/me")
    except ApiError:
        st.session_state.pop("api_credentials", None)
        st.session_state.pop("api_user", None)
        show_login(settings)
        return
    st.session_state["api_user"] = user

    health_api = service_status(f"{settings.app_base_url.rstrip('/')}/health")
    health_db = service_status(f"{settings.app_base_url.rstrip('/')}/health/db")
    health_ollama = service_status(f"{settings.app_base_url.rstrip('/')}/health/ollama")

    with st.sidebar:
        st.markdown(
            '<div class="brand"><span>✳</span> Local<br>Intelligence</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"{user['username']} · {user['role']}")
        if st.button("Keluar", use_container_width=True):
            st.session_state.pop("api_credentials", None)
            st.session_state.pop("api_user", None)
            st.rerun()
        st.markdown("---")
        navigation = [
            "✳  AI Chat & Analisis",
            "▤  Input & Knowledge Base",
            "⌘  Aturan & Audit",
            "◉  Audit & Status Sistem",
        ]
        if user["role"] in ("admin", "analyst"):
            navigation.insert(1, "⌕  Dokumen & Pencarian")
        section = st.radio(
            "NAVIGASI",
            navigation,
            label_visibility="visible",
        )
        st.markdown("---")
        st.markdown("**STATUS NODE**")
        st.caption(f"PostgreSQL: {'TERHUBUNG' if health_db else 'OFFLINE'}")
        st.caption(f"FastAPI: {'ONLINE' if health_api else 'OFFLINE'}")
        st.caption(f"Ollama: {'ONLINE' if health_ollama else 'OFFLINE'}")
        st.caption(f"Model: {settings.ollama_model}")

    try:
        summary = api_request("GET", "/dashboard/summary")
        sources = api_request("GET", "/sources")
        batches = api_request("GET", "/imports?limit=50")
        results = api_request("GET", "/analysis/results?limit=100")
        rules = api_request("GET", "/analysis/rules")
    except ApiError as exc:
        show_error(exc)
        st.stop()

    st.markdown(
        f"""
        <div class="topbar">
          <div><div class="topbar-title">{escape(section.split('  ',1)[-1])}</div>
          <div class="muted">Data dan ringkasan diambil melalui API dengan otorisasi</div></div>
          <div class="muted">PostgreSQL · FastAPI · Ollama lokal</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    metric_cols = st.columns(3)
    with metric_cols[0]:
        metric("SUMBER AKTIF", str(summary["sources"]), "Sumber terotorisasi", "green")
    with metric_cols[1]:
        metric(
            "BATCH SELESAI",
            str(summary["batches_completed"]),
            f"Dari {summary['batches_total']} batch",
            "blue",
        )
    with metric_cols[2]:
        metric(
            "HASIL KORELASI",
            str(summary["results_total"]),
            f"{summary['results_unreviewed']} belum direview",
            "amber",
        )

    if section.startswith("✳"):
        left, right = st.columns([1.5, 1])
        with left:
            st.subheader("Asisten Intelijen Lokal")
            st.warning(
                "AI hanya menjelaskan ringkasan agregat terverifikasi. "
                "Jangan masukkan data pribadi; hasil harus divalidasi analis."
            )
            with st.form("chat_form", clear_on_submit=True):
                question = st.text_area(
                    "Pertanyaan",
                    placeholder="Contoh: Ringkas jumlah batch dan korelasi yang belum ditinjau.",
                    max_chars=2000,
                )
                submitted = st.form_submit_button(
                    "Kirim pertanyaan", type="primary", disabled=not health_ollama
                )
            if submitted and question.strip():
                try:
                    answer = api_request(
                        "POST", "/chat", data={"question": question.strip()}
                    )
                    st.markdown(
                        f'<div class="chat-card"><div class="chat-role">ASISTEN · {escape(answer["model"])}</div>'
                        f'<div>{escape(answer["answer"])}</div><br><span class="muted">{escape(answer["limitations"])}</span></div>',
                        unsafe_allow_html=True,
                    )
                except ApiError as exc:
                    show_error(exc)

            st.subheader("Hasil korelasi")
            if results:
                table = pd.DataFrame(results)
                table = table[
                    [
                        "result_id",
                        "left_source",
                        "left_record_ref",
                        "right_source",
                        "right_record_ref",
                        "review_status",
                        "created_at",
                    ]
                ].rename(
                    columns={
                        "result_id": "ID hasil",
                        "left_source": "Sumber A",
                        "left_record_ref": "Referensi A",
                        "right_source": "Sumber B",
                        "right_record_ref": "Referensi B",
                        "review_status": "Status review",
                        "created_at": "Dibuat",
                    }
                )
                st.dataframe(table, use_container_width=True, hide_index=True)
            else:
                st.info("Belum ada hasil korelasi. Jalankan aturan setelah mengimpor data.")
        with right:
            st.subheader("Jalankan korelasi")
            enabled_rules = [rule for rule in rules if rule["enabled"]]
            if not enabled_rules:
                st.info("Tidak ada aturan korelasi aktif.")
            elif user["role"] in ("admin", "analyst"):
                rule_by_name = {
                    f"{rule['rule_code']} · {rule['rule_name']}": rule
                    for rule in enabled_rules
                }
                selected = st.selectbox("Aturan terverifikasi", list(rule_by_name))
                time_window = st.number_input(
                    "Jendela waktu (detik)", min_value=0, max_value=86400, value=300
                )
                if st.button("Jalankan analisis", type="primary"):
                    try:
                        result = api_request(
                            "POST",
                            "/analysis/correlate",
                            data={
                                "rule_code": rule_by_name[selected]["rule_code"],
                                "time_window_seconds": int(time_window),
                            },
                        )
                        st.success(
                            f"Analisis selesai: {result['results_created']} korelasi baru."
                        )
                        st.rerun()
                    except ApiError as exc:
                        show_error(exc)
            st.caption(
                "Pencocokan deterministik menggunakan referensi bersama yang "
                "diotorisasi dan batas waktu; bukan bukti identitas atau kausalitas."
            )

            reviewable = [item for item in results if item["review_status"] == "unreviewed"]
            if reviewable and user["role"] in ("admin", "analyst"):
                st.subheader("Review hasil")
                options = {item["result_id"]: item for item in reviewable}
                selected_id = st.selectbox(
                    "Hasil belum direview", list(options), format_func=lambda key: (
                        f"{options[key]['left_record_ref']} ↔ {options[key]['right_record_ref']}"
                    )
                )
                decision = st.selectbox("Keputusan analis", ["confirmed", "rejected"])
                if st.button("Simpan review"):
                    try:
                        api_request(
                            "POST",
                            f"/analysis/results/{selected_id}/review",
                            data={"review_status": decision},
                        )
                        st.success("Review tersimpan dan tercatat di audit.")
                        st.rerun()
                    except ApiError as exc:
                        show_error(exc)

    elif section.startswith("⌕"):
        st.subheader("Basis pengetahuan dokumen lokal")
        st.warning(
            "Dokumen dan pencarian berisi data sensitif disimpan di PostgreSQL server lokal. "
            "Hanya admin/analyst yang dapat mengunggah dan mencari; gunakan hanya data "
            "yang Anda berwenang proses."
        )
        upload_col, search_col = st.columns([1, 1.15], gap="large")
        with upload_col:
            st.markdown("#### Tambahkan dokumen")
            if user["role"] not in ("admin", "analyst"):
                st.info("Peran viewer tidak dapat mengunggah atau mencari dokumen.")
            else:
                document = st.file_uploader(
                    "PDF, teks, Office, gambar, dan format dokumen umum",
                    type=[
                        "pdf", "txt", "md", "csv", "doc", "docx", "docm",
                        "xls", "xlsx", "xlsm", "ppt", "pptx", "odt", "rtf",
                        "html", "htm", "png", "jpg", "jpeg", "tif", "tiff", "bmp",
                    ],
                    help=(
                        "PDF hasil pindai diproses dengan OCR Indonesia/Inggris. "
                        "Batas upload mengikuti MAX_UPLOAD_MB."
                    ),
                    key="document_upload",
                )
                if document and st.button("Ekstrak & indeks dokumen", type="primary"):
                    try:
                        result = api_request(
                            "POST",
                            "/documents",
                            files={
                                "file": (
                                    document.name,
                                    document.getvalue(),
                                    document.type or "application/octet-stream",
                                )
                            },
                        )
                        if result["status"] == "already_indexed":
                            st.info("Dokumen yang sama sudah pernah diindeks.")
                        else:
                            st.success(
                                f"Dokumen diindeks: {result['chunks']} bagian, "
                                f"{result['characters']:,} karakter."
                            )
                        if result["ocr_pages"]:
                            st.caption(
                                f"OCR digunakan pada {result['ocr_pages']} halaman pindai."
                            )
                        st.rerun()
                    except ApiError as exc:
                        show_error(exc)

            st.markdown("#### Dokumen terindeks")
            try:
                documents = api_request("GET", "/documents")
                if documents:
                    st.dataframe(
                        pd.DataFrame(documents)[
                            ["file_name", "file_type", "page_count", "chunk_count", "created_at"]
                        ].rename(
                            columns={
                                "file_name": "Nama file",
                                "file_type": "Format",
                                "page_count": "Halaman",
                                "chunk_count": "Bagian indeks",
                                "created_at": "Diunggah",
                            }
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("Belum ada dokumen. Unggah dokumen untuk mulai mencari.")
            except ApiError as exc:
                show_error(exc)

        with search_col:
            st.markdown("#### Cari dan analisis")
            with st.form("document_search_form"):
                search_query = st.text_input(
                    "NIK atau nama / pertanyaan",
                    max_chars=256,
                    placeholder="Masukkan NIK lengkap atau nama yang ingin dicari",
                )
                ask_ai = st.checkbox(
                    "Buat analisis AI lokal berdasarkan kutipan", value=True
                )
                search_submitted = st.form_submit_button(
                    "Cari di dokumen lokal", type="primary", disabled=not health_ollama and ask_ai
                )
            if search_submitted and search_query.strip():
                try:
                    result = api_request(
                        "POST",
                        "/documents/search",
                        data={"query": search_query.strip(), "ask_ai": ask_ai},
                    )
                    st.session_state["document_search_result"] = result
                except ApiError as exc:
                    show_error(exc)

            result = st.session_state.get("document_search_result")
            if result:
                if result["answer"]:
                    st.markdown("**Analisis AI lokal**")
                    st.markdown(result["answer"])
                    st.caption(result["notice"])
                st.markdown(f"**{result['result_count']} kutipan ditemukan**")
                for index, match in enumerate(result["matches"], start=1):
                    page = (
                        f" · halaman {match['page_number']}"
                        if match["page_number"]
                        else ""
                    )
                    with st.expander(
                        f"[{index}] {match['file_name']}{page} · bagian {match['chunk_index'] + 1}"
                    ):
                        st.text(match["excerpt"])
            if result and not result["matches"]:
                st.info("Tidak ditemukan kecocokan dalam dokumen yang terindeks.")

    elif section.startswith("▤"):
        source_col, import_col = st.columns([1.15, 1])
        with source_col:
            st.subheader("Sumber data")
            if sources:
                st.dataframe(
                    pd.DataFrame(sources)[
                        ["source_code", "source_name", "source_type", "enabled", "authorized_purpose"]
                    ].rename(
                        columns={
                            "source_code": "Kode",
                            "source_name": "Nama",
                            "source_type": "Tipe",
                            "enabled": "Aktif",
                            "authorized_purpose": "Tujuan",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            st.subheader("Riwayat batch impor")
            if batches:
                st.dataframe(
                    pd.DataFrame(batches)[
                        ["batch_id", "source_code", "file_name", "status", "records_read",
                         "records_loaded", "records_rejected", "created_at"]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("Belum ada batch impor.")
            if user["role"] == "admin":
                with st.expander("Daftarkan sumber data"):
                    with st.form("source_form"):
                        source_code = st.text_input("Kode sumber")
                        source_name = st.text_input("Nama sumber")
                        source_type = st.selectbox(
                            "Tipe sumber",
                            ["marketplace", "system_log", "population", "other"],
                        )
                        purpose = st.text_input("Tujuan terotorisasi")
                        create = st.form_submit_button("Simpan sumber")
                    if create:
                        try:
                            api_request(
                                "POST",
                                "/sources",
                                data={
                                    "source_code": source_code,
                                    "source_name": source_name,
                                    "source_type": source_type,
                                    "authorized_purpose": purpose,
                                },
                            )
                            st.success("Sumber tersimpan.")
                            st.rerun()
                        except ApiError as exc:
                            show_error(exc)

        with import_col:
            st.subheader("Impor dataset")
            if user["role"] not in ("admin", "analyst"):
                st.info("Peran viewer hanya dapat membaca data.")
            elif not any(source["enabled"] for source in sources):
                st.warning("Tidak ada sumber aktif untuk impor.")
            else:
                source_options = {
                    f"{source['source_name']} ({source['source_code']})": source["source_code"]
                    for source in sources
                    if source["enabled"] and source["source_type"] in (
                        "population", "marketplace", "system_log"
                    )
                }
                if source_options:
                    selected_source = st.selectbox(
                        "Sumber terotorisasi", list(source_options)
                    )
                    upload = st.file_uploader(
                        "CSV, XLSX, JSON, atau JSON Lines (.log)",
                        type=["csv", "xlsx", "json", "log"],
                        help="Batas ukuran mengikuti MAX_UPLOAD_MB.",
                    )
                    if upload and st.button("Validasi & impor", type="primary"):
                        try:
                            result = api_request(
                                "POST",
                                "/imports",
                                data={"source_code": source_options[selected_source]},
                                files={
                                    "file": (
                                        upload.name,
                                        upload.getvalue(),
                                        upload.type or "application/octet-stream",
                                    )
                                },
                            )
                            st.success(
                                f"Batch {result['batch_id']}: "
                                f"{result['records_loaded']} dimuat, "
                                f"{result['records_rejected']} ditolak."
                            )
                            if result["rejection_summary"]:
                                st.warning(f"Ringkasan penolakan: {result['rejection_summary']}")
                            st.rerun()
                        except ApiError as exc:
                            show_error(exc)
                else:
                    st.info("Daftarkan sumber bertipe population, marketplace, atau system_log.")
            st.markdown("**Format awal**")
            st.caption(
                "Marketplace wajib: transaction_ref, event_time, authorized_join_ref. "
                "System log: event_time, event_ref, authorized_join_ref. "
                "Population: record_ref. Timestamp tanpa zona dianggap UTC."
            )

    elif section.startswith("⌘"):
        rule_col, review_col = st.columns(2)
        with rule_col:
            st.subheader("Aturan korelasi")
            if rules:
                st.dataframe(
                    pd.DataFrame(rules)[
                        ["rule_code", "rule_name", "rule_version", "enabled", "rule_definition"]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("Belum ada aturan.")
        with review_col:
            st.subheader("Review terbaru")
            if results:
                st.dataframe(
                    pd.DataFrame(results)[
                        ["result_id", "rule_code", "left_record_ref",
                         "right_record_ref", "review_status", "created_at"]
                    ],
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("Belum ada hasil review.")
        st.caption(
            "Status confirmed/rejected adalah keputusan analis, bukan bukti identitas "
            "atau wrongdoing."
        )

    else:
        st.subheader("Status layanan")
        st.dataframe(
            pd.DataFrame(
                [
                    {"Layanan": "PostgreSQL", "Status": "Terhubung" if health_db else "Offline"},
                    {"Layanan": "FastAPI", "Status": "Online" if health_api else "Offline"},
                    {"Layanan": "Ollama", "Status": "Online" if health_ollama else "Offline"},
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.subheader("Audit keamanan dan analisis")
        if user["role"] != "admin":
            st.info("Riwayat audit hanya dapat dilihat administrator.")
        else:
            try:
                audit = api_request("GET", "/audit?limit=100")
                st.dataframe(
                    pd.DataFrame(audit) if audit else pd.DataFrame(),
                    use_container_width=True,
                    hide_index=True,
                )
            except ApiError as exc:
                show_error(exc)


if __name__ == "__main__":
    main()
