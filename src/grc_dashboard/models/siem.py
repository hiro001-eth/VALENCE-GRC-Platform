import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class SIEMEvent(BaseModel):
    event_id: str
    timestamp: datetime
    event_type: str
    severity: str
    raw_fields: dict[str, Any]

    model_config = ConfigDict(frozen=True)

class SIEMQuery(BaseModel):
    query_id: str
    raw_query: str
    
    model_config = ConfigDict(frozen=True)

class SIEMQueryResult(BaseModel):
    query_id: str
    query_hash: str
    events: list[SIEMEvent]
    total_count: int
    query_timestamp: datetime
    response_freshness_utc: datetime

    model_config = ConfigDict(frozen=True)

    @classmethod
    def construct_with_hash(cls, query_id: str, events: list[SIEMEvent], total_count: int, query_timestamp: datetime, response_freshness_utc: datetime) -> "SIEMQueryResult":
        # Compute canonical hash from core fields to satisfy ANCHOR:I2
        canonical_dict = {
            "query_id": query_id,
            "total_count": total_count,
            "query_timestamp": query_timestamp.isoformat(),
            "response_freshness_utc": response_freshness_utc.isoformat()
        }
        canonical_json = json.dumps(canonical_dict, sort_keys=True).encode("utf-8")
        computed_hash = hashlib.sha256(canonical_json).hexdigest()
        
        return cls(
            query_id=query_id,
            query_hash=computed_hash,
            events=events,
            total_count=total_count,
            query_timestamp=query_timestamp,
            response_freshness_utc=response_freshness_utc
        )
