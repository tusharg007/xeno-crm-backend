# Interview Explanation

## Why I Built This Project

I built this project to demonstrate a full product analytics workflow for a messaging and social platform. Instead of only creating charts from static data, I wanted to show the complete path from raw events to business insight.

The product idea is a simulated global messaging app. In a real messaging platform, every user action generates events: app sessions, sent messages, delivered messages, opened notifications, crashes, spam reports, friend requests, and feature usage. Product and data teams use those events to understand user engagement, retention, safety, reliability, and growth.

This project recreates that workflow in a smaller but realistic way. It generates synthetic app events, processes them through ETL, builds analytics tables, shows dashboards, and provides an AI insights copilot that can answer questions about the metrics.

## Architecture

The architecture follows a common analytics stack:

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

The synthetic event generator creates raw product events. The ETL pipeline loads and cleans them. Metric tables are built in DuckDB so dashboards do not need to query raw logs directly. The Streamlit app reads from these metric tables and visualizes the result. The AI copilot sits on top of the same metrics layer and turns natural-language questions into grounded answers.

The project also includes a FastAPI backend and a campaign delivery simulator. That part demonstrates how webhook-style callbacks work. A campaign creates messages, a channel service simulates delivery states, and receipt events update campaign analytics.

## Data Pipeline

The data pipeline has three major stages.

First, `pipelines/generate_synthetic_data.py` creates synthetic events. These events represent user sessions, messages, notification activity, safety reports, crash events, feature usage, and campaign outcomes. This gives the project an event-level foundation instead of hard-coded dashboard numbers.

Second, `pipelines/etl_pipeline.py` reads raw CSV data and loads it into DuckDB staging tables. This is the cleaning and normalization stage. In a real company, this would be similar to moving raw app logs from object storage into warehouse tables.

Third, `pipelines/build_metric_tables.py` builds analytics-ready tables. These tables calculate product KPIs, funnel metrics, retention cohorts, feature adoption, campaign metrics, and safety metrics. `pipelines/anomaly_detection.py` adds anomaly alerts using historical baselines.

The important design decision is separation of concerns: raw data is preserved, transformed data is modeled, and dashboards read from metric tables.

## Metric Definitions

The project tracks several categories of metrics.

Active user metrics include DAU and trend movement. These help answer whether the product is growing, stable, or declining.

Messaging metrics include message volume, delivery rate, open rate, click rate, and failure rate. These help measure communication reliability and user engagement.

Retention metrics measure whether users come back after their first activity. Retention matters because growth without repeat usage is usually weak product-market fit.

Funnel metrics show where users drop off across activation steps. For example, a user may install the app, create an account, send a first message, join a group, or receive a notification.

Feature adoption metrics show which features are used frequently and which are underused. This helps product teams prioritize improvements.

Safety metrics include spam reports, abuse reports, suspicious friend requests, blocks, and crash rates. These are important for messaging platforms because trust and reliability directly affect retention.

Campaign metrics include targeted users, delivered messages, opened messages, clicked messages, failed messages, attributed orders, and attributed revenue.

## AI Copilot

The AI copilot is designed to answer analytics questions in natural language. The key goal is grounding: it should use actual metrics and project documentation instead of inventing numbers.

The copilot uses a few layers:

- Deterministic routing for common product analytics questions.
- SQL-backed tools for fetching real dashboard metrics.
- Documentation context from files such as metric definitions, glossary, business rules, and data dictionary.
- Optional Groq LLM calls if a Groq API key is configured.
- Mock-mode fallback when no API key is available.

This makes the demo reliable. If the external LLM is unavailable, the dashboard and many copilot answers still work using local metrics.

## Anomaly Detection

The anomaly detection layer identifies unusual product behavior by comparing current values against historical baselines. In a production system, this could use more advanced methods such as seasonal decomposition, statistical thresholds, Bayesian models, or ML-based anomaly detection.

In this project, the goal is practical: show that analytics should not only report numbers, but also flag when something needs attention. Examples include DAU drops, spam report spikes, crash-rate increases, or unusual delivery failures.

## Business Impact

This project is useful because it connects technical data engineering work to product decisions.

An executive can use the dashboard to understand overall product health. A product manager can use retention and feature adoption dashboards to prioritize experiments. A safety team can monitor spam and abuse trends. A growth team can inspect notification and campaign performance. An analyst can ask the AI copilot for summaries and investigate anomalies faster.

The campaign simulation also shows how attribution works. If a communication is delivered, opened, clicked, and later followed by an order, the platform can connect that outcome back to the campaign. This is important for measuring whether messages actually create business value.

## Limitations

The data is synthetic, so it does not reflect real user behavior perfectly. The pipeline runs locally rather than on distributed infrastructure. DuckDB is excellent for local analytics, but a production system would likely use a cloud warehouse. The AI copilot is intentionally constrained for reliability and does not have the full reasoning power of a production analytics assistant. Authentication, authorization, audit logging, and real-time streaming are not implemented.

The campaign simulator also does not send real messages. It simulates lifecycle events such as sent, delivered, opened, clicked, and failed. That is intentional because the project focuses on analytics and event handling rather than real communication delivery.

## Future Improvements

With more time, I would move the operational database to PostgreSQL, orchestrate the data pipeline with Airflow or Dagster, add dbt-style metric modeling, and introduce data quality tests.

For scale, I would use Kafka or a queue system for event ingestion, add Redis for caching and async jobs, and separate the analytics warehouse from the transactional backend.

For product analytics depth, I would add experiment analysis, cohort drilldowns, user segmentation, notification fatigue metrics, safety risk scoring, and alert routing.

For the AI layer, I would improve RAG with embeddings, add query planning, show SQL citations, and make every answer explain which metric table or definition it used.

For production readiness, I would add JWT authentication, role-based access control, audit logs, rate limiting, monitoring, and deployment observability.
