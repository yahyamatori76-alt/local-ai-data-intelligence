# Software Requirements Specification (SRS)

## Local AI Data Intelligence Platform (Local MVP)

-   **Document version:** 1.0
-   **Status:** Baseline for implementation with Codex
-   **Deployment target:** Personal Windows PC or Linux workstation
-   **Data volume:** Under 10 GB for the initial MVP
-   **Primary objective:** Local, auditable correlation and analysis
    across authorized datasets
-   **Initial data categories:** Population/demographic data
    (Dukcapil-type schema), marketplace transaction data (Tokopedia-type
    schema), and system logs

------------------------------------------------------------------------

## 1. Purpose

This document defines the functional requirements, architecture,
database schema, implementation sequence, security requirements, and
acceptance criteria for a local-first AI Data Intelligence Platform.

The system imports structured files, validates and normalizes data,
stores approved records in PostgreSQL, performs deterministic
cross-source correlation, and uses a locally hosted language model to
explain verified analytical results in Indonesian.

This document is intended to be used as the implementation specification
for Codex. Codex should implement the application incrementally,
preserve the requirements in this document, and run tests after each
milestone.

## 2. Goals

1.  Run data processing and LLM inference locally after required
    software and model files have been downloaded.
2.  Import CSV, XLSX, JSON, and supported system log files.
3.  Track import batches, validation results, rejected rows, and data
    lineage.
4.  Correlate records using approved, explicit identifiers and
    documented rules.
5.  Present analytical results through a local dashboard.
6.  Allow users to ask questions in Indonesian about verified analysis
    results.
7.  Prevent the LLM from directly executing arbitrary SQL or
    independently asserting identity matches.
8.  Keep a traceable record of important user actions and analysis
    operations.

## 3. Out of Scope for the MVP

The following are explicitly excluded unless approved in a later
specification revision:

-   Kafka or other streaming infrastructure.
-   Kubernetes and multi-node deployment.
-   Distributed data lake architecture.
-   Multi-agent orchestration.
-   Automatic matching of real people across data sources.
-   Unapproved scraping or access to private Dukcapil or marketplace
    systems.
-   Cloud LLM APIs.
-   Automated enforcement actions based solely on AI output.
-   Production ingestion of personal data before access authorization,
    purpose limitation, and security review are confirmed.

## 4. Assumptions and Constraints

-   Initial deployment is a single PC or workstation.
-   Total initial data volume is below 10 GB.
-   Development and acceptance tests use synthetic or properly
    de-identified data.
-   Data from external organizations must be obtained and processed
    lawfully, with appropriate authorization and a defined purpose.
-   The system is local-first, but local deployment alone does not
    guarantee security.
-   Network services must bind to localhost by default.
-   The implementation should favor simple components and avoid
    unnecessary infrastructure.

## 5. Recommended Technology Stack

  -----------------------------------------------------------------------
  Component               Technology              Purpose
  ----------------------- ----------------------- -----------------------
  Operating system        Windows 11 with Docker  Local host
                          Desktop/WSL2, or Linux

  Language                Python 3.12             Application and data
                                                  processing

  API                     FastAPI + Uvicorn       Backend API

  Validation              Pydantic                Request and
                                                  configuration
                                                  validation

  Data processing         Pandas                  File parsing,
                                                  normalization,
                                                  correlation

  Database                PostgreSQL 17           Structured storage,
                                                  metadata, results

  Database access         SQLAlchemy + Psycopg    Database access

  Migrations              Alembic or versioned    Schema changes
                          SQL migrations

  Local LLM runtime       Ollama                  Local model inference

  Initial model           Small instruct model    Natural-language
                          supported by Ollama,    explanation
                          e.g. `llama3.2:3b` if
                          suitable for hardware

  Dashboard               Streamlit + Plotly      Local analyst interface

  Containerization        Docker Compose          PostgreSQL deployment

  Testing                 Pytest                  Unit and integration
                                                  tests

  HTTP client             HTTPX                   Backend-to-Ollama
                                                  communication
  -----------------------------------------------------------------------

