# Xeno Mini CRM

An AI-native campaign manager for retail brands. A marketer describes who they want
to reach in plain English; the agent finds the audience, writes the message, and
gates on human approval before launching. A separate channel service simulates async
delivery and fires real-time callbacks, making the analytics dashboard update live.

Built for Xeno's FDE Internship Drive 2026.

## Live demo

| | |
|---|---|
| Frontend | [StyleHub CRM](https://xeno-crm-backend-5eeqqhufg62kjv6zlsuhvz.streamlit.app) |
| API docs | [https://xeno-crm-backend-uelp.onrender.com/docs](https://xeno-crm-backend-uelp.onrender.com/docs) |
| CRM health | [https://xeno-crm-backend-uelp.onrender.com/health](https://xeno-crm-backend-uelp.onrender.com/health) |
| Channel health | [https://xeno-channel-service-c1yr.onrender.com/health](https://xeno-channel-service-c1yr.onrender.com/health) |
| Walkthrough | Not recorded yet |

## Architecture

Two independently deployed services communicating only via HTTP:

```text
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
│  └─ In-memory session store   └─ /receipt (callbacks)   │
│                                                         │
│              SQLite - 5 tables                          │
│   customers | orders | segments | campaigns | messages  │
└──────────────────────┬──────────────────────────────────┘
                       │ POST /send-batch (chunks of 50)
                       ▼
┌─────────────────────────────────────────────────────────┐
│           Channel Service (separate deploy)             │
│  Receives messages -> simulates delivery lifecycle      │
│  Async: sent -> delivered -> opened -> clicked          │
│  Fires callbacks -> POST /receipt on CRM backend        │
└─────────────────────────────────────────────────────────┘
```

## What makes this AI-native

The LangGraph agent doesn't just generate text. It reasons about customer data,
executes database queries via tools, drafts personalized copy, and maintains
conversational state across turns. The marketer never touches a form.

The HITL approval gate is a deliberate design decision: when the agent has built
a segment and drafted a message, it embeds `AWAITING_APPROVAL:[segment_id]` as
a signal token in its response. The graph parses this signal, sets
`awaiting_approval=True` in state, and surfaces a confirmation card in the UI.
`launch_campaign` cannot be called until the marketer explicitly approves; the
system prompt forbids it. This prevents a misunderstood instruction from
firing a campaign to thousands of real customers.

## Key technical decisions

| Decision | What I did | Why | At production scale |
|---|---|---|---|
| Database | SQLite | Zero config, sufficient for demo scope | PostgreSQL with read replicas for analytics |
| LLM provider | Groq with Llama 3.3 70B | Fast responses on the free tier and OpenAI-compatible chat semantics | Provider routing, fallbacks, and spend controls |
| Channel simulation | Async callbacks with per-channel probability profiles | Mirrors real provider lifecycle such as Twilio or MSG91 | Redis queue + dead-letter queue for guaranteed delivery |
| Callback idempotency | `STATUS_ORDER` index comparison | Prevents backward state on out-of-order or duplicate callbacks | Idempotency keys + exactly-once semantics via DB unique constraint |
| Agent memory | In-memory session dict, module-level | Simple, demo-safe, no external dependency | Redis with TTL for distributed session state |
| Campaign launch | Batch POST in chunks of 50 via async fan-out | Avoids thundering herd on channel service | Message queue such as SQS or Kafka between CRM and channel service |
| HITL gate | Signal token in agent response text | Avoids complex graph branching, keeps state machine simple | Dedicated approval workflow with audit log and rollback |

## The callback loop in detail

When a campaign launches, the CRM sends campaign messages to the channel service
`/send-batch` endpoint. The channel service simulates delivery asynchronously:
each message goes through sent -> delivered -> opened -> clicked with
channel-specific probability profiles (WhatsApp: 55% open rate, SMS: 35%,
Email: 25%).

Each state transition fires a POST back to `/receipt` on the CRM. The receipt
handler validates forward progress via `STATUS_ORDER` index comparison, updates
the message's status and timestamp, then recalculates campaign aggregate counters
using SQL COUNT subqueries rather than Python-side counting to stay safe under
concurrent callbacks. The campaign auto-completes when all messages reach a
terminal state.

## Data model

Five tables. Key design choices:

**`filter_rules` stored as a JSON string on Segment**: lets the agent generate and
store arbitrary filter combinations without schema migrations. The agent writes
`{"recency_days": 60, "gender": "F", "category": "Ethnic Wear"}` and the
`execute_segment_filter` function dynamically builds the SQL WHERE clause.

**Campaign aggregate counters denormalized**: `total_delivered`, `total_opened`,
and related counters are updated on every `/receipt` callback via SQL COUNT
subqueries. Analytics reads are O(1), with no aggregation at read time.

**Per-event timestamps on Message**: `sent_at`, `delivered_at`, `opened_at`,
`clicked_at`, and `failed_at` enable time-to-open analysis and delivery funnel
charts without joining to a separate events table.

**`created_by` on Segment (`human` or `ai`)**: distinguishes agent-created
segments from manually built ones.

## Local setup

```bash
git clone https://github.com/tusharg007/xeno-crm-backend
cd xeno-crm-backend
pip install -r requirements.txt
cp .env.example .env        # add GROQ_API_KEY

python seed_data.py         # seeds 200 customers + 650-800 orders
uvicorn main:app --reload   # starts on :8000, auto-seeds if DB empty

# In a second terminal:
git clone https://github.com/tusharg007/xeno-channel-service
cd xeno-channel-service
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --port 8001 --reload

# In a third terminal:
cd xeno-crm-backend
streamlit run streamlit_app.py
```

## Required environment

Backend:

```env
GROQ_API_KEY=your_groq_key_here
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
CHANNEL_SERVICE_URL=http://localhost:8001
DATABASE_URL=sqlite:///./xeno_crm.db
```

Channel service:

```env
CRM_RECEIPT_URL=http://localhost:8000/receipt
PORT=8001
```

Streamlit Cloud:

```toml
CRM_BACKEND_URL = "https://xeno-crm-backend-uelp.onrender.com"
```

## Project structure

```text
xeno-crm-backend/
├── main.py              # FastAPI app, startup auto-seed, /agent/chat, /demo/reset
├── config.py            # Pydantic settings: DATABASE_URL, GROQ_API_KEY, CHANNEL_SERVICE_URL
├── database.py          # SQLAlchemy engine, SessionLocal, Base, get_db()
├── models.py            # 5 SQLAlchemy 2.0 models (Mapped[] style)
├── schemas.py           # Pydantic v2 schemas with computed delivery rates
├── seed_data.py         # 200 customers + orders across 4 RFM segments
├── streamlit_app.py     # Frontend: AI chat tab + analytics dashboard
├── routers/
│   ├── customers.py     # CRUD + /stats/overview (RFM breakdown)
│   ├── segments.py      # CRUD + execute_segment_filter() engine
│   ├── campaigns.py     # Create, launch with batch send
│   └── receipts.py      # Async callback handler with idempotency
└── agent/
    ├── tools.py         # 5 LangGraph tools with db session injection
    └── graph.py         # StateGraph, HITL gate, in-memory session store

xeno-channel-service/
├── main.py              # POST /send, POST /send-batch
└── simulator.py         # DeliverySimulator with per-channel probability profiles
```

## Smoke tests

```bash
curl https://xeno-crm-backend-uelp.onrender.com/health
curl https://xeno-crm-backend-uelp.onrender.com/customers/stats/overview
curl https://xeno-channel-service-c1yr.onrender.com/health
```

Expected:

- CRM health returns `{"status":"ok","service":"xeno-crm"}`.
- Customer stats show 200 seeded customers and RFM counts.
- Channel health returns `{"status":"ok","service":"xeno-channel-service"}`.
- Streamlit sidebar shows customer count.
- Full loop works: find -> draft -> approve -> launch -> Analytics updates live.

## What I would add with more time

1. **WebSocket for live dashboard**: replace 4-second polling with a WebSocket
   connection that pushes receipt events to the frontend in real time.

2. **LLM-personalized messages per recipient**: instead of string template
   substitution, give the LLM each customer's purchase history and generate a
   unique message for each recipient.

3. **Predictive churn scoring**: use the RFM features already in the data model
   to train a churn model; surface a risk score on each customer profile and let
   the agent reference it when building segments.

4. **Multi-tenant architecture**: add `brand_id` to all tables and scope every
   query by it; the current single-tenant design supports this with one migration.

5. **Campaign scheduling**: allow the agent to schedule a campaign for a future
   datetime. "Send this tomorrow morning at 10am IST" is a natural language
   instruction the agent could parse and honour.
