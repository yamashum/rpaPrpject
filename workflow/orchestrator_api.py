from __future__ import annotations

"""HTTP API for interacting with the orchestrator."""

import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from .orchestrator import orchestrator, Job
from .flow import Flow
from .runner import Runner
from .log_db import (
    init_db,
    get_success_rate,
    get_average_duration,
    get_failure_counts,
    get_selector_success_rates,
    get_stats_by_period,
    get_stats_by_flow,
)

app = FastAPI(title="RPA Orchestrator")


class SubmitRequest(BaseModel):
    flow: str


class StatusUpdate(BaseModel):
    status: str
    result: str | None = None


@app.post("/jobs")
def submit_job(req: SubmitRequest) -> dict:
    flow_path = Path(req.flow)
    data = json.loads(flow_path.read_text())
    flow = Flow.from_dict(data)
    Runner().view_flow(flow)
    job = orchestrator.submit(req.flow)
    return {"id": job.id}


@app.get("/jobs/assign/{host}")
def assign_job(host: str) -> dict:
    job = orchestrator.assign_job(host)
    if not job:
        return {"id": None}
    return {"id": job.id, "flow": job.flow}


@app.post("/jobs/{job_id}/status")
def update_status(job_id: str, upd: StatusUpdate) -> dict:
    if job_id not in orchestrator.jobs:
        raise HTTPException(status_code=404, detail="job not found")
    orchestrator.update_status(job_id, upd.status, result=upd.result)
    return {"ok": True}


@app.post("/jobs/{job_id}/stop")
def stop_job(job_id: str) -> dict:
    orchestrator.stop(job_id)
    return {"ok": True}


@app.post("/jobs/{job_id}/rerun")
def rerun_job(job_id: str) -> dict:
    job = orchestrator.rerun(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return {"id": job.id}


@app.get("/state")
def state() -> dict:
    return orchestrator.get_state()


@app.get("/stats")
def stats(format: str = "json"):
    conn = init_db("runs.sqlite")
    data = {
        "success_rate": get_success_rate(conn),
        "average_duration": get_average_duration(conn),
        "failure_counts": get_failure_counts(conn),
        "selector_success_rates": get_selector_success_rates(conn),
        "by_day": get_stats_by_period(conn, "day"),
        "by_week": get_stats_by_period(conn, "week"),
        "by_month": get_stats_by_period(conn, "month"),
        "by_flow": get_stats_by_flow(conn),
    }
    if format == "html":
        return HTMLResponse(
            content=f"<html><body><pre>{json.dumps(data, indent=2)}</pre></body></html>"
        )
    return JSONResponse(content=data)


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    """Simple HTML dashboard showing job and queue status."""
    rows = []
    for jid, info in orchestrator.get_state().items():
        rows.append(
            f"<tr><td>{jid}</td><td>{info['flow']}</td><td>{info['host']}</td>"
            f"<td>{info['status']}</td><td>{info['started']}</td>"
            f"<td>{info['finished']}</td><td>{info['result']}</td></tr>"
        )
    table = "".join(rows) or "<tr><td colspan='7'>No jobs</td></tr>"
    return (
        "<html><head><title>Orchestrator</title></head><body><h1>Job Status"  # noqa: E501
        "</h1><table border='1'><tr><th>ID</th><th>Flow</th><th>Host"  # noqa: E501
        "</th><th>Status</th><th>Started</th><th>Finished</th>"  # noqa: E501
        "<th>Result</th></tr>" + table + "</table></body></html>"
    )