Do not add ClickHouse, Kafka, a vector database, or Kubernetes during
the initial MVP unless a documented requirement demonstrates a need.

## 6. Hardware Guidance

Recommended development baseline:

-   CPU: 6--8 cores preferred; 4 cores minimum for a basic prototype.
-   RAM: 32 GB preferred; 16 GB can work with a small model and
    constrained workloads.
-   Storage: SSD/NVMe with at least 50 GB free for application,
    database, and model files.
-   GPU: Optional. If available, VRAM of 8--12 GB or more may improve
    inference speed depending on model and quantization.
-   Internet: Required for downloading installers, Python packages,
    Docker images, and the model. Routine local inference can work
    offline afterward.

These are planning guidelines, not guaranteed performance
specifications. Model size, quantization, context length, and concurrent
use affect actual resource requirements.

## 7. High-Level Architecture

``` text
CSV / XLSX / JSON / System Logs
              |
              v
      Streamlit Dashboard
              |
              v
         FastAPI Backend
              |
       +------+-------+
       |              |
       v              v
Data Ingestion   Analysis Service
       |              |
       v              v
  PostgreSQL <--- Correlation Engine
       |
       v
Verified, minimized analysis results
       |
       v
     Ollama / Local LLM
       |
       v
Indonesian explanation with limitations
       |
       v
Streamlit Dashboard
```

### 7.1 Architectural Rules

-   Deterministic SQL/Python logic performs calculations and matching.
-   The LLM explains verified results; it is not the source of truth.
-   The LLM must not receive full sensitive tables when aggregate
    results are sufficient.
-   The LLM must not execute arbitrary SQL.
-   Correlation results must record the rule and source references used.
-   The application must not infer that two records represent the same
    person merely because names, locations, amounts, or timestamps are
    similar.

## 8. Functional Requirements

### FR-001: Source Registry

The system shall maintain a registry of authorized data sources,
including source code, display name, type, purpose, and enabled status.

**Acceptance criteria** - A source can be created and listed by an
authorized administrator. - Disabled sources cannot be used for new
imports. - Every import batch references a registered source.

### FR-002: File Import

The system shall support CSV, XLSX, and JSON imports. A system-log
parser shall support a documented initial format.

**Acceptance criteria** - Unsupported extensions are rejected. - Upload
size limits are enforced. - Import attempts create a batch record. -
Success, failure, and rejection counts are recorded. - A failed import
produces a useful error message without exposing secrets.

### FR-003: Validation and Normalization

The system shall normalize column names and validate required columns
and field types.

**Acceptance criteria** - Missing required columns are reported. -
Invalid timestamps are handled according to the selected import
policy. - Duplicate records can be detected. - The original file is not
silently modified. - Rejected rows are counted and, where safe,
associated with a non-sensitive error reason.

### FR-004: Data Storage

The system shall store normalized records and metadata in PostgreSQL.

**Acceptance criteria** - All stored records reference an import
batch. - Foreign-key constraints are enforced. - Indexes exist for
common time and join-reference queries. - Re-import behavior is
deterministic and documented.

### FR-005: Correlation Engine

The system shall correlate records using explicit, authorized join
references and configurable time windows.

**Acceptance criteria** - Matching rules are deterministic and
versioned. - Correlations outside configured time windows are
excluded. - Every result records the rule, source references, matching
method, and evidence summary. - Similarity alone must not be treated as
proof of identity. - The engine is tested with positive, negative, and
boundary cases.

### FR-006: Results and Provenance

The system shall retain the provenance of each correlation result.

**Acceptance criteria** - An analyst can identify the source batches and
record references that produced a result. - Results can be marked
unreviewed, confirmed, or rejected by an authorized user. - A confidence
value, if used, is documented and not presented as a probability unless
calibrated.

### FR-007: Local AI Chat

The system shall send prompts to a locally hosted Ollama instance.

