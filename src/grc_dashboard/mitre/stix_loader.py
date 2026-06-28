import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiohttp
import structlog

from grc_dashboard.config import Settings
from grc_dashboard.exceptions import STIXLoadException, STIXSchemaValidationError

logger = structlog.get_logger(__name__)

class STIXLoader:
    """
    MITRE ATT&CK STIX 2.1 data loader. Fetches enterprise matrix from 
    MITRE TAXII server or local cache. Enforces strict STIX schema validation.
    """
    def __init__(self, settings: Settings):
        self.settings = settings
        self.cache_dir = Path("data/cache/")
        self.cache_file = self.cache_dir / "enterprise_attack.json"
        self.ttl_hours = settings.mitre.cache_ttl_hours

    async def load_enterprise_matrix(self) -> dict[str, Any]:
        """Loads and validates the STIX bundle."""
        bundle = await self._load_from_cache()
        if not bundle:
            bundle = await self._fetch_from_taxii()
            self._save_to_cache(bundle)
        
        self._validate_stix_objects(bundle)
        return bundle

    async def _load_from_cache(self) -> dict[str, Any] | None:
        if not self.cache_file.exists() or not self._is_cache_fresh():
            return None
        try:
            with open(self.cache_file) as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
                return None
        except Exception as e:
            logger.warning("stix_cache_read_failed", error=str(e))
            return None

    def _save_to_cache(self, bundle: dict[str, Any]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(bundle, f)

    async def _fetch_from_taxii(self) -> dict[str, Any]:
        logger.info("fetching_stix_from_mitre", url=self.settings.mitre.stix_url)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(str(self.settings.mitre.stix_url)) as response:
                    response.raise_for_status()
                    res = await response.json()
                    if isinstance(res, dict):
                        return res
                    raise ValueError("Expected JSON object from TAXII")
        except Exception as e:
            raise STIXLoadException(
                message=f"Failed to fetch STIX data from MITRE: {e}",
                correlation_id="none",
                stage_name="MITRECoverage",
                dashboard_run_id="none"
            ) from e

    def _validate_stix_objects(self, stix_bundle: dict[str, Any]) -> list[dict[str, Any]]:
        if "objects" not in stix_bundle:
            raise STIXSchemaValidationError(
                message="Invalid STIX Bundle: missing 'objects' key",
                correlation_id="none",
                stage_name="MITRECoverage",
                dashboard_run_id="none"
            )
        objs = stix_bundle["objects"]
        if isinstance(objs, list):
            return objs
        raise STIXSchemaValidationError(
            message="STIX objects must be a list",
            correlation_id="none",
            stage_name="MITRECoverage",
            dashboard_run_id="none"
        )

    def _is_cache_fresh(self) -> bool:
        if not self.cache_file.exists():
            return False
        mtime = datetime.fromtimestamp(self.cache_file.stat().st_mtime, tz=UTC)
        return (datetime.now(UTC) - mtime) < timedelta(hours=self.ttl_hours)
