# Global Messaging Product Analytics & AI Insights Platform

An end-to-end product analytics and data engineering project for a simulated global messaging and social platform. The project models how teams at large-scale consumer platforms track engagement, retention, feature adoption, notification performance, platform safety, and campaign outcomes from raw event data through dashboards and an AI insights copilot.

This is not a toy dashboard. It is designed as a miniature analytics stack: synthetic app events are generated, processed through an ETL pipeline, stored in analytics-ready tables, queried through a SQL metrics layer, visualized in Streamlit, and exposed to an AI copilot that can answer product questions in natural language.

The project uses synthetic data only. No real user data, private messages, or production platform data is used.

## What This Project Demonstrates

- Product analytics for a high-volume messaging/social application
- Data engineering pipelines from raw events to modeled analytics tables
- SQL-based KPI, funnel, retention, and safety metric calculation
- Dashboard design for executives, product managers, data analysts, and trust/safety teams
- AI-assisted analytics through a natural-language insights copilot
- A campaign and delivery simulator that demonstrates webhook-style event callbacks
- Mock-mode operation so the analytics dashboard works without external API keys

## Architecture

```text
Synthetic Messaging App Events
  -> Raw Data Layer
  -> ETL Pipeline
  -> Analytics Tables
  -> SQL Metrics Layer
  -> Dashboards
  -> AI Insights Copilot
  -> Product/Safety Recommendations
```

### How The Layers Map To This Repository

| Layer | Purpose | Main Files |
| --- | --- | --- |
| Synthetic Messaging App Events | Generates realistic product events such as messages, sessions, notifications, crashes, feature usage, reports, and campaign interactions. | `pipelines/generate_synthetic_data.py` |
| Raw Data Layer | Stores generated event data as raw CSV files before modeling. | `data/raw/` |
| ETL Pipeline | Cleans, normalizes, and loads raw events into DuckDB. | `pipelines/etl_pipeline.py` |
| Analytics Tables | Builds metric-ready tables for product, retention, funnel, safety, and campaign analysis. | `pipelines/build_metric_tables.py` |
| SQL Metrics Layer | Provides reusable read-only SQL tools for dashboards and the AI copilot. | `analytics/`, `ai/tools.py` |
| Dashboards | Streamlit interface for executive overview, retention, feature adoption, platform safety, and AI insights. | `app/streamlit_app.py` |
| AI Insights Copilot | Answers product analytics questions using deterministic analytics tools, optional Groq LLM calls, and project documentation context. | `ai/copilot.py`, `ai/rag.py` |
| Product/Safety Recommendations | Turns metrics and anomalies into practical product recommendations. | `docs/business_rules.md`, `docs/ai_copilot_design.md` |

## Product Analytics Scope

The platform tracks metrics that are common in messaging, social, and communication products:

- Daily active users, weekly trends, and engagement movement
- Message volume, delivery rate, open rate, click rate, and notification response
- Retention cohorts and activation funnels
- Feature adoption for messaging, groups, media, payments, profile, and search-style actions
- Safety signals such as spam reports, abuse reports, suspicious friend requests, and block actions
- Reliability metrics such as crash rate and platform-level issues
- Campaign delivery and attribution metrics through simulated delivery callbacks

## Relevance to Data Analytics / Data Engineering / AI Product Analytics Roles

This project is intentionally positioned for analytics and data-focused internship roles. It demonstrates the type of work expected in data analytics, product analytics, analytics engineering, data engineering, and AI product analytics teams.

### Large-Scale Event Analytics

The project starts from event-level data rather than hard-coded charts. It simulates app usage at the event level, which is how real messaging and social platforms operate. Every dashboard metric is derived from raw behavioral events such as sessions, messages, notifications, feature usage, safety reports, and campaign callbacks.

### Product KPI Tracking

The dashboard tracks practical product KPIs including active users, delivery rate, feature adoption, retention, crash rate, safety reports, and campaign performance. These are the types of metrics a product analytics team would monitor for a consumer app.

### Retention And Funnel Analysis

The retention and funnel views show how users move from acquisition to activation to repeat engagement. This is relevant for understanding onboarding quality, product stickiness, and where users drop off.

### Scalable Data Pipelines

The pipeline separates raw data, transformed data, and metric tables. This mirrors production analytics systems where raw logs are not queried directly by every dashboard. Instead, teams create reliable modeled tables that can support repeated analysis.

### Dashboarding

The Streamlit app is built as an analytics workspace with multiple views for different stakeholders: executives, product teams, safety teams, and analysts. The goal is not only to show charts, but to make business decisions easier.

### AI-Assisted Analytics

The AI copilot lets a user ask questions such as "Why did DAU drop?", "Which feature has low adoption?", or "Show me campaign performance." The copilot connects natural language to the underlying analytics layer instead of inventing answers.

### RAG And Natural-Language Insight Generation

The copilot can use project documentation such as metric definitions, business rules, glossary notes, and data dictionary context. This is a lightweight Retrieval-Augmented Generation pattern: answers are grounded in the project's known definitions and available SQL metrics.

### Platform Safety Analytics

The safety dashboard includes spam, abuse, suspicious behavior, blocking, and crash signals. This is especially relevant for messaging and social platforms where growth must be balanced with user trust and platform health.

## Dashboards

### Executive Overview

High-level product health view showing user activity, message volume, notification performance, reliability, and anomaly alerts.

### Retention & Funnel Dashboard

Tracks activation, retention cohorts, conversion steps, and drop-off points across the user lifecycle.

### Feature Adoption Dashboard

Shows which product areas are being used, where adoption is weak, and which geographies or cohorts are contributing to growth.

### Platform Safety Dashboard

