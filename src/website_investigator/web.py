from __future__ import annotations

from pathlib import Path

from .models import Observation
from .reports import render_index, render_observation
from .runtime import load_runtime_config
from .util import read_json


def create_app(runtime: Path):
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import HTMLResponse, JSONResponse
    except ImportError as exc:
        raise RuntimeError("Install website-investigator[web] to use the local web app") from exc

    runtime = runtime.resolve()
    app = FastAPI(title="Website Investigator", docs_url=None, redoc_url=None)

    def target_map():
        config = load_runtime_config(runtime)
        return {target.id: target for target in config.targets}

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        targets = target_map()
        items = []
        for target_id, target in targets.items():
            path = runtime / "data" / "current" / f"{target_id}.json"
            if not path.exists():
                continue
            observation = Observation.model_validate(read_json(path))
            items.append(
                {
                    "id": target_id,
                    "name": target.name,
                    "host": observation.host,
                    "status": observation.status,
                    "scan_mode": observation.scan_mode,
                    "completed_at": observation.completed_at,
                    "findings": len(observation.findings),
                }
            )
        items.sort(key=lambda item: item["name"].lower())
        return HTMLResponse(render_index(items))

    @app.get("/targets/{target_id}", response_class=HTMLResponse)
    def target_detail(target_id: str) -> HTMLResponse:
        targets = target_map()
        target = targets.get(target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Unknown target ID")
        path = runtime / "data" / "current" / f"{target_id}.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="No observation exists yet")
        observation = Observation.model_validate(read_json(path))
        return HTMLResponse(render_observation(observation, display_name=target.name))

    @app.get("/api/targets/{target_id}")
    def target_json(target_id: str) -> JSONResponse:
        targets = target_map()
        if target_id not in targets:
            raise HTTPException(status_code=404, detail="Unknown target ID")
        path = runtime / "data" / "current" / f"{target_id}.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="No observation exists yet")
        return JSONResponse(read_json(path))

    return app
