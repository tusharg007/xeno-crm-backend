"""Basic tests for analytics copilot tools."""

from ai.tools import run_sql_query


def test_run_sql_query_rejects_non_select():
    try:
        run_sql_query("DELETE FROM daily_product_metrics")
    except ValueError as exc:
        assert "Only SELECT statements are allowed." in str(exc)
    else:
        raise AssertionError("run_sql_query should reject non-SELECT statements")
