import logging
from uuid import uuid4

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from agent.graph import run_agent
from database import create_tables, get_db
from models import Campaign, Customer, Message, Segment
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
async def startup() -> None:
    create_tables()
    db = next(get_db())
    try:
        customer_count = db.scalar(select(func.count()).select_from(Customer)) or 0
        if customer_count == 0:
            run_seed()
            customer_count = db.scalar(select(func.count()).select_from(Customer)) or 0
        logger.info("Xeno CRM ready. %s customers in database.", customer_count)
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
async def reset_demo(db: Session = Depends(get_db)) -> dict[str, object]:
    db.execute(delete(Message))
    db.execute(delete(Campaign))
    db.execute(delete(Segment))
    db.commit()
    run_seed()
    return {"ok": True, "message": "Demo reset complete"}


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
