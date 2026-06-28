"""AWS Config read-only compliance evidence collector."""
from __future__ import annotations

from typing import Any

from grc_dashboard.collectors.base import demo_mode_for_tenant, snapshot
from grc_dashboard.integrations.aws_auth import credentials_from_integration


async def collect_aws_evidence(
    tenant_id: str,
    metadata: dict[str, Any],
    secrets: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    region = metadata.get("region", "us-east-1")
    account_id = metadata.get("account_id", "unknown")

    if demo_mode_for_tenant(tenant_id):
        return [
            snapshot("aws", "config_rules_compliant", "pass", {
                "region": region,
                "account_id": account_id or "123456789012",
                "compliant_rules": 42,
                "non_compliant_rules": 3,
                "sample_rules": ["s3-bucket-public-read-prohibited", "iam-root-access-key-check"],
            }),
            snapshot("aws", "cloudtrail_enabled", "pass", {"trails": 2, "multi_region": True}),
            snapshot("aws", "guardduty_enabled", "pass", {"detectors": 1}),
            snapshot("aws", "mfa_root_account", "pass", {"root_mfa": True}),
        ]

    creds = credentials_from_integration(secrets or {}, metadata)
    if creds:
        try:
            import boto3  # type: ignore[import-untyped]

            session_kwargs: dict[str, str] = {
                "aws_access_key_id": creds["access_key"],
                "aws_secret_access_key": creds["secret_key"],
                "region_name": region,
            }
            if creds.get("session_token"):
                session_kwargs["aws_session_token"] = creds["session_token"]
            session = boto3.Session(**session_kwargs)
            sts = session.client("sts")
            identity = sts.get_caller_identity()
            config = session.client("config")
            rules = config.describe_config_rules()
            rule_count = len(rules.get("ConfigRules", []))
            return [
                snapshot("aws", "identity_verified", "pass", {
                    "account_id": identity.get("Account"),
                    "arn": identity.get("Arn"),
                    "live_pull": True,
                    "auth_method": metadata.get("auth_method", "iam_keys"),
                }),
                snapshot("aws", "config_rules", "pass", {
                    "region": region,
                    "config_rules_count": rule_count,
                    "live_pull": True,
                }),
            ]
        except ImportError:
            return [
                snapshot("aws", "boto3_required", "warn", {
                    "note": "Install boto3 for live AWS Config pulls: pip install boto3",
                }),
            ]
        except Exception as exc:
            return [
                snapshot("aws", "api_error", "fail", {"error": str(exc)[:200]}),
            ]

    access_key = (secrets or {}).get("access_key") or (secrets or {}).get("api_key")
    secret_key = (secrets or {}).get("secret_key") or (secrets or {}).get("secret")
    if access_key and secret_key:
        try:
            import boto3  # type: ignore[import-untyped]

            session = boto3.Session(
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
            )
            sts = session.client("sts")
            identity = sts.get_caller_identity()
            config = session.client("config")
            rules = config.describe_config_rules()
            rule_count = len(rules.get("ConfigRules", []))
            return [
                snapshot("aws", "identity_verified", "pass", {
                    "account_id": identity.get("Account"),
                    "arn": identity.get("Arn"),
                    "live_pull": True,
                }),
                snapshot("aws", "config_rules", "pass", {
                    "region": region,
                    "config_rules_count": rule_count,
                    "live_pull": True,
                }),
            ]
        except ImportError:
            return [
                snapshot("aws", "boto3_required", "warn", {
                    "note": "Install boto3 for live AWS Config pulls: pip install boto3",
                }),
            ]
        except Exception as exc:
            return [
                snapshot("aws", "api_error", "fail", {"error": str(exc)[:200]}),
            ]

    return [
        snapshot("aws", "connection_verified", "configured", {
            "region": region,
            "note": "Provide IAM access_key + secret_key for live Config API pulls",
        }),
    ]
