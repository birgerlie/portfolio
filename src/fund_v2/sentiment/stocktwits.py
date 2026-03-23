"""StockTwits sentiment source — converts API responses to SourceRecords."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from silicondb.sources.models import SourceRecord


class StockTwitsSentiment:
    """Converts StockTwits sentiment API responses to SourceRecords."""

    def parse_sentiment(self, response: dict[str, Any]) -> SourceRecord:
        symbol_data = response.get("symbol", {})
        symbol = symbol_data.get("symbol", "") if isinstance(symbol_data, dict) else str(symbol_data)
        sentiment = response.get("sentiment", {})
        bullish = int(sentiment.get("bullish", 0))
        bearish = int(sentiment.get("bearish", 0))
        total = bullish + bearish
        bull_ratio = bullish / total if total > 0 else 0.5

        return SourceRecord(
            source_name="stocktwits",
            collection="sentiment",
            identity=symbol,
            data={
                "symbol": symbol,
                "bull_ratio": bull_ratio,
                "bullish": bullish,
                "bearish": bearish,
                "total_messages": total,
            },
            timestamp=datetime.now(timezone.utc),
            idempotency_key=hashlib.md5(
                f"stocktwits:{symbol}:{datetime.now(timezone.utc).isoformat()[:13]}".encode()
            ).hexdigest(),
            tenant_id=0,
        )
