from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, SmallInteger, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class SignalLog(Base):
    __tablename__ = "signal_log"
    __table_args__ = (UniqueConstraint("symbol", "timeframe", "kind", "candle_time", name="uq_signal_log_candle"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), index=True)
    timeframe: Mapped[str] = mapped_column(String(5))
    kind: Mapped[str] = mapped_column(String(10))
    candle_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    direction: Mapped[int] = mapped_column(SmallInteger)
    signal: Mapped[str] = mapped_column(String(10))
    status: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[float | None] = mapped_column(Float)
    reference_price: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="pipeline")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
