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
└── PRD_MCP_Server.md
```

## Environment

```bash
LOGIN_URL=http://localhost:3000/login
MCP_BASE_URL=http://localhost:8000
PORT=8000
```

For Railway, set:

```bash
MCP_BASE_URL=https://your-railway-domain.up.railway.app
LOGIN_URL=https://login-poc.vercel.app/login
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

## Claude Desktop Connector

Use this URL after deployment:

```text
https://your-railway-domain.up.railway.app/mcp
```

The server intentionally skips real PKCE, JWT, and state validation because this
is only for proving the connector OAuth flow.
# mcp-test
