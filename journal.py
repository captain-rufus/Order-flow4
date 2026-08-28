"""Journal endpoints -- manual entries plus everything auto-logged by the scheduler."""
from __future__ import annotations
from fastapi import APIRouter
from pydantic import BaseModel
import uuid

from app.persistence import add_journal_entry, close_journal_entry, get_journal, get_open_trades

router = APIRouter(prefix="/journal", tags=["journal"])


class JournalEntryIn(BaseModel):
    pair: str
    market: str
    direction: str
    strategy: str
    entry: float
    stop: float
    target: float | None = None
    notes: str = ""


@router.get("")
async def list_journal(limit: int = 200):
    return {"entries": await get_journal(limit)}


@router.get("/open")
async def list_open_trades():
    return {"entries": await get_open_trades()}


@router.post("")
async def create_entry(entry: JournalEntryIn):
    entry_id = str(uuid.uuid4())
    await add_journal_entry({
        "id": entry_id, "pair": entry.pair, "market": entry.market, "direction": entry.direction,
        "strategy": entry.strategy, "entry": entry.entry, "stop": entry.stop, "target": entry.target,
        "notes": entry.notes, "auto_traded": 0, "broker_position_id": None,
    })
    return {"id": entry_id}


@router.post("/{entry_id}/close")
async def close_entry(entry_id: str, outcome: str, r_multiple: float | None = None):
    await close_journal_entry(entry_id, outcome, r_multiple)
    return {"closed": True}
