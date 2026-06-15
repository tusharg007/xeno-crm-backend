# Xeno Mini CRM — StyleHub

An AI-native campaign manager for retail brands. A marketer describes who they want
to reach in plain English; the agent finds the audience, writes the message, and
gates on human approval before launching. A separate channel service simulates async
delivery and fires real-time callbacks, making the analytics dashboard update live.
Lifecycle automations (Journeys) let marketers set up always-on triggers that
auto-launch campaigns when customer segments match.

Built for Xeno's FDE Internship Drive 2026.

## Live demo
| | |
|---|---|
| Frontend | [StyleHub CRM](https://xeno-crm-backend-5eeqqhufg62kjv6zlsuhvz.streamlit.app) |
| API docs | [https://xeno-crm-backend-uelp.onrender.com/docs](https://xeno-crm-backend-uelp.onrender.com/docs) |
| CRM health | [https://xeno-crm-backend-uelp.onrender.com/health](https://xeno-crm-backend-uelp.onrender.com/health) |
| Channel health | [https://xeno-channel-service-c1yr.onrender.com/health](https://xeno-channel-service-c1yr.onrender.com/health) |

## Architecture
Two independently deployed services communicating only via HTTP:

```text
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Frontend                        │
│  AI Campaign Agent │ Analytics Dashboard │ Journeys Manager  │
└──────┬─────────────────────┬──────────────────┬─────────────┘
       │ POST /agent/chat    │ GET /campaigns   │ POST /journeys/{id}/trigger
       ▼                     ▼                  ▼
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI CRM Backend                        │
│                                                              │
│  Hybrid Agent (agent/)          REST API (routers/)           │
│  ├─ Deterministic fast-path     ├─ /customers (CRUD + CDP)   │
│  ├─ LangGraph LLM fallback     ├─ /segments                 │
│  ├─ 6 tools                     ├─ /campaigns                │
│  ├─ HITL approval gate          ├─ /journeys (6 templates)   │
│  ├─ Groq retry/backoff          └─ /receipt (callbacks)      │
│  └─ In-memory session store                                  │
│                                                              │
│              SQLite - 6 tables                               │
│  customers │ orders │ segments │ journeys │ campaigns │ msgs │
└──────────────────────┬──────────────────────────────────────┘
                       │ POST /send-batch (chunks of 50)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│           Channel Service (separate deploy)                  │
│  Receives messages → simulates delivery lifecycle            │
│  Async: sent → delivered → read → opened → clicked           │
│  Fires callbacks → POST /receipt on CRM backend              │
│  Revenue attribution → POST /customers/{id}/order-attributed │
└─────────────────────────────────────────────────────────────┘
```

## What makes this AI-native
The agent uses a **hybrid deterministic + LLM architecture**. Common intents
(greetings, audience queries with clear filters, category insights, campaign
performance, save/launch confirmations) are handled by a deterministic fast-path
that parses the user's message, runs SQL queries directly, and returns structured
responses — no LLM call needed. Only ambiguous or complex requests fall through to
the LangGraph ReAct loop backed by Groq's Llama 3.3 70B.

This design gives sub-second responses for the most common flows, eliminates LLM
rate-limit sensitivity for demo scenarios, and keeps the agent accurate by
grounding every data answer in actual SQL results rather than LLM hallucination.

The HITL approval gate is a deliberate design decision: when the agent has built
a segment and drafted a message, it embeds `AWAITING_APPROVAL:[segment_id]` as
a signal token in its response. The graph parses this signal, sets
`awaiting_approval=True` in state, and surfaces a confirmation card in the UI.
`launch_campaign` cannot be called until the marketer explicitly approves; the
system prompt forbids it. This prevents a misunderstood instruction from
firing a campaign to thousands of real customers.

## Key features

### AI campaign agent (6 tools)
| Tool | Purpose |
|---|---|
| `query_customers_by_filters` | Find audience by recency, spend, gender, city, category, order count |
| `get_category_insights` | SQL-backed category buying analytics (never answers from general knowledge) |
| `create_segment` | Save matched audience with `created_by='ai'` tag |
| `draft_campaign_message` | Generate 3 WhatsApp/SMS message variants via LLM |
| `launch_campaign` | Create campaign + batch-POST to channel service in chunks of 50 |
| `get_campaign_analytics` | Campaign performance with delivery/open/click rates and revenue attribution |

### Journeys (lifecycle automation)
Six pre-built journey templates that auto-trigger campaigns when customer
segments match:
- **Win-Back Lapsed Customers** — inactive 60+ days
- **Save High-Value Customers** — top spenders becoming inactive (30-60 days, ≥₹5,000)
- **First Purchase Follow-up** — new customers within 7 days of first order
- **Reward Repeat Buyers** — 5+ orders, active within 45 days
- **Re-engage Lapsed Buyers** — inactive 90-180 days
- **Category Cross-Sell** — suggest next best category to single-category buyers

Each journey creates a segment, launches a campaign, and excludes customers
already in active campaigns to prevent message fatigue.

### Customer intelligence (CDP-style profiles)
Rich customer profiles with computed fields:
- **RFM persona**: Champion, Loyal, At Risk, Lapsed, Solo Buyer, New
- **Preferred channel**: WhatsApp / SMS / Email (weighted by gender)
- **Preferred day**: Weekdays vs Weekends (based on order history)
- **Next best category**: Cross-sell recommendation from purchase patterns
- **Campaign engagement**: messages received, opened, attributed orders

### Revenue attribution pipeline
The channel service simulates post-click conversions: 25% of clicked messages
generate an attributed order (random ₹500-₹4,000). The `/customers/{id}/order-attributed`
endpoint attributes the order to the campaign within a 7-day delivery window.
Campaign aggregate counters (`total_attributed_orders`, `total_attributed_revenue`)
update in real time.

## Key technical decisions
| Decision | What I did | Why | At production scale |
|---|---|---|---|
| Database | SQLite | Zero config, sufficient for demo scope | PostgreSQL with read replicas for analytics |
| LLM provider | Groq with Llama 3.3 70B | Fast responses on the free tier and OpenAI-compatible chat semantics | Provider routing, fallbacks, and spend controls |
| Agent architecture | Hybrid deterministic fast-path + LangGraph LLM fallback | Sub-second responses for common flows, LLM reserved for ambiguous requests | Intent classifier → deterministic handlers with LLM as catch-all |
| Groq resilience | Retry with exponential backoff (3 attempts, 12s timeout) | Free tier rate limits cause transient failures | Circuit breaker with provider fallback chain |
| Channel simulation | Async callbacks with per-channel probability profiles | Mirrors real provider lifecycle such as Twilio or MSG91 | Redis queue + dead-letter queue for guaranteed delivery |
| Callback idempotency | `STATUS_ORDER` index comparison | Prevents backward state on out-of-order or duplicate callbacks | Idempotency keys + exactly-once semantics via DB unique constraint |
| Agent memory | In-memory session dict, module-level | Simple, demo-safe, no external dependency | Redis with TTL for distributed session state |
| Campaign launch | Batch POST in chunks of 50 via async fan-out | Avoids thundering herd on channel service | Message queue such as SQS or Kafka between CRM and channel service |
| HITL gate | Signal token in agent response text | Avoids complex graph branching, keeps state machine simple | Dedicated approval workflow with audit log and rollback |
| Attribution | 7-day window post-delivery, channel service simulates conversions | Mirrors real-world campaign attribution logic | Event-sourced attribution with configurable windows per campaign |

## The callback loop in detail
When a campaign launches, the CRM sends campaign messages to the channel service
`/send-batch` endpoint. The channel service simulates delivery asynchronously:
each message goes through sent → delivered → read → opened → clicked with
channel-specific probability profiles:

| Channel | Failure rate | Read rate | Open rate | Click rate |
|---|---|---|---|---|
| WhatsApp | 3% | 70% | 55% | 32% |
| SMS | 8% | — | 35% | 18% |
| Email | 5% | — | 25% | 22% |

Each state transition fires a POST back to `/receipt` on the CRM. The receipt
handler validates forward progress via `STATUS_ORDER` index comparison, updates
the message's status and timestamp, then recalculates campaign aggregate counters
using SQL COUNT subqueries rather than Python-side counting to stay safe under
concurrent callbacks. The campaign auto-completes when all messages reach a
terminal state.

After a click event, the channel service waits 30-120 seconds and with 25%
probability simulates a purchase attribution by calling
`POST /customers/{customer_id}/order-attributed` on the CRM.

## Data model
Six tables. Key design choices:

**`filter_rules` stored as a JSON string on Segment**: lets the agent generate and
store arbitrary filter combinations without schema migrations. The agent writes
`{"recency_days": 60, "gender": "F", "category": "Ethnic Wear"}` and the
`execute_segment_filter` function dynamically builds the SQL WHERE clause.
Supports 9 filter keys: `recency_days`, `max_recency_days`, `min_spend`,
`max_spend`, `gender`, `city`, `category`, `min_orders`, `max_orders`, plus
special keys `customer_ids`, `message_statuses`, `campaign_status`, and
`attributed_order` for campaign engagement queries.

**Journey table**: stores lifecycle automations with `trigger_rules` (same
JSON filter format as segments), `message_template`, `channel`, and counters
for `customers_enrolled` and `campaigns_triggered`.

**Campaign aggregate counters denormalized**: `total_delivered`, `total_read`,
`total_opened`, `total_clicked`, `total_failed`, `total_attributed_orders`,
and `total_attributed_revenue` are updated on every `/receipt` callback via
SQL COUNT subqueries. Analytics reads are O(1), with no aggregation at read time.

**Per-event timestamps on Message**: `sent_at`, `delivered_at`, `read_at`,
`opened_at`, `clicked_at`, `failed_at`, and `attributed_at` enable time-to-open
analysis and delivery funnel charts without joining to a separate events table.

**Rich customer profiles**: `preferred_channel`, `preferred_day`,
`next_best_category`, `rfm_persona`, and `first_order_date` are computed from
order history and stored as denormalized columns for fast CDP-style profile reads.

**`created_by` on Segment**: distinguishes `human`, `ai`, and `journey`-created
segments.

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
CRM_BASE_URL=http://localhost:8000
PORT=8001
```

Streamlit Cloud:

```toml
CRM_BACKEND_URL = "https://xeno-crm-backend-uelp.onrender.com"
```

## Project structure
```text
xeno-crm-backend/
├── main.py                  # FastAPI app, startup auto-seed, /agent/chat, /demo/reset, /health
├── config.py                # Pydantic settings: DATABASE_URL, GROQ_API_KEY, CHANNEL_SERVICE_URL
├── database.py              # SQLAlchemy engine, SessionLocal, Base, get_db(), migration ALTERs
├── models.py                # 6 SQLAlchemy 2.0 models (Mapped[] style)
├── schemas.py               # Pydantic v2 schemas with computed delivery/attribution rates
├── seed_data.py             # 200 customers + orders across 4 RFM segments + profile backfill
├── streamlit_app.py         # Frontend: AI Agent, Analytics, Journeys (3 pages)
├── requirements.txt         # Backend + Streamlit dependencies
├── requirements_streamlit.txt # Streamlit Cloud subset (streamlit, plotly, requests)
├── render.yaml              # Render deployment config (free tier, Python 3.11.9)
├── runtime.txt              # Python version pin
├── routers/
│   ├── customers.py         # CRUD + /stats/overview + CDP profile + order attribution
│   ├── segments.py          # CRUD + execute_segment_filter() engine (13 filter keys)
│   ├── campaigns.py         # Create, launch, retry-delivery, performance, messages
│   ├── journeys.py          # 6 templates, create, trigger, pause/resume
│   └── receipts.py          # Async callback handler with idempotency + auto-complete
└── agent/
    ├── tools.py             # 6 LangGraph tools with db session injection
    ├── graph.py             # Hybrid deterministic + StateGraph, HITL gate, session store
    └── groq_utils.py        # ChatGroq builder, async/sync retry with exponential backoff

xeno-channel-service/
├── main.py                  # POST /send, POST /send-batch, /health, /status
└── simulator.py             # DeliverySimulator with per-channel profiles + attribution
```

## Smoke tests
```bash
curl https://xeno-crm-backend-uelp.onrender.com/health
curl https://xeno-crm-backend-uelp.onrender.com/customers/stats/overview
curl https://xeno-channel-service-c1yr.onrender.com/health
```

Expected:

- CRM health returns `{"status":"ok","service":"xeno-crm","checks":{...}}` with DB and channel service checks.
- Customer stats show 200 seeded customers and RFM counts.
- Channel health returns `{"status":"ok","service":"xeno-channel-service"}`.
- Streamlit sidebar shows customer, segment, and campaign counts.
- Full loop works: find → draft → approve → launch → Analytics updates live.
- Journeys: activate a template → trigger → campaign auto-launches → callbacks flow.

## What I would add with more time
1. **WebSocket for live dashboard**: replace polling with a WebSocket
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

6. **Journey evaluation scheduler**: replace manual "Run now" with a background
   scheduler that evaluates journey trigger rules on a configurable cadence
   (e.g., every 6 hours) and auto-launches campaigns without manual intervention.