**Acceptance criteria** - The backend can check whether Ollama is
reachable. - The selected model is configurable. - The API reports a
controlled error when Ollama is unavailable. - The LLM is instructed not
to invent findings or claim it queried data that was not supplied. -
Chat responses based on data must use verified result summaries supplied
by the backend.

### FR-008: Dashboard

The dashboard shall display system status, import batches, validation
summaries, correlation results, and a local AI chat interface.

**Acceptance criteria** - The dashboard displays useful errors if the
backend is unavailable. - Users can view and filter permitted results. -
Sensitive values are masked or omitted by default. - Export functions,
if implemented, enforce user permissions and are audited.

### FR-009: Authentication and Authorization

The application shall support local authentication and role-based access
control.

Initial roles: - `admin`: manage sources, users, configuration, and
imports. - `analyst`: import authorized data and run approved
analyses. - `viewer`: read permitted dashboards and results.

**Acceptance criteria** - Passwords are stored as secure password
hashes, never plaintext. - Disabled users cannot authenticate. - API
endpoints enforce authorization on the server. - Database credentials
use least privilege. - No public registration is enabled by default.

### FR-010: Audit Trail

The system shall record important security and analytical actions.

**Acceptance criteria** - Import, correlation, review, export, login
failure, and administrative changes can be audited. - Audit logs avoid
raw personal data, passwords, access tokens, and full sensitive
prompts. - Audit records include timestamp, actor when known, action,
outcome, and a request/correlation identifier.

### FR-011: Backup and Recovery

The system shall document a local backup and restore process.

**Acceptance criteria** - PostgreSQL backup can be generated. - Restore
is tested in a separate or clean environment. - Backup files are not
committed to source control. - Recovery steps are documented.

## 9. Non-Functional Requirements

-   **NFR-001 Local-first:** Processing and inference run locally after
    setup.
-   **NFR-002 Privacy:** Use synthetic/de-identified test data during
    development.
-   **NFR-003 Security:** Bind services to localhost by default and do
    not expose database or Ollama ports publicly.
-   **NFR-004 Reliability:** Errors are handled without exposing secrets
    or stack traces to end users.
-   **NFR-005 Maintainability:** Code is separated into ingestion,
    analytics, AI, API, security, and dashboard modules.
-   **NFR-006 Testability:** Core validation and correlation logic has
    automated tests.
-   **NFR-007 Traceability:** Analysis results can be traced to source
    batches and rule versions.
-   **NFR-008 Resource awareness:** The system can operate on a single
    workstation with under 10 GB of input data.
-   **NFR-009 Safe AI:** LLM output is treated as untrusted text and
    never automatically triggers privileged operations.
-   **NFR-010 Configuration:** Secrets and environment-specific settings
    are provided through environment variables, not hard-coded in source
    files.

## 10. Database Schema

Use PostgreSQL database `local_ai_intel`.

Create a versioned migration at `migrations/001_initial_schema.sql`.

``` sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE app_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'analyst'
        CHECK (role IN ('admin', 'analyst', 'viewer')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE source_registry (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_code VARCHAR(50) NOT NULL UNIQUE,
    source_name VARCHAR(150) NOT NULL,
    source_type VARCHAR(30) NOT NULL
        CHECK (source_type IN (
            'population', 'marketplace', 'system_log', 'other'
        )),
    description TEXT,
    authorized_purpose TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE import_batches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES source_registry(id),
    file_name VARCHAR(255),
    file_sha256 CHAR(64),
    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    records_read INTEGER NOT NULL DEFAULT 0,
    records_loaded INTEGER NOT NULL DEFAULT 0,
    records_rejected INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT,
    imported_by UUID REFERENCES app_users(id),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE dukcapil_records (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES import_batches(id),
    record_ref VARCHAR(128) NOT NULL,
    masked_identity_ref VARCHAR(128),
    region_code VARCHAR(30),
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    record_hash CHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (batch_id, record_ref)
);

CREATE TABLE marketplace_transactions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES import_batches(id),
    transaction_ref VARCHAR(128) NOT NULL,
    event_time TIMESTAMPTZ,
    status VARCHAR(40),
    amount NUMERIC(18,2),
    currency CHAR(3) DEFAULT 'IDR',
    authorized_join_ref VARCHAR(128),
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (batch_id, transaction_ref)
);

CREATE TABLE system_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    batch_id UUID NOT NULL REFERENCES import_batches(id),
    event_time TIMESTAMPTZ,
    severity VARCHAR(20),
    event_type VARCHAR(100),
    event_ref VARCHAR(128),
    authorized_join_ref VARCHAR(128),
    message TEXT,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE correlation_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_code VARCHAR(100) NOT NULL UNIQUE,
    rule_name VARCHAR(200) NOT NULL,
    rule_version INTEGER NOT NULL DEFAULT 1,
    rule_definition JSONB NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE correlation_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rule_id UUID NOT NULL REFERENCES correlation_rules(id),
    batch_id UUID REFERENCES import_batches(id),
    left_source VARCHAR(50) NOT NULL,
    left_record_ref VARCHAR(128) NOT NULL,
    right_source VARCHAR(50) NOT NULL,
    right_record_ref VARCHAR(128) NOT NULL,
    match_method VARCHAR(50) NOT NULL,
    confidence NUMERIC(5,4),
    evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    review_status VARCHAR(20) NOT NULL DEFAULT 'unreviewed'
        CHECK (review_status IN ('unreviewed', 'confirmed', 'rejected')),
    reviewed_by UUID REFERENCES app_users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE analysis_audit (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id UUID REFERENCES app_users(id),
    action VARCHAR(100) NOT NULL,
    source_code VARCHAR(50),
    request_id UUID,
    parameters_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    outcome VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_dukapil_batch
    ON dukcapil_records(batch_id);
CREATE INDEX idx_marketplace_event_time
    ON marketplace_transactions(event_time);
CREATE INDEX idx_marketplace_join_ref
    ON marketplace_transactions(authorized_join_ref);
CREATE INDEX idx_system_events_time
    ON system_events(event_time);
CREATE INDEX idx_system_events_join_ref
    ON system_events(authorized_join_ref);
CREATE INDEX idx_correlation_created_at
    ON correlation_results(created_at);
CREATE INDEX idx_correlation_review
    ON correlation_results(review_status);
```

### 10.1 Database Design Notes

-   `attributes` stores approved additional fields in JSONB.
-   `record_ref` is an internal reference, not a raw personal
    identifier.
-   `authorized_join_ref` must only contain a join key approved for the
    stated purpose.
-   Raw personal identifiers must not be copied into prompts, audit
    logs, or example datasets.
-   `confidence` is a method score unless a statistically calibrated
    probability has been implemented and documented.
-   Review status is an analyst workflow, not proof of identity or
    wrongdoing.

## 11. Repository Structure

Create this repository structure:

``` text
local-ai-data-intelligence/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── routes_health.py
│   │   ├── routes_import.py
│   │   ├── routes_analysis.py
│   │   └── routes_chat.py
│   ├── ingestion/
│   │   ├── importer.py
│   │   ├── log_parser.py
│   │   └── validation.py
│   ├── analytics/
│   │   ├── normalization.py
│   │   ├── correlation.py
│   │   └── quality_checks.py
│   ├── ai/
│   │   ├── ollama_client.py
│   │   └── analysis_planner.py
│   ├── db/
│   │   ├── connection.py
│   │   └── repositories.py
│   └── security/
│       ├── access_control.py
│       └── audit.py
├── dashboard/
│   └── streamlit_app.py
├── migrations/
│   └── 001_initial_schema.sql
├── tests/
│   ├── test_importer.py
│   ├── test_validation.py
│   ├── test_correlation.py
│   └── test_api.py
├── data/
│   └── synthetic/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── requirements.txt
├── README.md
└── SRS.md
```

## 12. Installation and Development Environment

