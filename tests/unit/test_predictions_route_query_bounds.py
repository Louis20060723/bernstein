"""GET /metrics/predictions rejects non-finite query values at the boundary.

``budget_cap`` is a USD ceiling. ``ge=0.0`` alone admits ``+Infinity``
(``inf >= 0.0`` is true), and the handler echoes the value back into a
``JSONResponse``. Starlette renders with ``json.dumps(..., allow_nan=False)``,
so the echo raised ``ValueError: Out of range float values are not JSON
compliant: inf`` and the request came back as an unhandled 500.

A budget ceiling of infinity is not a USD amount, so the fix belongs at the
parameter boundary rather than in the render step: reject the value with a
422 before the handler runs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from bernstein.core.server import create_app


@pytest.fixture()
def app(tmp_path: Path) -> FastAPI:
    return create_app(jsonl_path=tmp_path / "tasks.jsonl")


@pytest.fixture()
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.anyio()
@pytest.mark.parametrize("value", ["Infinity", "-Infinity", "NaN", "inf", "-inf", "nan"])
async def test_non_finite_budget_cap_is_refused_not_crashed(client: AsyncClient, value: str) -> None:
    """Every non-finite spelling is a 422, and none of them reaches the renderer."""
    resp = await client.get(f"/metrics/predictions?budget_cap={value}")
    assert resp.status_code == 422, f"budget_cap={value} should be refused as unprocessable, got {resp.status_code}"


@pytest.mark.anyio()
async def test_non_finite_window_hours_is_refused_not_crashed(client: AsyncClient) -> None:
    """The same holds for ``window_hours``, whose ``le`` bound already excluded it."""
    resp = await client.get("/metrics/predictions?window_hours=Infinity")
    assert resp.status_code == 422


@pytest.mark.anyio()
@pytest.mark.parametrize("value", ["0", "0.0", "5.0", "1e9"])
async def test_finite_budget_cap_still_answers(client: AsyncClient, value: str) -> None:
    """The refusal is scoped to non-finite values; ordinary caps are unaffected."""
    resp = await client.get(f"/metrics/predictions?budget_cap={value}")
    assert resp.status_code == 200
    assert resp.json()["budget_cap_usd"] == float(value)
