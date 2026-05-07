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
from uuid import uuid4

import httpx
from fastmcp import Context, FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.server.dependencies import get_access_token
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
BACKEND_BASE_URL = os.getenv(
    "BACKEND_BASE_URL",
    f"{urlsplit(LOGIN_URL).scheme}://{urlsplit(LOGIN_URL).netloc}",
).rstrip("/")
OAUTH_AUTHORIZE_URL = os.getenv(
    "OAUTH_AUTHORIZE_URL",
    f"{urlsplit(LOGIN_URL).scheme}://{urlsplit(LOGIN_URL).netloc}/oauth/authorize",
).rstrip("?")
PORT = int(os.getenv("PORT", "8000"))
MCP_PATH = "/mcp"

ACCESS_TOKEN = "fake_access_token_abc123"
REFRESH_TOKEN = "fake_refresh_token_xyz789"
AUTH_CODE = "fake_authorization_code_123"
CLIENT_ID = "fake-client-id"
AUTH_REQUESTS: dict[str, dict[str, str]] = {}
CURRENT_COMPANY_BY_TOKEN: dict[str, str] = {ACCESS_TOKEN: "azflow"}
TEST_COMPANIES = [
    {
        "company_code": "azflow",
        "company_name": "에이지플로우",
        "role": "ADMIN",
    },
    {
        "company_code": "vsventures",
        "company_name": "벤처스퀘어",
        "role": "MEMBER",
    },
]
TEST_PORTFOLIOS_BY_COMPANY = {
    "azflow": [
        {"portfolio_id": "azflow-pf-001", "name": "AZFLOW Alpha Fund"},
        {"portfolio_id": "azflow-pf-002", "name": "AZFLOW Growth SPV"},
    ],
    "vsventures": [
        {"portfolio_id": "vsventures-pf-001", "name": "VentureSquare Seed Fund"},
        {"portfolio_id": "vsventures-pf-002", "name": "VentureSquare Bridge Fund"},
    ],
}


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


def get_frontend_origin() -> str:
    parts = urlsplit(LOGIN_URL)
    return f"{parts.scheme}://{parts.netloc}"


def extract_bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def get_current_access_token_value() -> str:
    token = get_access_token()
    if token is not None:
        return token.token
    return ACCESS_TOKEN


def companies_for_token(token: str) -> list[dict[str, object]]:
    current_company_code = CURRENT_COMPANY_BY_TOKEN.get(token, "azflow")
    return [
        {
            **company,
            "is_current": company["company_code"] == current_company_code,
        }
        for company in TEST_COMPANIES
    ]


def find_company(company_code: str, companies: list[dict[str, object]]) -> dict[str, object] | None:
    for company in companies:
        if company.get("company_code") == company_code:
            return company
    return None


async def fetch_companies_from_backend(access_token: str) -> dict[str, object]:
    url = f"{BACKEND_BASE_URL}/mcp/auth/companies"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {access_token}"})
    if response.status_code == 401:
        return {"error": "unauthorized", "message": "토큰이 만료되었거나 유효하지 않습니다.", "status_code": 401}
    if response.status_code == 403:
        return {"error": "forbidden", "message": "사용자가 어떤 회사에도 소속되어 있지 않습니다.", "status_code": 403}
    if response.status_code >= 400:
        return {
            "error": "backend_error",
            "message": f"회사 목록 조회 실패: backend returned {response.status_code}",
            "status_code": response.status_code,
            "body": response.text,
        }

    payload = response.json()
    companies = payload.get("companies", [])
    current_company = next(
        (company for company in companies if company.get("is_current")),
        companies[0] if companies else None,
    )
    return {
        "companies": companies,
        "current_company_code": current_company.get("company_code") if current_company else None,
    }


async def request_company_switch_from_backend(access_token: str, company_code: str) -> dict[str, object]:
    url = f"{BACKEND_BASE_URL}/mcp/auth/token"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            json={"grant_type": "company_switch", "company_code": company_code},
        )
    if response.status_code == 401:
        return {"error": "unauthorized", "message": "토큰이 만료되었거나 유효하지 않습니다.", "status_code": 401}
    if response.status_code == 403:
        return {"error": "forbidden", "message": "해당 회사에 접근 권한이 없습니다.", "status_code": 403}
    if response.status_code >= 400:
        return {
            "error": "backend_error",
            "message": f"회사 변경 실패: backend returned {response.status_code}",
            "status_code": response.status_code,
            "body": response.text,
        }
    return response.json()


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


@mcp.custom_route("/mcp/auth/companies", methods=["GET"])
async def backend_companies(request: Request) -> JSONResponse:
    token = extract_bearer_token(request)
    if token is None or token not in CURRENT_COMPANY_BY_TOKEN:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    return JSONResponse({"companies": companies_for_token(token)})


@mcp.custom_route("/mcp/auth/token", methods=["POST"])
async def backend_token(request: Request) -> JSONResponse:
    token = extract_bearer_token(request)
    if token is None or token not in CURRENT_COMPANY_BY_TOKEN:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        body = {}

    company_code = str(body.get("company_code", ""))
    company = find_company(company_code, companies_for_token(token))
    if company is None:
        return JSONResponse({"error": "forbidden", "message": "해당 회사에 접근 권한이 없습니다."}, status_code=403)

    CURRENT_COMPANY_BY_TOKEN[token] = company_code
    return JSONResponse(
        {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": 3600,
            "current_company_code": company_code,
            "company": {**company, "is_current": True},
        }
    )


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


