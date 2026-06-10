# AGENTS.md

## What this project is
AI-native Mini CRM for retail brands. FastAPI backend with LangGraph agent.
Separate xeno-channel-service repo simulates message delivery via async callbacks.

## Stack
- Python 3.11, FastAPI 0.111.0, Pydantic v2, SQLAlchemy 2.0, LangGraph 0.0.69
- SQLite (file: xeno_crm.db), httpx for all async HTTP

## Code rules — never violate these
- SQLAlchemy: always Mapped[] + mapped_column() style. Never Column() legacy style.
- Pydantic: always @field_validator, never @validator. Always model_config not class Config.
- Async: all endpoints async def. All HTTP via httpx.AsyncClient. Never use requests library.
- IDs: all primary keys are str(uuid4()), never integer autoincrement.
- Errors: HTTPException with specific status codes. Never bare except.
- No print() anywhere. Use Python logging module.
- No hardcoded API keys. All config from environment via pydantic-settings.

## Folder structure — do not change this
main.py, database.py, models.py, schemas.py, config.py, seed_data.py
routers/: __init__.py, customers.py, segments.py, campaigns.py, receipts.py
agent/: __init__.py, graph.py, tools.py