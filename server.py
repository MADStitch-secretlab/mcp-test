"""
Factsheet MCP PoC server.

This intentionally uses a fake OAuth flow to verify that Claude Desktop can
discover metadata, open authorization, exchange a code, and attach a Bearer
token to later MCP tool calls.
"""

from __future__ import annotations

import os
from time import time
from urllib.parse import urlencode

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse


LOGIN_URL = os.getenv("LOGIN_URL", "http://localhost:3000/login").rstrip("?")
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://localhost:8000").rstrip("/")
PORT = int(os.getenv("PORT", "8000"))
MCP_PATH = "/mcp"

ACCESS_TOKEN = "fake_access_token_abc123"
REFRESH_TOKEN = "fake_refresh_token_xyz789"
CLIENT_ID = "fake-client-id"


auth = StaticTokenVerifier(
    tokens={
        ACCESS_TOKEN: {
            "client_id": CLIENT_ID,
            "sub": "factsheet-poc-user",
            "scope": "mcp:tools",
        }
    }
)

mcp = FastMCP(name="Factsheet PoC", auth=auth)


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "factsheet-mcp-poc"})


@mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])
async def oauth_metadata(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "issuer": MCP_BASE_URL,
            "authorization_endpoint": f"{MCP_BASE_URL}/authorize",
            "token_endpoint": f"{MCP_BASE_URL}/token",
            "registration_endpoint": f"{MCP_BASE_URL}/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
        }
    )


@mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
@mcp.custom_route("/.well-known/oauth-protected-resource/mcp", methods=["GET"])
async def protected_resource_metadata(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "resource": f"{MCP_BASE_URL}{MCP_PATH}",
            "authorization_servers": [MCP_BASE_URL],
        }
    )


@mcp.custom_route("/register", methods=["POST"])
async def register(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        body = {}

    return JSONResponse(
        {
            "client_id": CLIENT_ID,
            "client_secret": None,
            "client_id_issued_at": int(time()),
            "redirect_uris": body.get("redirect_uris", []),
            "token_endpoint_auth_method": "none",
        }
    )


@mcp.custom_route("/authorize", methods=["GET"])
async def authorize(request: Request) -> RedirectResponse:
    qs = request.query_params
    forward_params = {
        "redirect_uri": qs.get("redirect_uri", ""),
        "state": qs.get("state", ""),
        "code_challenge": qs.get("code_challenge", ""),
        "code_challenge_method": qs.get("code_challenge_method", "S256"),
        "client_id": qs.get("client_id", ""),
    }
    return RedirectResponse(f"{LOGIN_URL}?{urlencode(forward_params)}", status_code=302)


@mcp.custom_route("/token", methods=["POST"])
async def token(request: Request) -> JSONResponse:
    await request.body()
    return JSONResponse(
        {
            "access_token": ACCESS_TOKEN,
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": REFRESH_TOKEN,
        }
    )


@mcp.tool
def hello() -> str:
    """Return a PoC success message."""
    return "PoC 인증 성공! Claude Desktop이 OAuth 흐름을 완료했습니다."


@mcp.tool
def whoami() -> str:
    """Return the fake authenticated session identity."""
    return "현재 세션은 fake_access_token_abc123 토큰으로 인증되었습니다."


if __name__ == "__main__":
    print("Factsheet MCP PoC server starting")
    print(f"  LOGIN_URL    = {LOGIN_URL}")
    print(f"  MCP_BASE_URL = {MCP_BASE_URL}")
    print(f"  MCP_PATH     = {MCP_PATH}")
    print(f"  PORT         = {PORT}")
    mcp.run(transport="http", host="0.0.0.0", port=PORT, path=MCP_PATH)
