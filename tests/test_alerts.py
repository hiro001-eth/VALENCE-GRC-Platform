from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from grc_dashboard.alerting.alert_engine import AlertEngine
from grc_dashboard.db.models import AlertRecord
from grc_dashboard.db.session import AsyncSessionLocal, init_db


@pytest.fixture(scope="module", autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_alert_engine_creates_records():
    # Setup alert engine with mocked network calls
    engine = AlertEngine()
    engine.slack.send_alert = AsyncMock(return_value=True)
    engine.teams.send_alert = AsyncMock(return_value=True)
    engine.email.send_alert = AsyncMock(return_value=False)  # SMTP unconfigured

    test_metrics = [
        {
            "metric_id": "KRI-MTTR-001",
            "metric_name": "Mean Time to Respond",
            "rag_status": "Red",
            "narrative": "MTTR exceeds critical threshold.",
        },
        {
            "metric_id": "KRI-MTTD-001",
            "metric_name": "Mean Time to Detect",
            "rag_status": "Amber",
            "narrative": "MTTD is high.",
        },
        {
            "metric_id": "KPI-FPR-001",
            "metric_name": "False Positive Rate",
            "rag_status": "Green",  # Green should NOT trigger alerts
            "narrative": "FPR is healthy.",
        }
    ]

    run_id = "TEST_RUN_999"

    # Process metrics
    await engine.process_metrics(run_id, test_metrics)

    # Verify database entries
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AlertRecord).where(AlertRecord.run_id == run_id)
        )
        alerts = result.scalars().all()
        assert len(alerts) == 2

        # Check fields
        alert_map = {a.metric_id: a for a in alerts}
        assert "KRI-MTTR-001" in alert_map
        assert "KRI-MTTD-001" in alert_map
        assert "KPI-FPR-001" not in alert_map

        assert alert_map["KRI-MTTR-001"].rag_status == "Red"
        assert alert_map["KRI-MTTR-001"].severity == "critical"
        assert alert_map["KRI-MTTR-001"].channels_notified == ["slack", "teams"]

        assert alert_map["KRI-MTTD-001"].rag_status == "Amber"
        assert alert_map["KRI-MTTD-001"].severity == "high"


@pytest.mark.asyncio
async def test_alert_engine_no_duplicates():
    engine = AlertEngine()
    engine.slack.send_alert = AsyncMock(return_value=True)
    engine.teams.send_alert = AsyncMock(return_value=True)
    engine.email.send_alert = AsyncMock(return_value=True)

    test_metrics = [
        {
            "metric_id": "KRI-MTTR-001",
            "metric_name": "Mean Time to Respond",
            "rag_status": "Red",
            "narrative": "MTTR exceeds critical threshold.",
        }
    ]

    run_id = "TEST_RUN_DUP_888"

    # Process once
    await engine.process_metrics(run_id, test_metrics)

    # Process twice
    await engine.process_metrics(run_id, test_metrics)

    # Check alert count
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AlertRecord).where(AlertRecord.run_id == run_id)
        )
        alerts = result.scalars().all()
        # Should be 1, not 2
        assert len(alerts) == 1
