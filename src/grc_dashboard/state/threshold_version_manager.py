import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Generator, Optional

try:
    import fcntl
except ImportError:
    fcntl = None  # type: ignore

try:
    import msvcrt
except ImportError:
    msvcrt = None  # type: ignore

import structlog
from pydantic import BaseModel, ConfigDict

from grc_dashboard.exceptions import ConfigCorruptException

logger = structlog.get_logger(__name__)

class ThresholdState(BaseModel):
    active_threshold_hash: str
    previous_threshold_hash: Optional[str]
    activated_at: datetime
    activated_by: str

    model_config = ConfigDict(frozen=True)

class ThresholdVersionManager:
    """
    Atomic tracking of active threshold configuration hashes (ANCHOR:I3 proof layer L3).
    Enables guaranteed rollback to previous known-good config.
    """
    def __init__(self, state_path: Path):
        self.state_path = state_path
        self.lock_path = state_path.with_suffix(".lock")
        self._ensure_state_exists()

    def load(self) -> ThresholdState:
        with self._acquire_lock():
            return self._load_unlocked()

    def _load_unlocked(self) -> ThresholdState:
        try:
            with open(self.state_path, "r") as f:
                data = json.load(f)
            return ThresholdState.model_validate(data)
        except Exception as e:
            raise ConfigCorruptException(
                message=f"Threshold state file corrupt: {e}",
                correlation_id="none",
                stage_name="StateManagement",
                dashboard_run_id="none"
            ) from e

    def activate(self, threshold_hash: str, user: str) -> None:
        with self._acquire_lock():
            self._activate_unlocked(threshold_hash, user)

    def _activate_unlocked(self, threshold_hash: str, user: str) -> None:
        current_state = self._read_raw()
        
        new_state = {
            "active_threshold_hash": threshold_hash,
            "previous_threshold_hash": current_state.get("active_threshold_hash") if current_state else None,
            "activated_at": datetime.now(UTC).isoformat(),
            "activated_by": user
        }
        
        with open(self.state_path, "w") as f:
            json.dump(new_state, f)
            
        logger.info("threshold_version_activated", 
                    new_hash=threshold_hash, 
                    prev_hash=new_state["previous_threshold_hash"], 
                    user=user)

    def rollback(self) -> ThresholdState:
        with self._acquire_lock():
            state = self._load_unlocked()
            if not state.previous_threshold_hash:
                raise ValueError("No previous threshold hash available for rollback.")
                
            logger.warning("initiating_threshold_rollback", 
                           from_hash=state.active_threshold_hash, 
                           to_hash=state.previous_threshold_hash)
                           
            self._activate_unlocked(state.previous_threshold_hash, "system_rollback")
            return self._load_unlocked()

    @contextlib.contextmanager
    def _acquire_lock(self) -> Generator[None, None, None]:
        """Cross-process file lock supporting fcntl (Unix) and msvcrt (Windows)."""
        self.lock_path.touch(exist_ok=True)
        # Open in read/write binary mode for locking compatibility
        f = open(self.lock_path, "rb+")
        try:
            if fcntl:
                fcntl.flock(f, fcntl.LOCK_EX)  # type: ignore[attr-defined]
            elif msvcrt:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
            yield
        finally:
            try:
                if fcntl:
                    fcntl.flock(f, fcntl.LOCK_UN)  # type: ignore[attr-defined]
                elif msvcrt:
                    f.seek(0)
                    msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
            except Exception:
                pass
            f.close()

    def _ensure_state_exists(self) -> None:
        if not self.state_path.exists():
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            with self._acquire_lock():
                with open(self.state_path, "w") as f:
                    json.dump({
                        "active_threshold_hash": "initial_empty_hash",
                        "previous_threshold_hash": None,
                        "activated_at": datetime.now(UTC).isoformat(),
                        "activated_by": "system_init"
                    }, f)

    def _read_raw(self) -> dict[str, Any]:
        try:
            with open(self.state_path, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
                return {}
        except Exception:
            return {}
