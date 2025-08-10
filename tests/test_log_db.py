from datetime import datetime, timezone

import pytest

from workflow.log_db import (
    get_average_duration,
    get_failure_counts,
    get_run_counts_by_period,
    get_selector_success_rates,
    get_success_rate,
    get_stats_by_flow,
    get_stats_by_period,
    init_db,
    log_run,
    log_selector_result,
)


def test_metrics_computation():
    conn = init_db(':memory:')
    log_run(conn, '1', 'flow', 0.0, 1.0, True, selector_hit_rate=1.0)
    log_run(
        conn,
        '2',
        'flow',
        0.0,
        2.0,
        False,
        failure_reason='err',
        selector_hit_rate=0.5,
    )
    log_run(conn, '3', 'flow', 0.0, 3.0, True, selector_hit_rate=0.75)
    assert pytest.approx(get_success_rate(conn)) == 2 / 3
    assert pytest.approx(get_average_duration(conn)) == 2.0
    cur = conn.execute(
        "SELECT failure_reason, selector_hit_rate FROM runs WHERE run_id='2'"
    )
    row = cur.fetchone()
    assert row == ('err', 0.5)


def test_selector_success_rates():
    conn = init_db(':memory:')
    log_selector_result(conn, 'btn', True)
    log_selector_result(conn, 'btn', False)
    log_selector_result(conn, 'input', True)
    rates = get_selector_success_rates(conn)
    assert rates['btn'] == 0.5
    assert rates['input'] == 1.0


def test_failure_counts_and_periods():
    conn = init_db(':memory:')
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t1 = base.timestamp()
    t2 = (base.replace(day=2)).timestamp()
    t3 = (base.replace(day=8)).timestamp()
    log_run(conn, '1', 'flow', t1, t1 + 1, True)
    log_run(conn, '2', 'flow', t2, t2 + 1, False, failure_reason='network')
    log_run(conn, '3', 'flow', t3, t3 + 1, False, failure_reason='timeout')
    counts = get_failure_counts(conn)
    assert counts['network'] == 1
    assert counts['timeout'] == 1
    day = dict(get_run_counts_by_period(conn, 'day'))
    assert day['2024-01-01'] == 1
    assert day['2024-01-02'] == 1
    assert day['2024-01-08'] == 1
    week = dict(get_run_counts_by_period(conn, 'week'))
    assert week
    month = dict(get_run_counts_by_period(conn, 'month'))
    assert month['2024-01'] == 3


def test_grouped_stats():
    conn = init_db(':memory:')
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    t1 = base.timestamp()
    t2 = (base.replace(day=2)).timestamp()
    log_run(conn, '1', 'flow1', t1, t1 + 1, True, selector_hit_rate=1.0)
    log_run(conn, '2', 'flow1', t1 + 10, t1 + 12, False, failure_reason='oops', selector_hit_rate=0.0)
    log_run(conn, '3', 'flow2', t2, t2 + 2, True, selector_hit_rate=0.5)
    by_flow = get_stats_by_flow(conn)
    assert pytest.approx(by_flow['flow1']['success_rate']) == 0.5
    assert by_flow['flow1']['failure_counts']['oops'] == 1
    by_day = get_stats_by_period(conn, 'day')
    assert pytest.approx(by_day['2024-01-01']['success_rate']) == 0.5
    assert by_day['2024-01-02']['run_count'] == 1
