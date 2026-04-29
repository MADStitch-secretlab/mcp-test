"""
Factsheet MCP PoC server.

This intentionally uses a fake OAuth flow to verify that Claude Desktop can
discover metadata, open authorization, exchange a code, and attach a Bearer
token to later MCP tool calls.
"""

from __future__ import annotations

import os
from time import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse


def normalize_login_url(url: str) -> str:
    url = url.rstrip("?")
    parts = urlsplit(url)
    if parts.scheme and parts.netloc and parts.path in ("", "/"):
        return urlunsplit((parts.scheme, parts.netloc, "/login", parts.query, parts.fragment))
    return url


LOGIN_URL = normalize_login_url(os.getenv("LOGIN_URL", "http://localhost:3000/login"))
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://localhost:8000").rstrip("/")
PORT = int(os.getenv("PORT", "8000"))
MCP_PATH = "/mcp"

ACCESS_TOKEN = "fake_access_token_abc123"
REFRESH_TOKEN = "fake_refresh_token_xyz789"
AUTH_CODE = "fake_authorization_code_123"
CLIENT_ID = "fake-client-id"
AUTH_REQUESTS: dict[str, dict[str, str]] = {}


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


def append_query_params(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    existing_params = parse_qsl(parts.query, keep_blank_values=True)
    query = urlencode([*existing_params, *params.items()])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))


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
    redirect_uri = qs.get("redirect_uri", "")
    state = qs.get("state", "")
    AUTH_REQUESTS[state] = {
        "redirect_uri": redirect_uri,
        "client_id": qs.get("client_id", ""),
        "resource": qs.get("resource", ""),
        "code_challenge": qs.get("code_challenge", ""),
        "code_challenge_method": qs.get("code_challenge_method", "S256"),
    }
    mcp_callback_url = append_query_params(f"{MCP_BASE_URL}/login/callback", {"state": state})
    forward_params = {
        "response_type": qs.get("response_type", "code"),
        "redirect_uri": mcp_callback_url,
        "redirectUrl": mcp_callback_url,
        "redirect_url": mcp_callback_url,
        "redirectUri": mcp_callback_url,
        "redirectURL": mcp_callback_url,
        "redirecturl": mcp_callback_url,
        "callbackUrl": mcp_callback_url,
        "callback_url": mcp_callback_url,
        "returnUrl": mcp_callback_url,
        "return_url": mcp_callback_url,
        "returnTo": mcp_callback_url,
        "mcp_callback_url": mcp_callback_url,
        "state": state,
        "code_challenge": qs.get("code_challenge", ""),
        "code_challenge_method": qs.get("code_challenge_method", "S256"),
        "client_id": qs.get("client_id", ""),
        "resource": qs.get("resource", ""),
    }
    login_redirect_url = append_query_params(LOGIN_URL, forward_params)
    print(
        "[authorize] "
        f"state={state} "
        f"claude_redirect_uri={redirect_uri} "
        f"mcp_callback_url={mcp_callback_url} "
        f"login_redirect_url={login_redirect_url}",
        flush=True,
    )
    return RedirectResponse(login_redirect_url, status_code=302)


async def get_login_success_state(request: Request) -> str:
    state = request.query_params.get("state", "")
    if state:
        return state

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception:
            return ""
        return str(body.get("state", ""))

    try:
        form = await request.form()
    except Exception:
        return ""
    return str(form.get("state", ""))


async def complete_login(request: Request) -> RedirectResponse | JSONResponse:
    state = await get_login_success_state(request)
    auth_request = AUTH_REQUESTS.get(state)
    if not auth_request:
        print(f"[login-callback] unknown_state state={state}", flush=True)
        return JSONResponse(
            {"error": "unknown_state", "error_description": "No pending OAuth request for this state."},
            status_code=400,
        )

    redirect_uri = auth_request["redirect_uri"]
    claude_callback_url = append_query_params(redirect_uri, {"code": AUTH_CODE, "state": state})
    print(
        "[login-callback] "
        f"state={state} "
        f"claude_callback_url={claude_callback_url}",
        flush=True,
    )
    return RedirectResponse(claude_callback_url, status_code=302)


@mcp.custom_route("/login/callback", methods=["GET", "POST"])
async def login_callback(request: Request) -> RedirectResponse | JSONResponse:
    return await complete_login(request)


@mcp.custom_route("/login/success", methods=["GET", "POST"])
async def login_success(request: Request) -> RedirectResponse | JSONResponse:
    return await complete_login(request)


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
    print("Factsheet MCP PoC server starting", flush=True)
    print(f"  LOGIN_URL    = {LOGIN_URL}", flush=True)
    print(f"  MCP_BASE_URL = {MCP_BASE_URL}", flush=True)
    print(f"  MCP_PATH     = {MCP_PATH}", flush=True)
    print(f"  PORT         = {PORT}", flush=True)
    mcp.run(transport="http", host="0.0.0.0", port=PORT, path=MCP_PATH)