Monitors spam reports, abuse reports, suspicious friend requests, blocking behavior, and crash-rate signals.

### AI Insights Copilot

Natural-language analytics interface for asking product, growth, safety, and campaign questions.

## Screenshot Placeholders

Add screenshots to `docs/screenshots/` using these filenames.

### Executive Overview Dashboard

![Executive Overview Dashboard](docs/screenshots/executive-overview-dashboard.png)

### Retention & Funnel Dashboard

![Retention & Funnel Dashboard](docs/screenshots/retention-funnel-dashboard.png)

### Feature Adoption Dashboard

![Feature Adoption Dashboard](docs/screenshots/feature-adoption-dashboard.png)

### Platform Safety Dashboard

![Platform Safety Dashboard](docs/screenshots/platform-safety-dashboard.png)

### AI Insights Copilot

![AI Insights Copilot](docs/screenshots/ai-insights-copilot.png)

## AI Copilot Examples

Try questions like:

- Why did DAU drop this week?
- Which country has the highest message growth?
- Which feature has low adoption?
- Are spam reports increasing?
- Which platform has the highest crash rate?
- Show me all campaign performance.
- Generate a weekly product analytics report.

The app can run without a Groq API key. In mock mode, the copilot uses deterministic analytics responses and SQL-backed dashboard data. If `GROQ_API_KEY` is provided, the copilot can also use Groq for more flexible natural-language generation.

## Campaign And Delivery Simulation

The repository also includes the original campaign simulation workflow. It demonstrates how communication systems track delivery outcomes:

```text
Campaign launched
  -> messages created
  -> channel service queues delivery
  -> sent / delivered / opened / clicked / failed callbacks
  -> CRM backend records receipts
  -> campaign analytics update
```

This part is useful for explaining webhook-driven event ingestion and attribution, which are common in marketing analytics, product notifications, and growth systems.

## Tech Stack

- Python
- FastAPI
- Streamlit
- DuckDB
- SQLite
- SQLAlchemy
- Pydantic
- Pandas
- Plotly
- LangGraph/Groq utilities for optional AI workflows
- Synthetic data generation and ETL pipelines

## Repository Map

```text
app/streamlit_app.py                 Streamlit analytics dashboard
main.py                              FastAPI application and health checks
analytics/                           DuckDB client and analytics helpers
ai/                                  AI copilot, RAG helpers, and SQL tools
pipelines/                           Synthetic data, ETL, metric tables, anomalies
docs/                                Metric definitions, glossary, business rules
routers/                             API routers for analytics and campaign simulation
models.py                            SQLAlchemy entities for campaign simulation
schemas.py                           Pydantic request/response models
seed_data.py                         Demo customer and order data generation
tests/                               Lightweight validation tests
```

## Run Locally

Recommended Python version: `3.11`.

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Generate synthetic analytics data

```bash
python pipelines/generate_synthetic_data.py --rows 100000
```

### 3. Run the ETL pipeline

```bash
python pipelines/etl_pipeline.py
```

### 4. Build metric tables and anomaly alerts

```bash
python pipelines/build_metric_tables.py
python pipelines/anomaly_detection.py
```

### 5. Start the dashboard

```bash
streamlit run app/streamlit_app.py
```

### 6. Optional: start the FastAPI backend

```bash
uvicorn main:app --reload
```

FastAPI docs will be available at:

```text
http://127.0.0.1:8000/docs
```

Health check:

```text
http://127.0.0.1:8000/health
```

## Mock Mode And API Keys

The analytics dashboard works without external API keys. If `GROQ_API_KEY` is not set, the AI copilot falls back to deterministic analytics logic and SQL-backed responses.

Optional `.env`:

```env
GROQ_API_KEY=
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
DATABASE_URL=sqlite:///./xeno_crm.db
ANALYTICS_DB_PATH=data/processed/messaging_analytics.duckdb
CHANNEL_SERVICE_URL=http://localhost:8001
```

## Strong Resume Bullets

- Built an end-to-end product analytics platform for a simulated global messaging app, processing synthetic event data through Python ETL pipelines into DuckDB analytics tables and Streamlit dashboards.
- Designed KPI dashboards for DAU, retention, funnel conversion, feature adoption, notification delivery, crash rate, spam reports, and campaign performance using SQL, Pandas, and Plotly.
- Implemented an AI analytics copilot that maps natural-language product questions to SQL-backed metrics, documentation context, and deterministic fallback responses for mock-mode reliability.
- Modeled webhook-style campaign delivery events through a FastAPI backend and async channel simulator, enabling delivery, open, click, failure, and attribution analytics.
- Created recruiter-ready documentation, metric definitions, data dictionary, business rules, and demo scripts to explain product impact, data architecture, and future scaling paths.

## Future Improvements

- Move from SQLite/DuckDB local storage to PostgreSQL plus a warehouse-style analytics database.
- Add dbt-style metric modeling and data quality tests.
- Add Airflow or Dagster for scheduled orchestration.
- Add Kafka or Redis queues for durable event ingestion and delivery callbacks.
- Add authentication, role-based access, and audit logs for production readiness.
- Add experiment analysis, cohort drilldowns, and anomaly alert routing.
- Add a larger RAG layer over dashboards, metric definitions, incident reports, and product notes.

## Important Documentation

- [Metric Definitions](docs/metric_definitions.md)
- [Data Dictionary](docs/data_dictionary.md)
- [Product Analytics Glossary](docs/product_analytics_glossary.md)
- [Business Rules](docs/business_rules.md)
- [AI Copilot Design](docs/ai_copilot_design.md)
- [Interview Explanation](docs/interview_explanation.md)
- [Demo Script](docs/demo_script.md)
