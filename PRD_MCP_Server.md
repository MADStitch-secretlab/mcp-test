# Factsheet MCP PoC — MCP 서버 PRD (v2: Railway 배포)

## 1. 개요

### 1.1 목적
실제 OAuth 표준을 거치지 않고도, **Claude Desktop이 OAuth 인증 흐름을 정상적으로 수행한 것으로 인식하는지** 검증.

핵심 검증 포인트:
- Claude Desktop이 Custom Connector 추가 시 자동으로 OAuth 메타데이터를 발견하는가
- `/authorize` URL을 사용자 브라우저에 자동으로 열어주는가
- redirect로 돌아온 `code`를 토큰으로 교환하는가
- 이후 Tool 호출 시 Bearer 토큰을 자동으로 첨부하는가

### 1.2 범위
- ✅ MCP 서버 (FastMCP, Python)
- ✅ OAuth 메타데이터 응답 (가짜)
- ✅ `/authorize` 엔드포인트 (Next.js 로그인 화면으로 redirect)
- ✅ `/token` 엔드포인트 (검증 없이 가짜 토큰 발급)
- ✅ 인증된 Tool 1개 (`hello`)
- ✅ Railway 배포 (HTTPS 자동)
- ❌ 실제 PKCE / JWT / state 검증 (PoC라 의도적으로 생략)

### 1.3 비기능 요건
- 단일 Python 파일 (`server.py`)
- 환경변수 기반 설정 (로컬/배포 분리)
- Railway 호스팅 (HTTPS 자동 제공)
- Docker 기반 배포

---

## 2. 시스템 구성

```
[Claude Desktop]
       │
       │ Custom Connector 추가
       │ URL: https://mcp-poc.up.railway.app/mcp
       ▼
┌──────────────────────────────────┐
│   MCP 서버 (Railway 호스팅)       │
│   https://mcp-poc.up.railway.app │
│                                  │
│  /.well-known/...                 │
│  /authorize  → Vercel로 redirect  │
│  /token      → 가짜 토큰          │
│  /mcp        → Tool 처리          │
└──────────────┬───────────────────┘
               │
               ▼
   [Next.js 로그인 — Vercel]
   https://login-poc.vercel.app
```

### 기술 스택
| 항목 | 선택 |
|---|---|
| 언어 | Python 3.11+ |
| 프레임워크 | FastMCP |
| 전송 방식 | Streamable HTTP (SSE 지원) |
| 호스팅 | Railway (HTTPS 자동, Docker 배포) |

---

## 3. 환경변수

| 변수명 | 로컬 값 | 배포 값 (예시) | 용도 |
|---|---|---|---|
| `LOGIN_URL` | `http://localhost:3000/login` | `https://login-poc.vercel.app/login` | Next.js 로그인 화면 URL |
| `MCP_BASE_URL` | `http://localhost:8000` | `https://mcp-poc.up.railway.app` | OAuth 메타데이터 issuer URL |
| `PORT` | `8000` | (Railway가 자동 주입) | 서버 포트 |

### `.env.example`
```bash
LOGIN_URL=http://localhost:3000/login
MCP_BASE_URL=http://localhost:8000
PORT=8000
```

---

## 4. 엔드포인트 명세

### 4.1 `GET /.well-known/oauth-authorization-server`

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

### 4.2 `GET /.well-known/oauth-protected-resource`

```json
{
  "resource": "{MCP_BASE_URL}/mcp",
  "authorization_servers": ["{MCP_BASE_URL}"]
}
```

### 4.3 `POST /register` (가짜 DCR)

받은 거 무시, 가짜 응답:
```json
{
  "client_id": "fake-client-id",
  "client_secret": null,
  "client_id_issued_at": 1730000000,
  "redirect_uris": ["<요청에서 받은 값 그대로>"],
  "token_endpoint_auth_method": "none"
}
```

### 4.4 `GET /authorize`

**받는 쿼리스트링**: `response_type`, `client_id`, `redirect_uri`, `state`, `code_challenge`, `code_challenge_method`

**동작**: 받은 파라미터 그대로 `LOGIN_URL`에 전달하여 302 redirect:
```
{LOGIN_URL}?redirect_uri={원본}&state={원본}&code_challenge={원본}&code_challenge_method={원본}&client_id={원본}
```

### 4.5 `POST /token`

**Content-Type**: `application/x-www-form-urlencoded`

**동작**: 받은 거 무시, 가짜 토큰 발급:
```json
{
  "access_token": "fake_access_token_abc123",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "fake_refresh_token_xyz789"
}
```

### 4.6 `POST /mcp` (FastMCP 자동 처리)

**인증**: Bearer 헤더 있으면 통과, 없으면 `401 + WWW-Authenticate: Bearer`

**제공 Tool**: `hello`, `whoami`

