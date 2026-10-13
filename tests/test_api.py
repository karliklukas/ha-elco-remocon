"""API client against a local fake Remocon-Net server."""

import asyncio

import aiohttp
from aiohttp import web
import pytest

from conftest import api


class FakeCloud:
    def __init__(self):
        self.logins = 0
        self.expire_next = False
        self.menu_status = 200
        self.rate_limit = False
        self.gateway_errors = 0  # how many next dataItems calls fail with a gateway error
        self.data_calls = 0

    def app(self):
        app = web.Application()
        app.router.add_post("/api/v2/accounts/login", self.login)
        app.router.add_get("/api/v2/remote/plants/lite", self.plants)
        app.router.add_post("/api/v2/remote/dataItems/{gw}/get", self.data_items)
        app.router.add_get("/api/v2/menuItems/{gw}", self.menu_items)
        return app

    async def login(self, request):
        body = await request.json()
        if body.get("pwd") != "good":
            return web.Response(status=400, text="bad credentials")
        self.logins += 1
        return web.json_response({"token": f"T{self.logins}"})

    def _authorized(self, request):
        return request.headers.get("ar.authToken") == f"T{self.logins}"

    async def plants(self, request):
        if not self._authorized(request):
            return web.Response(status=405)
        return web.json_response([{"gwId": "GW1", "plantName": "TP"}])

    async def data_items(self, request):
        self.data_calls += 1
        if self.gateway_errors:
            self.gateway_errors -= 1
            return web.Response(status=500, text=":-( Gateway error from GW1 (Response code: InternalError)")
        if self.rate_limit:
            return web.Response(status=429, text="slow down")
        if self.expire_next or not self._authorized(request):
            self.expire_next = False
            return web.Response(status=405)
        body = await request.json()
        assert request.query["umsys"] == "si" and body["culture"] == "cs-CZ"
        return web.json_response({"items": [{"id": i["id"], "zone": i["zn"], "value": 1.0} for i in body["items"] if i["id"] == "IsHeatingPumpOn"]})

    async def menu_items(self, request):
        if self.menu_status != 200:
            return web.json_response({"Message": "An error has occurred."}, status=self.menu_status)
        ids = [int(x) for x in request.query["menuItems"].split(",")]
        return web.json_response([{"id": i, "value": 33.0} for i in ids if i == 348])


@pytest.fixture
async def cloud(monkeypatch):
    monkeypatch.setattr(api, "RETRY_DELAY", 0)
    fake = FakeCloud()
    runner = web.AppRunner(fake.app())
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    async with aiohttp.ClientSession() as session:
        yield fake, session, f"http://127.0.0.1:{port}/api/v2/"
    await runner.cleanup()


async def test_login_and_read(cloud):
    fake, session, url = cloud
    client = api.RemoconApi(session, "a@b.c", "good", url)
    assert (await client.get_plants())[0]["gwId"] == "GW1"
    items = await client.get_data_items("GW1", {}, [{"id": "IsHeatingPumpOn", "zn": 0}, {"id": "Unknown", "zn": 0}], "cs-CZ")
    assert list(items) == ["IsHeatingPumpOn@0"]
    assert (await client.get_menu_items("GW1", [348, 349]))[348]["value"] == 33.0


async def test_expired_token_relogin(cloud):
    fake, session, url = cloud
    client = api.RemoconApi(session, "a@b.c", "good", url)
    await client.get_plants()
    fake.expire_next = True
    items = await client.get_data_items("GW1", {}, [{"id": "IsHeatingPumpOn", "zn": 0}], "cs-CZ")
    assert "IsHeatingPumpOn@0" in items and fake.logins == 2


async def test_gateway_error_retried_once(cloud):
    fake, session, url = cloud
    client = api.RemoconApi(session, "a@b.c", "good", url)
    fake.gateway_errors = 1
    items = await client.get_data_items("GW1", {}, [{"id": "IsHeatingPumpOn", "zn": 0}], "cs-CZ")
    assert "IsHeatingPumpOn@0" in items and fake.data_calls == 2
    fake.gateway_errors, fake.data_calls = 2, 0  # fails twice -> error after exactly one retry
    with pytest.raises(api.RemoconError):
        await client.get_data_items("GW1", {}, [{"id": "IsHeatingPumpOn", "zn": 0}], "cs-CZ")
    assert fake.data_calls == 2


async def test_bad_password(cloud):
    _, session, url = cloud
    with pytest.raises(api.RemoconAuthError):
        await api.RemoconApi(session, "a@b.c", "bad", url).login()


async def test_menu_server_error_and_rate_limit(cloud):
    fake, session, url = cloud
    client = api.RemoconApi(session, "a@b.c", "good", url)
    fake.menu_status = 500
    with pytest.raises(api.RemoconError):
        await client.get_menu_items("GW1", [348])
    fake.rate_limit = True
    with pytest.raises(api.RemoconRateLimited):
        await client.get_data_items("GW1", {}, [{"id": "IsHeatingPumpOn", "zn": 0}], "cs-CZ")
