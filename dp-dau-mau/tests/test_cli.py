import json
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from cli import dpdau
from service.app import create_app


def _patch_httpx(monkeypatch, app) -> None:
    def client_factory(base_url: str, **kwargs) -> httpx.Client:
        transport = httpx.ASGITransport(app=app)
        return httpx.Client(
            transport=transport,
            base_url=base_url,
            headers=kwargs.get("headers"),
            timeout=kwargs.get("timeout"),
        )

    monkeypatch.setattr(dpdau, "httpx", SimpleNamespace(Client=client_factory))


def test_cli_generate_ingest_and_query(tmp_path: Path, monkeypatch) -> None:
    app = create_app()
    _patch_httpx(monkeypatch, app)
    runner = CliRunner()

    data_dir = Path(os.environ["DATA_DIR"])
    dataset = data_dir / "streams" / "synthetic_cli.jsonl"
    result = runner.invoke(
        dpdau.app,
        [
            "generate-synthetic",
            "--days",
            "7",
            "--users",
            "5",
            "--p-active",
            "0.6",
            "--seed",
            "1",
            "--start",
            "2025-10-01",
            "--out",
            str(dataset),
        ],
    )
    assert result.exit_code == 0

    result = runner.invoke(
        dpdau.app,
        [
            "ingest",
            "--from",
            str(dataset),
            "--format",
            "jsonl",
            "--host",
            "http://testserver",
            "--api-key",
            "test-key",
        ],
    )
    assert result.exit_code == 0

    result = runner.invoke(
        dpdau.app,
        [
            "mau",
            "--end",
            "2025-10-07",
            "--host",
            "http://testserver",
            "--api-key",
            "test-key",
        ],
    )
    assert result.exit_code == 0
    response = json.loads(result.stdout)
    assert "estimate" in response

    client = TestClient(app)
    resp = client.get("/budget/dau?day=2025-10-07", headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200
