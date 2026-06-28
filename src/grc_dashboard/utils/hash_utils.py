import hashlib
import json
from pathlib import Path

from pydantic import BaseModel


def sha256_bytes(data: bytes) -> str:
    """Computes SHA-256 hash of raw bytes."""
    return hashlib.sha256(data).hexdigest()

def sha256_model(model: BaseModel) -> str:
    """
    Computes a deterministic SHA-256 hash of a Pydantic model.
    Serializes to canonical JSON (sorted keys) before hashing.
    """
    # model_dump_json serializes datetimes appropriately
    canonical_json = model.model_dump_json(warnings=False, exclude_none=True)
    # Load and re-dump to ensure strict key sorting
    parsed = json.loads(canonical_json)
    sorted_json = json.dumps(parsed, sort_keys=True, separators=(',', ':')).encode("utf-8")
    return sha256_bytes(sorted_json)

def sha256_file(path: Path) -> str:
    """Computes SHA-256 hash of a file in chunks to bound memory."""
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
