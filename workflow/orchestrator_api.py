from __future__ import annotations

"""HTTP API for interacting with the orchestrator."""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .orchestrator import orchestrator, Job

app = FastAPI(title="RPA Orchestrator")


class SubmitRequest(BaseModel):
    flow: str


class StatusUpdate(BaseModel):
    status: str
    result: str | None = None


@app.post("/jobs")
def submit_job(req: SubmitRequest) -> dict:
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
