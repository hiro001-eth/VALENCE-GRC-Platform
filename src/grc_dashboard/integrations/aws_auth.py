"""AWS cross-account IAM role authentication for live collectors."""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def assume_role_credentials(
    role_arn: str,
    external_id: str,
    region: str = "us-east-1",
    session_name: str = "valence-grc",
) -> dict[str, str] | None:
    """Assume a customer IAM role and return temporary AWS credentials."""
    try:
        import boto3  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("boto3_not_installed")
        return None

    try:
        sts = boto3.client("sts", region_name=region)
        resp = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name[:64],
            ExternalId=external_id,
        )
        creds = resp["Credentials"]
        return {
            "access_key": creds["AccessKeyId"],
            "secret_key": creds["SecretAccessKey"],
            "session_token": creds["SessionToken"],
            "expires_at": creds["Expiration"].isoformat(),
        }
    except Exception as exc:
        logger.warning("aws_assume_role_failed", role_arn=role_arn, error=str(exc))
        return None


def credentials_from_integration(secrets: dict[str, Any], metadata: dict[str, Any]) -> dict[str, str] | None:
    """Resolve AWS credentials from OAuth secrets or cross-account role metadata."""
    if secrets.get("access_key") and secrets.get("secret_key"):
        out: dict[str, str] = {
            "access_key": str(secrets["access_key"]),
            "secret_key": str(secrets["secret_key"]),
        }
        if secrets.get("session_token"):
            out["session_token"] = str(secrets["session_token"])
        return out

    role_arn = metadata.get("role_arn") or secrets.get("role_arn")
    external_id = metadata.get("external_id") or secrets.get("external_id")
    if role_arn and external_id:
        region = metadata.get("region", "us-east-1")
        return assume_role_credentials(str(role_arn), str(external_id), str(region))
    return None
