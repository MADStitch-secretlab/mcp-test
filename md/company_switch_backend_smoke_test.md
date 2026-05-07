# Company Switch Backend Smoke Test

Date: 2026-05-07

Target PRD: `md/test_server_company_switch_PRD.md`

## Scope

Local frontend-backend and MCP integration smoke test for the company switching
PRD.

Frontend backend:

```text
http://127.0.0.1:3000
```

MCP server:

```text
http://127.0.0.1:8000/mcp
```

Test token:

```text
fake_access_token_abc123
```

## Implemented Backend Surface

| Area | Endpoint / Tool | Result |
|---|---|---|
| Company list API | Frontend backend `GET /mcp/auth/companies` | Pass |
| Company switch token API | Frontend backend `POST /mcp/auth/token` | Pass |
| Tool result pattern | `list_companies` | Pass |
| Direct switch helper | `switch_company_by_code` | Pass |
| Elicitation pattern | `switch_company` | Pass with graceful fallback when unsupported |
| OAuth fallback pattern | `switch_company_oauth` | Pass, returns frontend OAuth URL |
| Data isolation helper | `get_portfolio_summary` | Pass |

## Smoke Results

### REST API

| Case | Expected | Actual |
|---|---|---|
| Frontend backend valid token company list | 2 companies returned with `is_current` | Pass |
| Frontend backend invalid token company list | 401 unauthorized | Pass |
| Frontend backend switch to `vsventures` | 200, current company becomes `vsventures` | Pass |
| Frontend backend switch to `unknown` | 403 forbidden | Pass |

### MCP Tools

| Case | Expected | Actual |
|---|---|---|
| Tool listing | Company switch tools exposed | Pass |
| MCP `list_companies` via frontend backend | Company array and current company returned | Pass |
| `switch_company_by_code("vsventures")` | Switch success response | Pass |
| `get_portfolio_summary` after switch | Only `vsventures` portfolios returned | Pass |
| `switch_company_by_code("unknown")` | Clear forbidden message | Pass |
| `switch_company` without elicitation support | Graceful fallback message | Pass |
| `switch_company_oauth` | Browser `auth_url` returned with callback params | Pass |

## Notes

- `BACKEND_BASE_URL` now points to the frontend backend origin by default.
- Local default is `http://localhost:3000`.
- `switch_company_oauth` returns the frontend OAuth URL based on `OAUTH_AUTHORIZE_URL`.
- The returned OAuth URL includes both `redirectUrl` and `redirect_uri`, both pointing back to the MCP callback URL.