Primary development target: Windows 11 with PowerShell, Docker Desktop,
and Ollama running on the host. Linux is also supported, but
installation commands may differ.

### 12.1 Install Python

Install Python 3.12 from the official Python downloads page.

Verify:

``` powershell
py -3.12 --version
py -3.12 -m pip --version
```

Create a virtual environment:

``` powershell
mkdir C:\local-ai-data-intelligence
cd C:\local-ai-data-intelligence
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If PowerShell activation is blocked, use Command Prompt:

``` bat
.venv\Scripts\activate.bat
```

### 12.2 Install Git

Install Git from the official Git website.

Verify:

``` powershell
git --version
git init
```

### 12.3 Install Docker Desktop

Install Docker Desktop for Windows and enable its recommended WSL2
backend for Linux containers.

Verify:

``` powershell
wsl --version
docker --version
docker compose version
docker run --rm hello-world
```

### 12.4 Install Ollama

Install Ollama from the official download page.

Verify and download a suitable local model:

``` powershell
ollama --version
ollama pull llama3.2:3b
ollama list
ollama run llama3.2:3b
```

The example model is a starting point only. Confirm its availability,
language quality, memory requirements, and license before selecting it
for a specific use.

### 12.5 Python Dependencies

Create `requirements.txt`:

``` text
fastapi
uvicorn[standard]
pydantic
pydantic-settings
psycopg[binary]
sqlalchemy
alembic
pandas
openpyxl
python-multipart
httpx
streamlit
plotly
requests
bcrypt
pytest
```

Install:

``` powershell
python -m pip install -r requirements.txt
```

Use pinned dependency versions before creating a release or production
deployment.

## 13. Environment Configuration

Create `.env.example`:

``` dotenv
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000

POSTGRES_DB=local_ai_intel
POSTGRES_USER=app_user
POSTGRES_PASSWORD=REPLACE_WITH_STRONG_PASSWORD
DATABASE_URL=postgresql+psycopg://app_user:REPLACE_WITH_STRONG_PASSWORD@localhost:5432/local_ai_intel

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b

UPLOAD_DIR=./data
MAX_UPLOAD_MB=100
```

Copy `.env.example` to `.env` and replace placeholder secrets. Do not
commit `.env` or real datasets to version control.

If the backend is later containerized, use the appropriate host address
for reaching Ollama from inside Docker. Do not expose Ollama to the
local network unnecessarily.

## 14. Docker Compose

Initial Compose setup should run PostgreSQL only. Ollama runs on the
host, while FastAPI and Streamlit can initially run in the Python
virtual environment for easier debugging.

Create `docker-compose.yml`:

``` yaml
services:
  postgres:
    image: postgres:17
    container_name: local-ai-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: local_ai_intel
      POSTGRES_USER: app_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app_user -d local_ai_intel"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
