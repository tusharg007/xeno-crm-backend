# Two-Minute Demo Script

## 0:00 - 0:15: Introduction

Hi, I built a product analytics and AI insights platform for a simulated global messaging app. The goal is to show how raw app events can become product KPIs, dashboards, anomaly alerts, and AI-assisted insights.

## 0:15 - 0:35: Architecture

The architecture starts with synthetic messaging app events. These events move into a raw data layer, then an ETL pipeline cleans and loads them into DuckDB. After that, metric tables are built for product analytics, retention, feature adoption, safety, and campaign performance. Streamlit visualizes these metrics, and the AI copilot answers questions using the same analytics layer.

## 0:35 - 1:05: Dashboard Walkthrough

On the dashboard, the executive overview gives a quick health check of the product. I can see active users, message performance, notification outcomes, crash signals, and anomaly alerts.

The retention and funnel page shows where users are dropping off and whether cohorts are coming back. The feature adoption page shows which product areas are being used more or less. The platform safety page monitors signals like spam reports, suspicious behavior, blocks, and crash rate.

## 1:05 - 1:30: AI Insights Copilot

The AI copilot lets me ask product questions in natural language, such as "Why did DAU drop this week?", "Which feature has low adoption?", or "Show campaign performance." The copilot is connected to SQL-backed metrics and documentation, so the answers are grounded in the data rather than just generic LLM output. It also works in mock mode without an external API key.

## 1:30 - 1:50: Campaign And Webhook Simulation

I also kept a campaign simulation workflow. When a campaign launches, messages are created and a separate channel service simulates delivery events like sent, delivered, opened, clicked, and failed. These callbacks update campaign analytics, which demonstrates webhook-style event ingestion and attribution.

## 1:50 - 2:00: Closing

Overall, this project demonstrates data engineering pipelines, product KPI tracking, retention and funnel analysis, safety analytics, dashboarding, and AI-assisted analytics. If I had more time, I would scale it with PostgreSQL, Airflow or Dagster, dbt-style modeling, queue-based ingestion, authentication, and stronger RAG over metric definitions.