---

## 5. 인증 흐름 (배포 환경)

```
[1] Claude Desktop: Custom Connector 추가
    URL: https://mcp-poc.up.railway.app/mcp
        ↓
[2] /mcp 호출 → 401 + WWW-Authenticate: Bearer
        ↓
[3] /.well-known/... 발견 → 메타데이터 받음
        ↓
[4] /register 호출 → 가짜 client_id 받음
        ↓
[5] 브라우저로 https://mcp-poc.up.railway.app/authorize?... 자동 오픈
        ↓
[6] MCP 서버가 https://login-poc.vercel.app/login으로 302
        ↓
[7] 사용자가 로그인 + 회사 선택
        ↓
[8] Vercel: redirect_uri로 302 (?code=fake&state=원본)
        ↓
[9] Claude Desktop: /token 호출 → 가짜 토큰 받음
        ↓
[10] /mcp 다시 호출 (Bearer 토큰) → Tool 사용 가능
```

---

## 6. 산출물

### 6.1 파일 구조
```
poc_mcp_server/
├── server.py
├── requirements.txt
├── Dockerfile
├── railway.json
├── .env.example
├── .gitignore
└── README.md
```

### 6.2 `requirements.txt`
```
fastmcp>=2.0.0
```

### 6.3 `Dockerfile`
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

EXPOSE 8000

