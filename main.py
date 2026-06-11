import logging
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from agent.graph import run_agent
from database import create_tables, get_db
from models import Customer
from routers.campaigns import router as campaigns_router
from routers.customers import router as customers_router
from routers.receipts import router as receipts_router
from routers.segments import router as segments_router
from schemas import ChatRequest, ChatResponse
from seed_data import run_seed


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Xeno Mini CRM")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(customers_router, prefix="/customers", tags=["customers"])
app.include_router(segments_router, prefix="/segments", tags=["segments"])
app.include_router(campaigns_router, prefix="/campaigns", tags=["campaigns"])
app.include_router(receipts_router, prefix="", tags=["receipts"])


@app.on_event("startup")
async def startup_event():
    """Create tables and auto-seed if database is empty.

    Render's free tier has an ephemeral filesystem - the SQLite file is lost
    on every restart. This startup hook ensures the demo always has data.
    """
    create_tables()
    from sqlalchemy.orm import Session
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
        logger.info(f"Xeno CRM ready. {customer_count} customers, {order_count} orders.")
    finally:
        db.close()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "xeno-crm"}


@app.get("/seed")
async def seed() -> dict[str, object]:
    run_seed()
    return {"ok": True, "message": "Database seeded"}


@app.post("/demo/reset")
async def demo_reset(db: Session = Depends(get_db)):
    """Reset demo state: clear campaigns/messages/segments, keep customers and orders.

    Preserves the customer and order data so the RFM segments remain valid.
    Clears only transactional data (campaigns, messages, segments) so the
    evaluator can run multiple demo flows without stale data cluttering the UI.
    """
    from models import Message, Campaign, Segment
    try:
        db.query(Message).delete()
        db.query(Campaign).delete()
        db.query(Segment).delete()
        db.commit()
        return {
            "ok": True,
            "message": "Demo reset. Campaigns, messages, and segments cleared.",
            "customers_preserved": db.query(Customer).count()
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")


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
