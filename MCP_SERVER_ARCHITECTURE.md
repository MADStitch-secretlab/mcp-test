# Factsheet MCP Server Architecture

이 문서는 현재 구현된 MCP 서버의 구조와 OAuth PoC 인증 흐름을 정리합니다.

## 1. 목적

이 서버는 실제 OAuth 보안 검증을 완성하기 위한 서버가 아니라, Claude Desktop 또는 Claude의 Custom Connector가 OAuth 기반 MCP 연결 흐름을 정상적으로 수행하는지 확인하기 위한 PoC 서버입니다.

검증 대상은 다음과 같습니다.

- Claude가 MCP 서버에서 OAuth metadata를 발견하는지
- Claude가 `/authorize`를 열고 브라우저 인증 흐름을 시작하는지
- 로그인 프론트가 MCP 서버로 인증 완료 신호를 돌려주는지
- MCP 서버가 Claude callback URL로 `code`와 `state`를 붙여 redirect하는지
- Claude가 `/token`으로 code를 교환하는지
- 이후 MCP tool 호출에 Bearer token을 첨부하는지

## 2. 현재 파일 구성

```text
.
├── server.py
├── requirements.txt
├── Dockerfile
├── railway.json
├── Procfile
├── .env.example
├── README.md
├── PRD_MCP_Server.md
└── MCP_SERVER_ARCHITECTURE.md
```

런타임에서 실제로 중요한 파일은 다음입니다.

```text
server.py
requirements.txt
Dockerfile
railway.json
Procfile
```

`PRD_MCP_Server.md`와 `MCP_SERVER_ARCHITECTURE.md`는 문서입니다. 서버 실행 중에 읽지 않습니다.

## 3. 주요 환경변수

| 변수 | 예시 | 설명 |
|---|---|---|
| `LOGIN_URL` | `https://mcp-server-mocha-three.vercel.app/login` | 로그인 프론트 URL |
| `MCP_BASE_URL` | `https://port-0-mcp-test-m4h5z3nf13944b7f.sel4.cloudtype.app` | MCP 서버 외부 공개 URL |
| `BACKEND_BASE_URL` | `https://port-0-mcp-test-m4h5z3nf13944b7f.sel4.cloudtype.app` | 회사 목록/토큰 API를 제공하는 backend URL |
| `OAUTH_AUTHORIZE_URL` | `https://mcp-server-mocha-three.vercel.app/oauth/authorize` | 회사 변경 OAuth fallback용 프론트 authorize URL |
| `PORT` | `8000` | 서버 listen port |

현재 `server.py`는 `LOGIN_URL`에 도메인 루트만 들어온 경우 자동으로 `/login`을 붙입니다.

예:

```text
LOGIN_URL=https://mcp-server-mocha-three.vercel.app
```

위 값은 내부에서 아래처럼 보정됩니다.

```text
https://mcp-server-mocha-three.vercel.app/login
```

그래도 배포 환경변수에는 명시적으로 `/login`까지 넣는 것을 권장합니다.

```text
LOGIN_URL=https://mcp-server-mocha-three.vercel.app/login
MCP_BASE_URL=https://port-0-mcp-test-m4h5z3nf13944b7f.sel4.cloudtype.app
BACKEND_BASE_URL=https://port-0-mcp-test-m4h5z3nf13944b7f.sel4.cloudtype.app
OAUTH_AUTHORIZE_URL=https://mcp-server-mocha-three.vercel.app/oauth/authorize
```

## 4. 외부 구성 요소

```text
[Claude / Claude Desktop]
        |
        | Custom Connector URL
        | https://MCP_BASE_URL/mcp
        v
[MCP Server]
        |
        | /authorize에서 로그인 프론트로 redirect
        v
[Login Frontend]
        |
        | 로그인 완료 후 redirectUrl로 이동
        v
[MCP Server /login/callback]
        |
        | Claude callback으로 code/state redirect
        v
[Claude callback]
        |
        | /token 호출
        v
[MCP Server /token]
```

## 5. MCP 서버 엔드포인트

### `GET /health`

헬스 체크용 엔드포인트입니다.

응답 예:

