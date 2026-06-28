from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import aiohttp
import structlog

from grc_dashboard.config import Settings
from grc_dashboard.exceptions import (
    SIEMRateLimitException,
    SIEMSchemaValidationError,
    StaleMetricException,
)
from grc_dashboard.models.siem import SIEMEvent, SIEMQuery, SIEMQueryResult

logger = structlog.get_logger(__name__)

class SIEMClient(ABC):
    """
    Abstract SIEM client interface establishing standard pagination, rate limiting,
    and schema validation boundaries (ANCHOR:I4, ANCHOR:I7).
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = str(settings.siem.base_url).rstrip("/")
        self.api_key = settings.siem.api_key.get_secret_value()
        self.ttl_minutes = settings.siem.data_ttl_minutes

    async def execute_query(self, query: SIEMQuery) -> AsyncGenerator[SIEMQueryResult, None]:
        """Entrypoint for fetching results via pagination generator."""
        logger.info("siem_query_start", query_id=query.query_id)
        
        async for batch in self._paginate(query):
            validated_batch = self._validate_response_schema(batch)
            self._validate_freshness(validated_batch)
            yield validated_batch
            
        logger.info("siem_query_complete", query_id=query.query_id)

    @abstractmethod
    def _paginate(self, query: SIEMQuery) -> AsyncGenerator[dict[str, Any], None]:
        """Vendor-specific pagination implementation. Yields raw dict batches."""
        pass

    def _validate_response_schema(self, raw: dict[str, Any]) -> SIEMQueryResult:
        """
        Enforces ANCHOR:I4 Strict API Schema Validation Boundary.
        Parses raw dict into Pydantic models. Unmapped fields ignored;
        type mismatches raise SIEMSchemaValidationError.
        """
        try:
            if raw.get("query_hash") == "computed_in_model":
                events_raw = raw.get("events", [])
                events = [SIEMEvent.model_validate(e) for e in events_raw]
                
                q_ts_val = raw.get("query_timestamp")
                q_ts: Any = None
                if isinstance(q_ts_val, str):
                    q_ts = datetime.fromisoformat(q_ts_val.replace("Z", "+00:00"))
                elif isinstance(q_ts_val, datetime):
                    q_ts = q_ts_val
                else:
                    q_ts = datetime.now(UTC)
                
                f_ts_val = raw.get("response_freshness_utc")
                f_ts: Any = None
                if isinstance(f_ts_val, str):
                    f_ts = datetime.fromisoformat(f_ts_val.replace("Z", "+00:00"))
                elif isinstance(f_ts_val, datetime):
                    f_ts = f_ts_val
                else:
                    f_ts = datetime.now(UTC)
                
                return SIEMQueryResult.construct_with_hash(
                    query_id=raw["query_id"],
                    events=events,
                    total_count=raw["total_count"],
                    query_timestamp=q_ts,
                    response_freshness_utc=f_ts
                )
            return SIEMQueryResult.model_validate(raw)
        except Exception as e:
            logger.error("schema_validation_failed", error=str(e))
            # Mocking field path extraction for error context
            raise SIEMSchemaValidationError(
                message="SIEM response schema drift detected.",
                field_path="unknown",
                raw_value=str(raw)[:100]
            ) from e

    def _validate_freshness(self, result: SIEMQueryResult) -> None:
        """Enforces ANCHOR:I1 Data Freshness Validation."""
        now = datetime.now(UTC)
        age_delta = now - result.response_freshness_utc
        age_minutes = age_delta.total_seconds() / 60.0
        
        if age_minutes > self.ttl_minutes:
            raise StaleMetricException(
                message=f"SIEM data is stale. Age: {age_minutes:.1f}m > TTL: {self.ttl_minutes}m",
                age_minutes=age_minutes
            )

    def _apply_rate_limit(self, response: aiohttp.ClientResponse) -> None:
        """Examines headers for 429 semantics."""
        if response.status == 429:
            retry_after = int(response.headers.get("Retry-After", 10))
            raise SIEMRateLimitException(
                message="SIEM Rate Limit Exceeded",
                retry_after=retry_after
            )