```

Run:

``` powershell
docker compose up -d
docker compose ps
docker compose logs postgres
```

Apply migrations explicitly. Do not assume that editing a SQL file
automatically updates an existing database.

## 15. Backend API Requirements

Implement these endpoints:

  ----------------------------------------------------------------------------------------
  Method                  Endpoint                                 Purpose
  ----------------------- ---------------------------------------- -----------------------
  GET                     `/health`                                Application health

  GET                     `/health/db`                             Database connectivity

  GET                     `/health/ollama`                         Ollama connectivity

  GET                     `/sources`                               List permitted data
                                                                   sources

  POST                    `/imports`                               Import an authorized
                                                                   dataset

  GET                     `/imports`                               List import batches

  GET                     `/imports/{batch_id}`                    Import details and
                                                                   validation counts

  POST                    `/analysis/correlate`                    Run a named, approved
                                                                   correlation rule

  GET                     `/analysis/results`                      List permitted results

  POST                    `/analysis/results/{result_id}/review`   Review a result

  POST                    `/chat`                                  Ask the local AI about
                                                                   permitted information
  ----------------------------------------------------------------------------------------

All endpoints except a deliberately limited local health check must
enforce appropriate authentication and authorization before operational
use.

## 16. Initial Correlation Rule

Implement the first rule as a deterministic transaction-to-system-event
correlation:

-   Join only on an explicitly approved shared reference.
-   Normalize timestamps to UTC for comparison.
-   Use a configurable time window, initially 300 seconds.
-   Preserve transaction and event record references.
-   Store rule code and version.
-   Return no match if the reference is missing or the time difference
    exceeds the allowed window.
-   Do not interpret correlation as causation or wrongdoing.

Create synthetic test files such as:

`data/synthetic/transactions.csv`

``` csv
transaction_ref,event_time,status,amount,authorized_join_ref
TX-001,2026-11-01T10:15:00+07:00,completed,150000,SESSION-101
TX-002,2026-11-01T11:20:00+07:00,pending,250000,SESSION-102
TX-003,2026-11-02T09:05:00+07:00,completed,85000,SESSION-103
```

`data/synthetic/system_events.csv`

``` csv
event_time,severity,event_type,event_ref,authorized_join_ref,message
2026-11-01T10:15:10+07:00,warning,api_timeout,EV-001,SESSION-101,Request timeout
2026-11-01T11:25:00+07:00,error,db_error,EV-002,SESSION-102,Database operation failed
2026-11-02T09:07:00+07:00,info,health_check,EV-003,SESSION-103,Health check passed
```

These are synthetic references created for testing and do not represent
actual identifiers from any external platform.

## 17. Local AI Behavior

The LLM integration shall:

1.  Use Ollama's local API.
2.  Use a configurable model.
3.  Explain analysis results supplied by the backend.
4.  Clearly state when data is insufficient.
5.  Avoid inventing statistics, events, records, or identities.
6.  Never execute arbitrary SQL or shell commands.
7.  Avoid sending raw personal identifiers to the model.
8.  Include a concise explanation of the method and limitations where
    relevant.

The first implementation may support general chat to validate
connectivity. Data-aware chat must be implemented only after the
analysis service returns verified result summaries.

## 18. Dashboard Requirements

The initial Streamlit dashboard shall include:

-   Application and database health status.
-   Ollama health and configured model.
-   Import form for supported files.
-   Source selection.
-   Import history and row counts.
-   Validation error summary.
-   Correlation rule selection.
-   Correlation result table.
-   Filters for source, time, and review status.
-   Local AI question-and-answer panel.
-   A visible warning that AI output is explanatory and must be
    validated by an analyst.

Do not display raw personal data by default.

## 19. Testing Plan

### Unit tests

-   Supported and unsupported file extensions.
-   Missing required columns.
-   Invalid timestamps.
-   Duplicate records.
-   Correlation with matching references inside the time window.
-   Correlation outside the time window.
-   Missing join references.
-   Empty datasets.
-   Database constraints and invalid review statuses.

### Integration tests

-   API health.
-   Database connection.
-   Import batch creation.
-   Import and row counts.
-   Persistence of correlation results.
-   Ollama unavailable behavior.
-   Chat response handling.
-   Access-control enforcement.

### Security tests

-   Unauthenticated access to protected endpoints is denied.
-   Viewer cannot import or change configuration.
-   Analyst cannot administer users.
-   SQL injection attempts are rejected or safely parameterized.
-   File upload size and type limits work.
-   Secrets and personal data do not appear in application logs.
-   Database and Ollama are not exposed publicly.

## 20. Acceptance Criteria

The MVP is accepted when:

-   AC-01: PostgreSQL starts and the schema migrations apply
    successfully.
-   AC-02: Ollama responds to a local API request.
-   AC-03: CSV, XLSX, and JSON imports work for supported schemas.
-   AC-04: System-log records can be parsed into normalized fields.
-   AC-05: Synthetic transaction and event records correlate according
    to the configured rule.
-   AC-06: Correlations outside the time window are excluded.
-   AC-07: Results can be traced to source batch and record references.
-   AC-08: Streamlit can communicate with FastAPI.
-   AC-09: AI answers are based on supplied verified results when making
    data-specific claims.
-   AC-10: Protected endpoints enforce authentication and role checks.
-   AC-11: No cloud LLM API is required.
-   AC-12: A PostgreSQL backup can be created and restored successfully.
-   AC-13: Automated tests pass.
-   AC-14: The README provides repeatable installation, startup,
    testing, and troubleshooting instructions.

## 21. Implementation Milestones

### Milestone 1 --- Environment and database

-   Install Python, Git, Docker Desktop, and Ollama.
-   Create the repository and virtual environment.
-   Start PostgreSQL.
-   Apply the initial schema.
-   Verify health checks.

### Milestone 2 --- Ingestion

-   Implement file validation.
-   Implement CSV, XLSX, and JSON parsing.
-   Implement log parsing.
-   Create import batch tracking.
-   Add ingestion tests.

### Milestone 3 --- Correlation engine

-   Implement normalization.
-   Implement the first approved correlation rule.
-   Persist results and provenance.
-   Add positive, negative, and boundary tests.

### Milestone 4 --- API and dashboard

-   Implement the required API routes.
-   Build the Streamlit interface.
-   Display source, import, and correlation results.
-   Add user-friendly error handling.

### Milestone 5 --- Local AI integration

-   Integrate FastAPI with Ollama.
-   Implement local chat.
-   Add a data-aware explanation endpoint that consumes verified
    analysis summaries.
-   Add tests for missing or unavailable model responses.

### Milestone 6 --- Security and acceptance

-   Implement authentication and RBAC.
-   Review data minimization and audit logging.
-   Add backup and restore instructions.
-   Run the full test suite.
-   Complete the acceptance checklist.

## 22. Codex Implementation Instructions

Codex should follow these instructions when implementing the project:

1.  Read this entire `SRS.md` before making changes.
2.  Inspect the existing repository before creating or replacing files.
3.  Implement only the requirements in this document unless
    clarification is requested.
4.  Work milestone by milestone in the order defined above.
5.  Before each milestone, summarize the files to be created or changed.
6.  Do not replace working code unnecessarily.
7.  Never insert real personal data, credentials, tokens, or production
    records into source code, tests, prompts, or logs.
8.  Use synthetic test fixtures.
9.  Add automated tests for each new core function.
10. Run tests after each milestone and report actual results; do not
    claim tests passed unless they were run.
11. Do not give the LLM direct access to unrestricted database queries,
    shell execution, or administrative actions.
12. Keep network services bound to localhost by default.
13. Add safe error handling and structured logging without sensitive
    payloads.
14. Update the README with actual setup and run commands.
15. If a requirement is ambiguous, document the assumption and ask
    before implementing risky behavior.
16. Do not add Kafka, Kubernetes, ClickHouse, a vector database, or
    multi-agent orchestration to the MVP without an approved requirement
    change.

### First task for Codex

Start with **Milestone 1 only**: - Inspect the repository. - Create the
basic project structure. - Add `.gitignore`, `.env.example`,
`requirements.txt`, `docker-compose.yml`, and the initial SQL
migration. - Document installation and startup steps in `README.md`. -
Validate the Compose configuration and schema setup where the
environment permits. - Do not implement the full application yet. -
Report files created, commands run, tests/checks performed, and any
remaining manual installation steps.

## 23. Official Documentation

-   Python downloads: https://www.python.org/downloads/
-   Docker Desktop for Windows:
    https://docs.docker.com/desktop/setup/install/windows-install/
-   Ollama downloads: https://ollama.com/download
-   Ollama API: https://docs.ollama.com/api/introduction
-   FastAPI: https://fastapi.tiangolo.com/
-   PostgreSQL: https://www.postgresql.org/docs/
-   Streamlit: https://docs.streamlit.io/
-   PostgreSQL Row-Level Security:
    https://www.postgresql.org/docs/current/ddl-rowsecurity.html

------------------------------------------------------------------------

**End of SRS v1.0**
