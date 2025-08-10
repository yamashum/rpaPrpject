import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # type: ignore
from workflow.orchestrator_api import app  # type: ignore
from workflow.log_db import init_db, log_run


def test_stats_endpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    conn = init_db('runs.sqlite')
    log_run(conn, '1', 'flow', 0.0, 1.0, True, selector_hit_rate=1.0)
    client = TestClient(app)
    resp = client.get('/stats')
    assert resp.status_code == 200
    data = resp.json()
    assert data['by_flow']['flow']['run_count'] == 1
    resp_html = client.get('/stats?format=html')
    assert resp_html.status_code == 200
    assert '<html>' in resp_html.text.lower()
