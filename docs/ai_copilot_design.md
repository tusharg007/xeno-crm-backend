# AI Copilot Design

## Goal
Provide a safe product-analytics assistant for a global messaging platform demo.

## Inputs
- DuckDB metric tables
- Metric definitions
- Data dictionary
- Business rules
- Glossary

## Core tools
- `run_sql_query`: execute read-only SQL against DuckDB
- `retrieve_metric_definition`: fetch exact metric meaning
- `detect_anomaly`: inspect recent anomaly table
- `generate_weekly_report`: produce a markdown report
- `summarize_dashboard_insights`: compile high-level executive summary

## Safety model
- Read-only SQL only
- Simple keyword routing before LLM reasoning
- Fallback deterministic answers when Groq is unavailable
- No claims about real production data; all datasets are synthetic