async def switch_company_internal(company_code: str, ctx: Context) -> dict[str, object]:
    access_token = get_current_access_token_value()
    companies_result = await fetch_companies_from_backend(access_token)
    if "error" in companies_result:
        return companies_result

    companies = companies_result["companies"]
    selected_company = find_company(company_code, companies)  # type: ignore[arg-type]
    if selected_company is None:
        return {
            "error": "forbidden",
            "message": "해당 회사에 접근 권한이 없습니다.",
            "company_code": company_code,
            "available_company_codes": [company["company_code"] for company in companies],  # type: ignore[index]
        }

    switch_result = await request_company_switch_from_backend(access_token, company_code)
    if "error" in switch_result:
        return switch_result

    await ctx.set_state("current_company_code", company_code)
    return {
        "status": "ok",
        "message": f"{selected_company['company_name']} 회사로 변경되었습니다.",
        "current_company_code": company_code,
        "company": selected_company,
        "token_response": switch_result,
    }


@mcp.tool
async def list_companies(ctx: Context) -> dict[str, object]:
    """List companies the authenticated user can access."""
    access_token = get_current_access_token_value()
    result = await fetch_companies_from_backend(access_token)
    if "error" not in result and result.get("current_company_code"):
        await ctx.set_state("current_company_code", result["current_company_code"])
    return result


@mcp.tool
async def switch_company_by_code(company_code: str, ctx: Context) -> dict[str, object]:
    """Switch the active company by company_code using the standard tool-result pattern."""
    return await switch_company_internal(company_code, ctx)


@mcp.tool
async def switch_company(ctx: Context) -> dict[str, object]:
    """Switch company using MCP elicitation when the client supports it."""
    access_token = get_current_access_token_value()
    companies_result = await fetch_companies_from_backend(access_token)
    if "error" in companies_result:
        return companies_result

    companies = companies_result["companies"]
    choices = {
        str(company["company_code"]): {
            "title": f"{company['company_name']} ({company['role']})"
            + (" - 현재" if company.get("is_current") else "")
        }
        for company in companies  # type: ignore[union-attr]
    }

    try:
        result = await ctx.elicit(
            "변경할 회사를 선택하세요.",
            choices,
            response_title="회사",
            response_description="현재 MCP 세션에서 사용할 회사를 선택합니다.",
        )
    except Exception as exc:
        return {
            "error": "elicitation_not_supported",
            "message": "이 클라이언트는 elicitation을 지원하지 않습니다. list_companies 또는 switch_company_oauth Tool을 대신 사용해주세요.",
            "detail": str(exc),
            "fallback_tools": ["list_companies", "switch_company_oauth"],
        }

    action = getattr(result, "action", None)
    if action != "accept":
        return {
            "status": action or "cancelled",
            "message": "회사 선택이 완료되지 않았습니다.",
            "fallback_tools": ["list_companies", "switch_company_oauth"],
        }

    selected_company_code = str(getattr(result, "data", ""))
    return await switch_company_internal(selected_company_code, ctx)


@mcp.tool
async def switch_company_oauth(ctx: Context) -> dict[str, object]:
    """Return a browser URL for the OAuth company-switching fallback flow."""
    state = f"company-switch-{uuid4().hex}"
    mcp_callback_url = append_query_params(
        f"{MCP_BASE_URL}/login/callback",
        {"state": state, "purpose": "company_switch"},
    )
    auth_url = append_query_params(
        OAUTH_AUTHORIZE_URL,
        {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirectUrl": mcp_callback_url,
            "redirect_uri": mcp_callback_url,
            "state": state,
            "resource": f"{MCP_BASE_URL}{MCP_PATH}",
            "purpose": "company_switch",
        },
    )
    await ctx.set_state("pending_company_switch_state", state)
    return {
        "auth_url": auth_url,
        "message": "위 링크에서 회사를 선택해주세요.",
        "state": state,
    }


@mcp.tool
async def get_portfolio_summary(ctx: Context) -> dict[str, object]:
    """Return company-scoped portfolio data for TC-06 data isolation checks."""
    access_token = get_current_access_token_value()
    companies_result = await fetch_companies_from_backend(access_token)
    if "error" in companies_result:
        return companies_result

    current_company_code = str(companies_result.get("current_company_code") or "azflow")
    await ctx.set_state("current_company_code", current_company_code)
    current_company = find_company(
        current_company_code,
        companies_result["companies"],  # type: ignore[arg-type]
    )
    return {
        "current_company_code": current_company_code,
        "current_company": current_company,
        "portfolios": TEST_PORTFOLIOS_BY_COMPANY.get(current_company_code, []),
    }


if __name__ == "__main__":
    print("Factsheet MCP PoC server starting", flush=True)
    print(f"  LOGIN_URL    = {LOGIN_URL}", flush=True)
    print(f"  MCP_BASE_URL = {MCP_BASE_URL}", flush=True)
    print(f"  BACKEND_BASE_URL = {BACKEND_BASE_URL}", flush=True)
    print(f"  OAUTH_AUTHORIZE_URL = {OAUTH_AUTHORIZE_URL}", flush=True)
    print(f"  MCP_PATH     = {MCP_PATH}", flush=True)
    print(f"  PORT         = {PORT}", flush=True)
    mcp.run(transport="http", host="0.0.0.0", port=PORT, path=MCP_PATH)
