from __future__ import annotations

import threading
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from flask import Flask, jsonify, render_template, request, send_from_directory

from pharma_agent.service import OUTPUT_DIR, list_reports, run_research_workflow

BASE_DIR = Path(__file__).resolve().parent
STAGE_ORDER = ["search", "research", "dedupe", "report", "complete"]
STAGE_LABELS = {
    "search": "Search Companies",
    "research": "Research Details",
    "dedupe": "Clean And Merge",
    "report": "Generate Word File",
    "complete": "Ready To Download",
}

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
jobs: dict[str, dict] = {}
job_lock = threading.Lock()


def build_stage_state() -> list[dict]:
    return [
        {"key": key, "label": STAGE_LABELS[key], "status": "pending", "message": "Waiting to start."}
        for key in STAGE_ORDER
    ]


def serialize_job(job: dict) -> dict:
    payload = deepcopy(job)
    return payload


def update_stage(job_id: str, stage_key: str, status: str, message: str) -> None:
    with job_lock:
        job = jobs[job_id]
        for stage in job["stages"]:
            if stage["key"] == stage_key:
                stage["status"] = status
                stage["message"] = message
                break
        job["current_stage"] = stage_key


def run_job(job_id: str, location: str, title: str, max_results: int, mode: str) -> None:
    try:
        result = run_research_workflow(
            query=location,
            title=title,
            max_results=max_results,
            mode=mode,
            progress_callback=lambda stage, status, message: update_stage(job_id, stage, status, message),
        )
        with job_lock:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["report"] = result
    except Exception as exc:
        with job_lock:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(exc)
            for stage in jobs[job_id]["stages"]:
                if stage["status"] == "active":
                    stage["status"] = "failed"
                    stage["message"] = str(exc)
                    break


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/reports")
def reports_api():
    return jsonify({"reports": list_reports()})


@app.post("/api/jobs")
def create_job():
    payload = request.get_json(silent=True) or {}
    location = (payload.get("location") or "Hyderabad").strip()
    title = (payload.get("title") or f"Pharmacy Companies In {location}").strip()
    max_results = int(payload.get("max_results") or 5)
    max_results = max(1, min(max_results, 25))
    mode = (payload.get("mode") or "sample").strip().lower()
    if mode not in {"sample", "live"}:
        return jsonify({"error": "Mode must be 'sample' or 'live'."}), 400

    job_id = uuid4().hex
    job = {
        "id": job_id,
        "status": "running",
        "location": location,
        "title": title,
        "mode": mode,
        "current_stage": "search",
        "stages": build_stage_state(),
        "report": None,
        "error": None,
    }
    with job_lock:
        jobs[job_id] = job

    worker = threading.Thread(target=run_job, args=(job_id, location, title, max_results, mode), daemon=True)
    worker.start()
    return jsonify(serialize_job(job)), 202


@app.get("/api/jobs/<job_id>")
def get_job(job_id: str):
    with job_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"error": "Job not found."}), 404
        return jsonify(serialize_job(job))


@app.get("/downloads/<path:filename>")
def download_report(filename: str):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
