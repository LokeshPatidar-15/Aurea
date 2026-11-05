from sqlalchemy import select

from database import SessionLocal
from models.paper import PaperPosition
from services import paper_analytics
from services.paper_service import to_dict


def _closed() -> list:
    with SessionLocal() as session:
        rows = session.execute(select(PaperPosition).where(PaperPosition.status == "closed")).scalars().all()
        return [to_dict(r) for r in rows]


def performance() -> dict:
    return paper_analytics.performance(_closed())


def equity_curve(limit: int = 1000) -> list:
    points = paper_analytics.equity_curve(_closed())
    return points[-limit:]