```json
{
  "status": "ok",
  "service": "factsheet-mcp-poc"
}
```

### `GET /.well-known/oauth-authorization-server`

Claude가 OAuth authorization server metadata를 발견하기 위해 호출합니다.

주요 응답 필드:

```json
{
  "issuer": "{MCP_BASE_URL}",
  "authorization_endpoint": "{MCP_BASE_URL}/authorize",
  "token_endpoint": "{MCP_BASE_URL}/token",
  "registration_endpoint": "{MCP_BASE_URL}/register",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code"],
  "code_challenge_methods_supported": ["S256"],
  "token_endpoint_auth_methods_supported": ["none"]
}
```

### `GET /.well-known/oauth-protected-resource`

Claude가 MCP resource metadata를 발견하기 위해 호출합니다.

응답 예:

```json
{
  "resource": "{MCP_BASE_URL}/mcp",
  "authorization_servers": ["{MCP_BASE_URL}"]
}
```

### `GET /.well-known/oauth-protected-resource/mcp`

일부 클라이언트가 MCP path 기준으로 protected resource metadata를 찾을 수 있어 추가 제공하는 호환 엔드포인트입니다.

### `POST /register`

Dynamic Client Registration PoC 엔드포인트입니다.

요청 검증 없이 fake client를 반환합니다.

응답 예:

```json
{
  "client_id": "fake-client-id",
  "client_secret": null,
  "client_id_issued_at": 1730000000,
  "redirect_uris": ["요청에서 받은 redirect_uris"],
  "token_endpoint_auth_method": "none"
}
```

### `GET /authorize`

Claude가 브라우저 인증을 시작하기 위해 호출하는 엔드포인트입니다.

Claude 요청 예:

```text
GET /authorize
  ?response_type=code
  &client_id=fake-client-id
  &redirect_uri=https%3A%2F%2Fclaude.ai%2Fapi%2Fmcp%2Fauth_callback
  &code_challenge=...
  &code_challenge_method=S256
  &state=...
  &resource={MCP_BASE_URL}/mcp
```

서버 동작:

1. `state`를 key로 Claude의 원본 `redirect_uri`를 메모리에 저장합니다.
2. MCP 서버의 로그인 완료 callback URL을 만듭니다.
3. 로그인 프론트로 redirect합니다.

로그인 프론트로 보내는 URL 구조:

```text
{LOGIN_URL}
  ?redirectUrl={MCP_BASE_URL}/login/callback?state={state}
  &redirect_uri={MCP_BASE_URL}/login/callback?state={state}
  &callbackUrl={MCP_BASE_URL}/login/callback?state={state}
  &returnUrl={MCP_BASE_URL}/login/callback?state={state}
  &state={state}
  ...
```

중요한 값은 `redirectUrl`입니다.

```text
redirectUrl=https://MCP서버도메인/login/callback?state=...
```

### `GET /login/callback`

로그인 프론트가 로그인 또는 회사 선택 완료 후 브라우저를 돌려보내는 MCP 서버 callback입니다.

프론트는 로그인 성공 후 다음처럼 이동해야 합니다.

```js
window.location.href = redirectUrl
```

MCP 서버는 `/login/callback?state=...`를 받으면 다음을 수행합니다.

1. `state`로 메모리에 저장된 Claude 원본 callback URL을 찾습니다.
2. fake authorization code를 붙입니다.
3. Claude callback URL로 redirect합니다.

최종 redirect 예:

```text
https://claude.ai/api/mcp/auth_callback
  ?code=fake_authorization_code_123
  &state={state}
```

### `POST /login/callback`

프론트가 form 또는 JSON 방식으로 state를 보낼 경우를 위한 호환 엔드포인트입니다.

다만 OAuth 브라우저 흐름에서는 프론트가 `fetch`만 호출하면 안 됩니다. 반드시 브라우저 자체가 이동해야 합니다.

권장 방식:

```js
window.location.href = redirectUrl
```

비권장 방식:

```js
fetch(redirectUrl)
```

`fetch`는 브라우저 주소창을 Claude callback으로 이동시키지 않기 때문에 Claude 인증 흐름이 이어지지 않을 수 있습니다.

