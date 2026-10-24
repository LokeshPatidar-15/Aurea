from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Feature(Base):
    __tablename__ = "features"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    timeframe: Mapped[str] = mapped_column(String(5), primary_key=True)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)

    ret_1: Mapped[float | None] = mapped_column(Float)
    ret_4: Mapped[float | None] = mapped_column(Float)
    ret_24: Mapped[float | None] = mapped_column(Float)
    rsi_14: Mapped[float | None] = mapped_column(Float)
    macd_hist: Mapped[float | None] = mapped_column(Float)
    bb_pct_b: Mapped[float | None] = mapped_column(Float)
    bb_width: Mapped[float | None] = mapped_column(Float)
    ema_20_dist: Mapped[float | None] = mapped_column(Float)
    atr_14_pct: Mapped[float | None] = mapped_column(Float)
    vol_z: Mapped[float | None] = mapped_column(Float)
    hour_utc: Mapped[int] = mapped_column(SmallInteger)
    day_of_week: Mapped[int] = mapped_column(SmallInteger)
    dist_swing_high_atr: Mapped[float | None] = mapped_column(Float)
    dist_swing_low_atr: Mapped[float | None] = mapped_column(Float)
    sweep_bull: Mapped[bool] = mapped_column(Boolean)
    sweep_bear: Mapped[bool] = mapped_column(Boolean)
    dist_poc_atr: Mapped[float | None] = mapped_column(Float)
    in_value_area: Mapped[bool] = mapped_column(Boolean)
    is_filled: Mapped[bool] = mapped_column(Boolean)
    is_outlier: Mapped[bool] = mapped_column(Boolean)
