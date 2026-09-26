"""Inventory API and user isolation against real PostgreSQL (SYNTHETIC users and records)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from recallgraph.inventory import service as inventory_service
from recallgraph.normalization.service import normalize_cpsc_records
from tests.integration.test_normalization import _store
from tests.test_cpsc_normalizer import synthetic_payload

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple 42"
ITEM = {
    "nickname": "Kitchen air fryer",
    "manufacturer": "Acme",
    "model": "AF-100X",
    "description": "air fryer",
    "purchase_year": 2025,
}


@pytest.fixture
async def clean(session_factory: async_sessionmaker[AsyncSession]) -> None:
    return None


@pytest.fixture
async def catalog(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _store(session_factory, [synthetic_payload(RecallID=1)])
    await normalize_cpsc_records(session_factory)


async def _auth(client: AsyncClient, email: str) -> dict[str, str]:
    await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _create(client: AsyncClient, headers: dict[str, str], body: dict[str, object]) -> str:
    response = await client.post("/api/v1/inventory", json=body, headers=headers)
    assert response.status_code == 201, response.text
    item_id: str = response.json()["id"]
    return item_id


async def test_inventory_requires_authentication(clean: None, client: AsyncClient) -> None:
    for method, url in [("GET", "/api/v1/inventory"), ("POST", "/api/v1/inventory")]:
        response = await client.request(method, url, json=ITEM)
        assert response.status_code == 401


async def test_crud_lifecycle(clean: None, client: AsyncClient) -> None:
    alice = await _auth(client, "alice@example.com")
    item_id = await _create(client, alice, ITEM)

    listing = (await client.get("/api/v1/inventory", headers=alice)).json()
    assert listing["total"] == 1 and listing["items"][0]["nickname"] == "Kitchen air fryer"

    patched = await client.patch(
        f"/api/v1/inventory/{item_id}",
        json={"nickname": "Garage fryer", "model": None},
        headers=alice,
    )
    assert patched.status_code == 200
    assert (patched.json()["nickname"], patched.json()["model"]) == ("Garage fryer", None)
    assert patched.json()["manufacturer"] == "Acme"  # untouched field kept

    assert (await client.delete(f"/api/v1/inventory/{item_id}", headers=alice)).status_code == 204
    assert (await client.get(f"/api/v1/inventory/{item_id}", headers=alice)).status_code == 404


async def test_users_cannot_access_each_others_items(clean: None, client: AsyncClient) -> None:
    alice = await _auth(client, "alice@example.com")
    bob = await _auth(client, "bob@example.com")
    item_id = await _create(client, alice, ITEM)
    url = f"/api/v1/inventory/{item_id}"

    assert (await client.get(url, headers=bob)).status_code == 404
    assert (await client.get(f"{url}/matches", headers=bob)).status_code == 404
    assert (await client.patch(url, json={"nickname": "stolen"}, headers=bob)).status_code == 404
    assert (await client.delete(url, headers=bob)).status_code == 404
    assert (await client.get("/api/v1/inventory", headers=bob)).json()["total"] == 0

    still_there = await client.get(url, headers=alice)
    assert still_there.status_code == 200
    assert still_there.json()["nickname"] == "Kitchen air fryer"


async def test_item_is_matched_against_official_recalls(catalog: None, client: AsyncClient) -> None:
    alice = await _auth(client, "alice@example.com")
    item_id = await _create(client, alice, ITEM)

    body = (await client.get(f"/api/v1/inventory/{item_id}/matches", headers=alice)).json()

    top = body["matches"][0]
    assert (top["tier"], top["recall"]["source_record_id"]) == ("identifier_match", "1")
    assert "does not mean the product is safe" in body["disclaimer"]


@pytest.mark.parametrize(
    "body",
    [
        {"nickname": "no product info"},
        {"nickname": "", "model": "A1"},
        {"nickname": "bad upc", "upc": "12"},
        {"nickname": "mass assignment", "model": "A1", "user_id": "00000000-0000-0000-0000-0"},
        {"nickname": "bad year", "model": "A1", "purchase_year": 1800},
    ],
)
async def test_invalid_items_are_rejected(
    clean: None, client: AsyncClient, body: dict[str, object]
) -> None:
    alice = await _auth(client, "alice@example.com")

    response = await client.post("/api/v1/inventory", json=body, headers=alice)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_patch_cannot_remove_all_product_info(clean: None, client: AsyncClient) -> None:
    alice = await _auth(client, "alice@example.com")
    item_id = await _create(client, alice, {"nickname": "x", "model": "A1"})

    response = await client.patch(
        f"/api/v1/inventory/{item_id}", json={"model": None}, headers=alice
    )

    assert response.status_code == 422


async def test_per_user_item_limit(
    clean: None, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(inventory_service, "MAX_ITEMS_PER_USER", 2)
    alice = await _auth(client, "alice@example.com")
    for n in range(2):
        await _create(client, alice, {"nickname": f"item {n}", "model": f"M{n}00"})

    response = await client.post(
        "/api/v1/inventory", json={"nickname": "third", "model": "M300"}, headers=alice
    )

    assert response.status_code == 409


async def test_malformed_item_id_is_validation_problem(clean: None, client: AsyncClient) -> None:
    alice = await _auth(client, "alice@example.com")

    assert (await client.get("/api/v1/inventory/not-a-uuid", headers=alice)).status_code == 422