### `GET /login/success`

`/login/callback`과 같은 동작을 하는 alias 엔드포인트입니다.

### `POST /token`

Claude가 authorization code를 access token으로 교환하기 위해 호출합니다.

현재 PoC에서는 code, PKCE, client 검증 없이 fake token을 발급합니다.

응답 예:

```json
{
  "access_token": "fake_access_token_abc123",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "fake_refresh_token_xyz789"
}
```

### `POST /mcp`

FastMCP가 처리하는 MCP endpoint입니다.

인증 동작:

- Bearer token 없음: `401 Unauthorized`
- 잘못된 Bearer token: `401 Unauthorized`
- `Authorization: Bearer fake_access_token_abc123`: 통과

제공 tool:

- `hello`
- `whoami`
- `list_companies`
- `switch_company_by_code`
- `switch_company`
- `switch_company_oauth`
- `get_portfolio_summary`

### `GET /mcp/auth/companies`

회사 변경 테스트용 backend endpoint입니다.

요청:

```text
Authorization: Bearer {access_token}
```

응답 예:

```json
{
  "companies": [
    {
      "company_code": "azflow",
      "company_name": "에이지플로우",
      "role": "ADMIN",
      "is_current": true
    },
    {
      "company_code": "vsventures",
      "company_name": "벤처스퀘어",
      "role": "MEMBER",
      "is_current": false
    }
  ]
}
```

### `POST /mcp/auth/token`

회사 변경 테스트용 backend token endpoint입니다.

요청:

```json
{
  "grant_type": "company_switch",
  "company_code": "vsventures"
}
```

응답 예:

```json
{
  "access_token": "fake_access_token_abc123",
  "token_type": "Bearer",
  "expires_in": 3600,
  "current_company_code": "vsventures"
}
```

## 6. 회사 변경 테스트 Tool

### `list_companies`

`BACKEND_BASE_URL/mcp/auth/companies`를 호출해서 현재 토큰으로 접근 가능한 회사 목록을 반환합니다.

### `switch_company_by_code`

`company_code`를 직접 받아 회사 접근 권한을 확인한 뒤 `BACKEND_BASE_URL/mcp/auth/token`으로 회사 변경을 요청합니다.

### `switch_company`

MCP Elicitation을 사용해서 클라이언트에 회사 선택 UI를 요청합니다.

클라이언트가 elicitation을 지원하지 않으면 다음 fallback 메시지를 반환합니다.

```text
이 클라이언트는 elicitation을 지원하지 않습니다.
list_companies 또는 switch_company_oauth Tool을 대신 사용해주세요.
```

### `switch_company_oauth`

브라우저 회사 선택 fallback을 위해 `OAUTH_AUTHORIZE_URL` 기반 URL을 반환합니다.

### `get_portfolio_summary`

TC-06 데이터 격리 검증용 테스트 Tool입니다. 현재 회사에 해당하는 portfolio mock 데이터만 반환합니다.

## 7. 전체 인증 흐름

```mermaid
sequenceDiagram
    participant Claude as Claude
    participant MCP as MCP Server
    participant Front as Login Frontend

    Claude->>MCP: POST /mcp without token
    MCP-->>Claude: 401 WWW-Authenticate: Bearer

    Claude->>MCP: GET /.well-known/oauth-protected-resource/mcp
    MCP-->>Claude: protected resource metadata

    Claude->>MCP: GET /.well-known/oauth-authorization-server
    MCP-->>Claude: authorization server metadata

    Claude->>MCP: POST /register
    MCP-->>Claude: fake-client-id

    Claude->>MCP: GET /authorize?redirect_uri=ClaudeCallback&state=...
    MCP->>MCP: Store ClaudeCallback by state
    MCP-->>Front: 302 LOGIN_URL?redirectUrl=MCP/login/callback?state=...

    Front->>Front: User login and company selection
    Front-->>MCP: Browser redirect to /login/callback?state=...

    MCP->>MCP: Load ClaudeCallback by state
    MCP-->>Claude: 302 ClaudeCallback?code=fake_authorization_code_123&state=...

    Claude->>MCP: POST /token
    MCP-->>Claude: fake access token

    Claude->>MCP: POST /mcp with Bearer token
    MCP-->>Claude: MCP response
```