CMD ["python", "server.py"]
```

### 6.4 `railway.json`
```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "DOCKERFILE",
    "dockerfilePath": "Dockerfile"
  },
  "deploy": {
    "startCommand": "python server.py",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### 6.5 `.gitignore`
```
__pycache__/
*.pyc
.env
.venv/
venv/
```

---

## 7. 참조 코드 — `server.py`

```python
"""
poc_mcp_server/server.py

PoC: 가짜 OAuth로 Claude Desktop 인증 흐름 검증
"""
import os
from urllib.parse import urlencode
from fastmcp import FastMCP
from starlette.responses import JSONResponse, RedirectResponse
from starlette.requests import Request

# ── 환경변수 ──
LOGIN_URL = os.getenv("LOGIN_URL", "http://localhost:3000/login")
MCP_BASE_URL = os.getenv("MCP_BASE_URL", "http://localhost:8000")
PORT = int(os.getenv("PORT", "8000"))

print(f"🚀 MCP PoC 서버 시작")
print(f"   LOGIN_URL    = {LOGIN_URL}")
print(f"   MCP_BASE_URL = {MCP_BASE_URL}")
print(f"   PORT         = {PORT}")

mcp = FastMCP(name="Factsheet PoC")


# ── OAuth 메타데이터 ──
@mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET"])
async def oauth_metadata(request: Request):
    return JSONResponse({
        "issuer": MCP_BASE_URL,
        "authorization_endpoint": f"{MCP_BASE_URL}/authorize",
        "token_endpoint": f"{MCP_BASE_URL}/token",
        "registration_endpoint": f"{MCP_BASE_URL}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
    })


@mcp.custom_route("/.well-known/oauth-protected-resource", methods=["GET"])
async def protected_resource_metadata(request: Request):
    return JSONResponse({
        "resource": f"{MCP_BASE_URL}/mcp",
        "authorization_servers": [MCP_BASE_URL],
    })


# ── DCR (가짜) ──
@mcp.custom_route("/register", methods=["POST"])
async def register(request: Request):
    body = await request.json()
    return JSONResponse({
        "client_id": "fake-client-id",
        "client_secret": None,
        "client_id_issued_at": 1730000000,
        "redirect_uris": body.get("redirect_uris", []),
        "token_endpoint_auth_method": "none",
    })


# ── /authorize → Vercel로 redirect ──
@mcp.custom_route("/authorize", methods=["GET"])
async def authorize(request: Request):
    qs = request.query_params
    forward_params = {
        "redirect_uri": qs.get("redirect_uri", ""),
        "state": qs.get("state", ""),
        "code_challenge": qs.get("code_challenge", ""),
        "code_challenge_method": qs.get("code_challenge_method", "S256"),
        "client_id": qs.get("client_id", ""),
    }
    redirect_url = f"{LOGIN_URL}?{urlencode(forward_params)}"
    return RedirectResponse(redirect_url, status_code=302)


# ── /token → 가짜 토큰 ──
@mcp.custom_route("/token", methods=["POST"])
async def token(request: Request):
    return JSONResponse({
        "access_token": "fake_access_token_abc123",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "fake_refresh_token_xyz789",
    })


# ── Tools ──
@mcp.tool
def hello() -> str:
    """인사 메시지 반환"""
    return "✅ PoC 인증 성공! Claude Desktop이 OAuth 흐름을 완료했습니다."


@mcp.tool
def whoami() -> str:
    """현재 세션 정보 반환"""
    return "현재 세션은 가짜 토큰으로 인증되었습니다."


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=PORT)
```

---

## 8. Railway 배포 가이드

### 8.1 사전 준비
- [Railway 계정](https://railway.app) 생성
- GitHub 저장소에 코드 푸시

### 8.2 배포 단계

#### Step 1. GitHub 저장소 생성 + 푸시
```bash
cd poc_mcp_server
git init
git add .
git commit -m "Initial PoC MCP server"
git branch -M main

# GitHub에 새 레포 생성 후
git remote add origin https://github.com/{username}/poc-mcp-server.git
git push -u origin main
```

#### Step 2. Railway 프로젝트 생성
1. Railway 대시보드 → **New Project**
2. **Deploy from GitHub repo** 선택
3. `poc-mcp-server` 저장소 선택
4. Railway가 Dockerfile 감지 → 자동 빌드 시작

#### Step 3. 도메인 발급
- Settings → Networking → **Generate Domain**
- 예: `mcp-poc-production.up.railway.app`

#### Step 4. 환경변수 설정
Railway 대시보드 → Variables 탭:
```
MCP_BASE_URL = https://mcp-poc-production.up.railway.app
LOGIN_URL    = https://login-poc.vercel.app/login
```

> ⚠️ MCP_BASE_URL은 **도메인 발급 후** 알 수 있음. 발급받은 값으로 채우고 저장 → 자동 재배포.

#### Step 5. 배포 검증
```bash
curl https://mcp-poc-production.up.railway.app/.well-known/oauth-authorization-server
```

기대 응답:
```json
{
  "issuer": "https://mcp-poc-production.up.railway.app",
  "authorization_endpoint": "https://mcp-poc-production.up.railway.app/authorize",
  ...
}
```

#### Step 6. 로그 확인
Railway 대시보드 → Deployments → Logs:
- `🚀 MCP PoC 서버 시작` 메시지 확인
- `LOGIN_URL`, `MCP_BASE_URL` 출력 확인

---

## 9. 로컬 개발 가이드

### 9.1 실행
```bash
cd poc_mcp_server
pip install -r requirements.txt

export LOGIN_URL=http://localhost:3000/login
export MCP_BASE_URL=http://localhost:8000
export PORT=8000

python server.py
```

### 9.2 검증
```bash
curl http://localhost:8000/.well-known/oauth-authorization-server
```

---

## 10. 검증 시나리오

### 시나리오 1: 메타데이터 응답
- **명령**: `curl https://mcp-poc-production.up.railway.app/.well-known/oauth-authorization-server`
- **기대**: JSON에 `issuer`, `authorization_endpoint`, `token_endpoint` 포함

### 시나리오 2: Custom Connector 추가
- **입력**: Claude Desktop → Connectors → Custom Connector → `https://mcp-poc-production.up.railway.app/mcp`
- **기대**: 브라우저 자동 오픈 → Vercel 로그인 화면 표시

### 시나리오 3: 로그인 통과 → Tool 호출
- **입력**: 로그인 → 회사 선택 → "hello 호출해줘"
- **기대**: `✅ PoC 인증 성공!` 메시지

---

## 11. 위험 요소

| 항목 | 내용 | 대응 |
|---|---|---|
| FastMCP 인증 미들웨어 | Bearer 토큰을 자동 검증할 수 있음 | `auth=None` 명시 |
| 메타데이터 라우트 충돌 | FastMCP가 OAuth 라우트 자동 생성 가능 | custom_route 우선 적용 |
| Claude Desktop 버전별 차이 | 메타데이터 필드 요구사항 다를 수 있음 | 1차 시도 후 응답 조정 |
| Railway 무료 플랜 슬립 | 미사용 시 콜드 스타트 ~5초 | 첫 요청은 느릴 수 있음 |

---

## 12. 다음 단계 (PoC 통과 시)

1. 실제 PKCE 검증 추가
2. JWT 발급 로직 (RS256) 추가
3. Factsheet 백엔드와 연동
4. FernetEncryption + DiskStore 추가
5. 사용량 측정 / 모니터링 추가

---

## 13. 산출물 체크리스트

- [ ] `server.py` 작성 (환경변수 기반)
- [ ] `Dockerfile`, `requirements.txt`, `.env.example` 작성
- [ ] GitHub 저장소 생성 및 푸시
- [ ] Railway 프로젝트 생성 및 배포
- [ ] Railway 도메인 발급
- [ ] 환경변수 설정 (`MCP_BASE_URL`, `LOGIN_URL`)
- [ ] 메타데이터 엔드포인트 응답 확인 (curl)
- [ ] Vercel 로그인 앱과 연동 테스트
- [ ] Claude Desktop end-to-end 테스트
