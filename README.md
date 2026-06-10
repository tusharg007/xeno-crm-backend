# Xeno Mini CRM - StyleHub

Xeno Mini CRM is an AI-native campaign management system for StyleHub, an Indian fashion retailer, built for the Xeno FDE assignment 2026. It helps marketers find the right customer audience, save that audience as a reusable segment, draft personalized campaign copy, launch campaigns through a simulated channel service, and watch delivery analytics update from receipt callbacks.

## Live Demo

- Frontend: https://xeno-crm-backend-5eeqqhufg62kjv6zlsuhvz.streamlit.app
- API Docs: https://xeno-crm-backend-uelp.onrender.com/docs
- Channel Service: https://xeno-channel-service-c1yr.onrender.com/health

## Architecture

```txt
    ┌─────────────────────────────────────────────────────────┐
    │                  Streamlit Frontend                     │
    │   Chat Interface (Tab 1)    Analytics Dashboard (Tab 2) │
    └──────────┬──────────────────────────┬───────────────────┘
               │ POST /agent/chat         │ GET /campaigns
               ▼                          ▼
    ┌─────────────────────────────────────────────────────────┐
    │                FastAPI CRM Backend                      │
    │                                                         │
    │  LangGraph Agent (agent/)     REST API (routers/)       │
    │  ├─ Intent parsing            ├─ /customers             │
    │  ├─ 5 tools                   ├─ /segments              │
    │  ├─ HITL approval gate        ├─ /campaigns             │
    │  └─ Session memory            └─ /receipt (callbacks)   │
    │                                                         │
    │              SQLite — 5 tables                          │
    │   customers│orders│segments│campaigns│messages          │
    └──────────────────────┬──────────────────────────────────┘
                           │ POST /send-batch (chunks of 50)
                           ▼
    ┌─────────────────────────────────────────────────────────┐
    │           Channel Service (separate deploy)             │
    │  Receives messages → simulates delivery lifecycle       │
    │  Async: sent → delivered → opened → clicked             │
    │  Fires callbacks → POST /receipt on CRM backend         │
    └─────────────────────────────────────────────────────────┘
```

## Key Technical Decisions

| Decision | What I did | Why | At production scale |
|---|---|---|---|
| Database | SQLite | Zero config, no infra needed | PostgreSQL with read replicas for analytics |
| Channel simulation | Async callbacks with per-channel delay+rate profiles | Mirrors real provider lifecycle (Twilio, MSG91) | Redis queue + dead-letter queue for guaranteed delivery |
| Agent memory | In-memory session dict | Simple, demo-safe, no external dependency | Redis or DynamoDB for distributed session state |
| Callback idempotency | STATUS_ORDER index comparison | Prevents backward state on out-of-order callbacks | Idempotency keys + exactly-once semantics via DB constraint |
| Campaign launch | Batch send in chunks of 50 via asyncio.gather | Avoids thundering herd on channel service | Message queue (SQS/Kafka) between CRM and channel service |
| Message personalization | String template substitution {name},{city},{last_category} | Predictable, fast, testable | LLM-personalized per recipient with full purchase context |

## Data Model

`Customer` stores profile, RFM aggregates, and last-order state so audience queries are fast without recomputing order history on every request.
`Order` stores retail purchase events with category, amount, product, channel, and timestamp so the segment engine can target behavior like ethnic wear buyers or high-value customers.
`Segment` stores `filter_rules` as a JSON string because the AI agent can create flexible audience definitions without requiring a schema migration for every new targeting dimension, and `created_by` distinguishes human-created audiences from AI-created ones.
`Campaign` denormalizes aggregate counters such as sent, delivered, opened, clicked, and failed so analytics reads are O(1) for dashboard refreshes.
`Message` stores one row per recipient with per-event timestamps, which enables funnel analysis and idempotent callback handling without expensive joins.

## Local Setup

```bash
# 1. Clone both repositories
git clone https://github.com/tusharg007/xeno-crm-backend.git
git clone https://github.com/tusharg007/xeno-channel-service.git

# 2. Set up the CRM backend
cd xeno-crm-backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure backend environment
cp .env.example .env
# Edit .env and set:
# GROQ_API_KEY=your_groq_key
# LLM_PROVIDER=groq
# LLM_MODEL=llama-3.3-70b-versatile
# CHANNEL_SERVICE_URL=http://localhost:8001
# DATABASE_URL=sqlite:///./xeno_crm.db

# 4. Create and seed the CRM database
python seed_data.py

# 5. Start the CRM backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 6. In another terminal, set up the channel service
cd ../xeno-channel-service
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# 7. Start the channel service
uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# 8. In another terminal, start the Streamlit frontend
cd ../xeno-crm-backend
source .venv/bin/activate
streamlit run streamlit_app.py
```

Local URLs:

- Streamlit frontend: `http://localhost:8501`
- CRM backend: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`
- Channel service: `http://localhost:8001`

## Project Structure

```txt
xeno-crm-backend/
├── agent/
│   ├── graph.py              # LangGraph state machine, HITL approval gate, session memory
│   └── tools.py              # 5 DB-backed agent tools
├── routers/
│   ├── customers.py          # Customer ingestion, order ingestion, stats
│   ├── segments.py           # Segment CRUD and filter engine
│   ├── campaigns.py          # Campaign CRUD, launch, message creation
│   └── receipts.py           # Delivery callback idempotency and analytics counters
├── .streamlit/
│   └── config.toml           # Streamlit Cloud/server theme config
├── config.py                 # Environment settings
├── database.py               # SQLAlchemy engine/session/base helpers
├── main.py                   # FastAPI app, router wiring, agent chat endpoint
├── models.py                 # SQLAlchemy 2.0 ORM models
├── schemas.py                # Pydantic v2 schemas
├── seed_data.py              # StyleHub customer/order seed generator
├── streamlit_app.py          # Chat UI and analytics dashboard
├── requirements.txt          # Backend + local frontend dependencies
├── requirements_streamlit.txt # Streamlit Cloud-only dependencies
└── render.yaml               # Render backend deployment blueprint

xeno-channel-service/
├── main.py                   # FastAPI send/send-batch endpoints
├── simulator.py              # Async delivery lifecycle simulator
├── requirements.txt          # Channel service dependencies
├── render.yaml               # Render channel service deployment blueprint
└── README.md                 # Channel service usage and lifecycle docs
```

## What I Would Add With More Time

1. WebSocket for live dashboard — replace 4-second polling with push events.
2. LLM-personalized messages per recipient using full purchase history — improve relevance beyond template tokens.
3. Predictive churn scoring from RFM features surfaced in the agent — help marketers prioritize high-risk customers.
4. Multi-tenant support — add `brand_id` to all tables, scope all queries.
5. Campaign scheduling — launch at a future datetime via APScheduler.
