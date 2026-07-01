import logging
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from agent.graph import run_agent
from analytics.duckdb_client import analytics_connection
from backend.services.bootstrap import bootstrap_analytics_if_needed
from config import settings
from database import create_tables, get_db
from models import Customer
from routers.analytics import router as analytics_router
from routers.campaigns import router as campaigns_router
from routers.customers import router as customers_router
from routers.journeys import router as journeys_router
from routers.receipts import router as receipts_router
from routers.segments import router as segments_router
from schemas import ChatRequest, ChatResponse
from seed_data import run_seed


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Global Messaging Product Analytics & AI Insights Platform")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(customers_router, prefix="/customers", tags=["customers"])
app.include_router(segments_router, prefix="/segments", tags=["segments"])
app.include_router(campaigns_router, prefix="/campaigns", tags=["campaigns"])
app.include_router(journeys_router, prefix="/journeys", tags=["journeys"])
app.include_router(receipts_router, prefix="", tags=["receipts"])
app.include_router(analytics_router, prefix="/analytics", tags=["analytics"])


@app.get("/")
async def home() -> dict[str, str]:
    return {
        "message": "Global Messaging Product Analytics API is live. Use /docs for APIs and the Streamlit app for the analytics demo.",
        "service": "global-messaging-analytics",
        "health": "/health",
        "docs": "/docs",
        "app": "https://xeno-crm-backend-5eeqqhufg62kjv6zlsuhvz.streamlit.app",
    }


@app.on_event("startup")
async def startup_event():
    """Create tables, bootstrap analytics, and seed campaign simulation data if needed."""
    create_tables()
    bootstrap_analytics_if_needed()

    from database import SessionLocal
    from models import Customer, Order
    import seed_data

    db: Session = SessionLocal()
    try:
        customer_count = db.query(Customer).count()
        order_count = db.query(Order).count()
        if customer_count == 0:
            logger.info("Database empty - running seed...")
            seed_data.run_seed(db)
            customer_count = db.query(Customer).count()
            order_count = db.query(Order).count()
        else:
            seed_data.ensure_customer_profiles(db)
            db.commit()
        logger.info("Campaign simulation data ready. %s customers, %s orders.", customer_count, order_count)
    finally:
        db.close()


@app.get("/health")
async def health(db: Session = Depends(get_db)):
    """Full health check for API, operational database, analytics warehouse, and channel service."""
    import httpx

    checks = {
        "api": "ok",
        "database": "unknown",
        "analytics_warehouse": "unknown",
        "channel_service": "unknown",
    }

    try:
        count = db.query(Customer).count()
        checks["database"] = f"ok ({count} customers)"
    except Exception as exc:
        checks["database"] = f"error: {exc}"

    try:
        with analytics_connection(read_only=True) as connection:
            metric_rows = connection.sql(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'daily_product_metrics'"
            ).fetchone()[0]
            anomaly_rows = connection.sql(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'anomaly_alerts'"
            ).fetchone()[0]
        checks["analytics_warehouse"] = "ok" if metric_rows and anomaly_rows else "missing metric tables"
    except Exception as exc:
        checks["analytics_warehouse"] = f"error: {type(exc).__name__}"

    channel_url = settings.CHANNEL_SERVICE_URL.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{channel_url}/health")
            checks["channel_service"] = "ok" if response.status_code == 200 else f"http {response.status_code}"
    except Exception as exc:
        checks["channel_service"] = f"unreachable: {type(exc).__name__}"

    overall = "ok" if all(value.startswith("ok") for value in checks.values()) else "degraded"
    return {"status": overall, "service": "global-messaging-analytics", "checks": checks}


@app.get("/seed")
async def seed() -> dict[str, object]:
    run_seed()
    return {"ok": True, "message": "Database seeded"}


@app.post("/demo/reset")
async def demo_reset(db: Session = Depends(get_db)):
    """Reset transactional demo state while preserving customers and orders."""
    from models import Campaign, Journey, Message, Segment

    try:
        db.query(Message).delete()
        db.query(Campaign).delete()
        db.query(Segment).delete()
        db.query(Journey).delete()
        db.commit()
        return {
            "ok": True,
            "message": "Demo reset. Campaigns, messages, segments, and journeys cleared.",
            "customers_preserved": db.query(Customer).count(),
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Reset failed: {exc}") from exc


@app.post("/agent/chat", response_model=ChatResponse)
async def agent_chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    session_id = request.session_id if request.session_id is not None else str(uuid4())
    result = await run_agent(
        request.message,
        request.conversation_history,
        session_id,
        db,
    )
    return ChatResponse(**result)
