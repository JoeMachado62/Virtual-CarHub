from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.marketcheck_history_enrichment_service import should_refresh_enrichment


def test_completed_history_enrichment_is_permanent_unless_forced() -> None:
    record = SimpleNamespace(
        status="completed",
        last_enriched_at=datetime.now(UTC) - timedelta(days=365),
        last_attempted_at=datetime.now(UTC) - timedelta(days=365),
    )

    assert should_refresh_enrichment(record) is False
    assert should_refresh_enrichment(record, force=True) is True


def test_failed_history_enrichment_still_retries_after_interval() -> None:
    record = SimpleNamespace(
        status="failed",
        last_enriched_at=None,
        last_attempted_at=datetime.now(UTC) - timedelta(days=2),
    )

    assert should_refresh_enrichment(record) is True
