# Factsheet MCP PoC

Fake OAuth MCP server for validating Claude Desktop custom connector behavior.

## What This Tests

- OAuth metadata discovery from Claude Desktop.
- Browser redirect from `/authorize` to the external login app.
- Login completion through the MCP bridge callback at `/login/callback`.
- Code exchange against `/token`.
- Bearer token attachment on later MCP calls.
- Authenticated access to the `hello` and `whoami` tools.

## Files

```text
.
├── server.py
├── requirements.txt
├── Dockerfile
├── railway.json
├── .env.example
├── .gitignore
├── README.md
├── PRD_MCP_Server.md
├── test_server_company_switch_PRD.md
└── MCP_SERVER_ARCHITECTURE.md
```

## Environment

```bash
LOGIN_URL=http://localhost:3000/login
MCP_BASE_URL=http://localhost:8000
BACKEND_BASE_URL=http://localhost:3000
OAUTH_AUTHORIZE_URL=http://localhost:3000/oauth/authorize
PORT=8000
```

For Railway, set:

```bash
MCP_BASE_URL=https://your-railway-domain.up.railway.app
LOGIN_URL=https://login-poc.vercel.app/login
BACKEND_BASE_URL=https://login-poc.vercel.app
OAUTH_AUTHORIZE_URL=https://login-poc.vercel.app/oauth/authorize
```

## Local Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

## Start Command

```bash
python server.py
```

The MCP endpoint is:

```text
http://localhost:8000/mcp
```

## Quick Checks

```bash
curl http://localhost:8000/.well-known/oauth-authorization-server
curl http://localhost:8000/.well-known/oauth-protected-resource
curl -I "http://localhost:8000/authorize?redirect_uri=http://localhost:9999/callback&state=test&code_challenge=abc&code_challenge_method=S256&client_id=fake-client-id"
curl -I "http://localhost:8000/login/callback?state=test"
curl -X POST http://localhost:8000/token
```

## Login App Contract

`/authorize` stores Claude's original `redirect_uri` on the MCP server, then
sends the browser to `LOGIN_URL` with `redirectUrl` pointing back to:

```text
https://your-mcp-domain/login/callback?state=...
```

After login, the frontend should navigate the browser to that `redirectUrl`.
The MCP server then redirects the browser to Claude's original callback URL with
`code` and `state` attached.

## Company Switching Test Tools

The server exposes the company-switching test tools from
`test_server_company_switch_PRD.md`:

- `list_companies`: returns the authenticated user's companies.
- `switch_company_by_code`: switches company using a `company_code`.
- `switch_company`: tries MCP elicitation and gracefully falls back when unsupported.
- `switch_company_oauth`: returns a browser URL for OAuth-style company switching.
- `get_portfolio_summary`: test helper for company-scoped data isolation.

The company list and company-switch token APIs live in the frontend backend.
Point `BACKEND_BASE_URL` at the login app origin so the MCP server calls:

```text
{BACKEND_BASE_URL}/mcp/auth/companies
{BACKEND_BASE_URL}/mcp/auth/token
```

For local fallback testing, the MCP server also keeps mock implementations of
those two endpoints.

## Claude Desktop Connector

Use this URL after deployment:

```text
https://your-railway-domain.up.railway.app/mcp
```

The server intentionally skips real PKCE, JWT, and state validation because this
is only for proving the connector OAuth flow.
# mcp-test
