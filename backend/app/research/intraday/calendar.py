from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.research.intraday.config import (
    ASIA_KOLKATA_NAME,
    EXPECTED_FIVE_MINUTE_BARS,
    NORMAL_SESSION_END,
    NORMAL_SESSION_START,
    SESSION_VERSION,
)

ASIA_KOLKATA = ZoneInfo(ASIA_KOLKATA_NAME)


@dataclass(frozen=True, slots=True)
class TradingSession:
    trading_date: date
    opens_at: datetime
    closes_at: datetime
    session_type: str = "REGULAR"
    source: str = "EXPLICIT_SESSION_UNIVERSE"
    version: str = SESSION_VERSION

    def expected_starts(self, interval_minutes: int = 5) -> tuple[datetime, ...]:
        cursor = self.opens_at
        values: list[datetime] = []
        while cursor < self.closes_at:
            values.append(cursor)
            cursor += timedelta(minutes=interval_minutes)
        return tuple(values)


@dataclass(slots=True)
class NseCashSessionCalendar:
    sessions: dict[date, TradingSession] = field(default_factory=dict)
    version: str = SESSION_VERSION

    @classmethod
    def from_trading_dates(
        cls,
        trading_dates: list[date] | tuple[date, ...],
        *,
        source: str = "PROJECT_DAILY_SESSION_UNIVERSE",
    ) -> "NseCashSessionCalendar":
        sessions = {}
        for value in trading_dates:
            opens_at = datetime.combine(value, NORMAL_SESSION_START, tzinfo=ASIA_KOLKATA)
            closes_at = datetime.combine(value, NORMAL_SESSION_END, tzinfo=ASIA_KOLKATA)
            sessions[value] = TradingSession(value, opens_at, closes_at, source=source)
        return cls(sessions=sessions)

    def add_special_session(
        self,
        trading_date: date,
        *,
        opens_at: datetime,
        closes_at: datetime,
        session_type: str,
        source: str,
    ) -> None:
        if opens_at.tzinfo is None or closes_at.tzinfo is None:
            raise ValueError("Special session timestamps must be timezone-aware")
        if not source.strip():
            raise ValueError("Special sessions require an auditable source")
        self.sessions[trading_date] = TradingSession(
            trading_date,
            opens_at.astimezone(ASIA_KOLKATA),
            closes_at.astimezone(ASIA_KOLKATA),
            session_type=session_type,
            source=source,
        )

    def session_for(self, trading_date: date) -> TradingSession:
        try:
            return self.sessions[trading_date]
        except KeyError as exc:
            raise KeyError(
                f"No sourced NSE session registered for {trading_date}; weekday inference is prohibited"
            ) from exc

    def is_session(self, trading_date: date) -> bool:
        return trading_date in self.sessions

    def expected_bar_count(self, trading_date: date, interval_minutes: int = 5) -> int:
        count = len(self.session_for(trading_date).expected_starts(interval_minutes))
        if interval_minutes == 5 and self.session_for(trading_date).session_type == "REGULAR":
            if count != EXPECTED_FIVE_MINUTE_BARS:
                raise ValueError("Regular NSE session must resolve to exactly 75 five-minute bars")
        return count
