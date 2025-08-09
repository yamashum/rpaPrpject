import pytest
from workflow.log_db import init_db, log_run, get_success_rate, get_average_duration


def test_metrics_computation():
    conn = init_db(':memory:')
    log_run(conn, '1', 'flow', 0.0, 1.0, True)
    log_run(conn, '2', 'flow', 0.0, 2.0, False)
    log_run(conn, '3', 'flow', 0.0, 3.0, True)
    assert pytest.approx(get_success_rate(conn)) == 2 / 3
    assert pytest.approx(get_average_duration(conn)) == 2.0
