"""Test the API client."""

import json
import ssl
from typing import Any

import moto
import pytest
from pytest_httpserver import HTTPServer
import trustme
import werkzeug.wrappers as wrappers

from aviatrix_ha.api import client


@pytest.fixture(scope="session")
def ca():
    return trustme.CA()


@pytest.fixture(scope="session")
def httpserver_ssl_context(ca):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    localhost_cert = ca.issue_cert("localhost")
    localhost_cert.configure_cert(context)
    return context


def respond_with_json(data: dict[str, Any]) -> wrappers.Response:
    return wrappers.Response(json.dumps(data), content_type="application/json")


def v2_api_handler(request: wrappers.Request) -> wrappers.Response:
    print(request.json)
    if request.json.get("action") == "login":
        if request.headers.get("X-Access-Key") != "mytoken":
            return wrappers.Response(status=403)
        if (
            request.json.get("username") == "admin"
            and request.json.get("password") == "mypassword"
        ):
            return respond_with_json({"return": True, "CID": "mycid"})
        return respond_with_json({"return": False})

    if request.json.get("action") == "initial_setup":
        return respond_with_json({"return": True})

    if request.json.get("action") == "setup_account_profile":
        if request.json.get("account_name") == "myaccount":
            return respond_with_json({"return": True})
        return respond_with_json({"return": False})

    if request.json.get("action") == "restore_cloudx_config":
        if (
            request.json.get("file_name") == "mybackup"
            and request.json.get("account_name") == "myaccount"
        ):
            return respond_with_json({"return": True})
        return respond_with_json({"return": False})

    return wrappers.Response(status=400)


@moto.mock_aws
def test_client(httpserver: HTTPServer):
    httpserver.expect_request(
        "/v2/api", query_string="action=get_api_token", method="GET"
    ).respond_with_json({"return": True, "results": {"api_token": "mytoken"}})
    httpserver.expect_request(
        "/v2/api",
    ).respond_with_handler(v2_api_handler)

    c = client.ApiClient(f"localhost:{httpserver.port}")
    assert c.cid == ""
    c.login("admin", "mypassword")
    assert c.cid == "mycid"
    c.initial_setup()
    assert c.create_cloud_account("myaccount")["return"]
    assert c.restore_backup("mybackup", "myaccount")["return"]