## 8. 프론트엔드 계약

프론트는 MCP 서버가 전달한 `redirectUrl`을 query string에서 읽어야 합니다.

예:

```js
const params = new URLSearchParams(window.location.search)
const redirectUrl = params.get("redirectUrl")
```

로그인과 회사 선택이 끝나면 `redirectUrl`로 브라우저를 이동시킵니다.

```js
function onLoginSuccess() {
  const params = new URLSearchParams(window.location.search)
  const redirectUrl = params.get("redirectUrl")

  if (redirectUrl) {
    window.location.href = redirectUrl
    return
  }

  window.location.href = "/"
}
```

프론트가 직접 Claude callback URL을 만들면 안 됩니다.

프론트가 이동해야 하는 URL은 Claude URL이 아니라 MCP callback URL입니다.

```text
https://MCP서버도메인/login/callback?state=...
```

그 다음 Claude callback으로 보내는 책임은 MCP 서버가 가집니다.

## 9. 로그로 보는 정상 흐름

정상 흐름에서는 배포 로그에 다음 순서가 보여야 합니다.

```text
POST /mcp HTTP/1.1" 401 Unauthorized
GET /.well-known/oauth-protected-resource/mcp HTTP/1.1" 200 OK
GET /.well-known/oauth-authorization-server HTTP/1.1" 200 OK
POST /register HTTP/1.1" 200 OK
[authorize] state=... claude_redirect_uri=... mcp_callback_url=... login_redirect_url=...
GET /authorize?... HTTP/1.1" 302 Found
GET /login/callback?state=... HTTP/1.1" 302 Found
POST /token HTTP/1.1" 200 OK
POST /mcp HTTP/1.1" 200 OK
```

`/authorize` 이후 `/login/callback`이 없다면 프론트가 `redirectUrl`로 브라우저 이동을 하지 않은 것입니다.

`/login/callback`은 있는데 `/token`이 없다면 Claude callback URL로 이동하는 과정에서 문제가 있는 것입니다.

`/token`은 있는데 `/mcp`가 401이면 token 값 또는 FastMCP auth 설정을 확인해야 합니다.

## 10. 현재 PoC 제한사항

현재 구현은 의도적으로 간단합니다.

- `AUTH_REQUESTS`는 메모리 dict입니다.
- 서버 재시작 시 pending authorization state가 사라집니다.
- 멀티 인스턴스 배포에서는 state가 다른 인스턴스에 저장될 수 있습니다.
- 실제 PKCE 검증을 하지 않습니다.
- 실제 JWT 발급을 하지 않습니다.
- fake access token만 허용합니다.
- built-in `/mcp/auth/companies`, `/mcp/auth/token`은 테스트 backend stub입니다.
- production 인증 서버로 쓰면 안 됩니다.

실제 제품화 단계에서는 다음이 필요합니다.

- Redis 또는 DB 기반 authorization request store
- state 만료 시간
- PKCE verifier 검증
- client 검증
- JWT access token 발급
- refresh token 저장 및 회전
- audit log
- HTTPS domain 고정 검증

## 11. 빠른 점검 체크리스트

배포 환경변수:

```text
MCP_BASE_URL=https://실제-MCP-서버도메인
LOGIN_URL=https://실제-프론트도메인/login
BACKEND_BASE_URL=https://실제-backend-도메인
OAUTH_AUTHORIZE_URL=https://실제-프론트도메인/oauth/authorize
```

Claude Custom Connector URL:

```text
https://실제-MCP-서버도메인/mcp
```

브라우저 확인:

```text
https://실제-MCP-서버도메인/health
https://실제-MCP-서버도메인/.well-known/oauth-authorization-server
https://실제-MCP-서버도메인/.well-known/oauth-protected-resource
```

로그에서 확인할 값:

```text
mcp_callback_url=https://실제-MCP-서버도메인/login/callback?state=...
login_redirect_url=https://실제-프론트도메인/login?redirectUrl=...
```
