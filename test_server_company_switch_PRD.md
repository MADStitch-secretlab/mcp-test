# Factsheet MCP 회사 변경 로직 테스트 PRD

**Test Server Update for Company Switching Logic**

| 항목 | 내용 |
|---|---|
| 버전 | 1.0 |
| 작성일 | 2026.05.07 |
| 작성 | Upflow (박진감) |
| 대상 | Factsheet 테스트 서버 (FE + BE + MCP 통합 인스턴스) |

---

## 1. 개요

### 1.1 배경

현재 Phase 1 설계에서 회사 변경 로직은 항상 `/oauth/authorize` 브라우저 플로우를 재호출하는 것으로 결정되어 있다. 그러나 이 방식은 클라이언트 환경(CLI / Desktop / Web)에 따라 UX 차이가 크고, MCP Elicitation 지원 여부가 클라이언트마다 달라 단일 로직으로 검증이 불가능하다.

이에 따라 Claude Code(CLI)와 Claude Desktop, ChatGPT 환경에서 회사 변경 로직 3가지 케이스를 실제로 테스트하여 최적 패턴을 확정한다.

### 1.2 목적

- 3가지 회사 변경 패턴(Tool 방식 / Elicitation 방식 / OAuth 재인증 방식)을 동일 테스트 서버에서 동시 제공한다.
- Claude Code, Claude Desktop, ChatGPT 클라이언트에서 각각 어느 패턴이 동작하는지 매트릭스를 확보한다.
- Phase 1 정식 spec에 반영할 회사 변경 로직을 데이터 기반으로 결정한다.

### 1.3 범위

- **대상 서버**: 테스트 서버 (FE + BE + MCP 통합 인스턴스)
- **미포함**: Production 서버, Mock 서버, 정식 Factsheet API
- **기간**: 테스트 서버 수정 1주 + 케이스별 검증 1주 (총 2주)

---

## 2. 현재 상태 vs 변경 후

### 2.1 현재 테스트 서버 구조

현재 테스트 서버는 Frontend, Backend, MCP 서버가 단일 인스턴스에 통합되어 있다. 회사 리스트 데이터는 인증된 사용자 토큰을 기반으로 Backend가 보유한다.

| 구성요소 | 역할 | 현재 상태 | 회사 변경 관련 |
|---|---|---|---|
| Frontend | 로그인 / 회사 선택 화면 | OAuth 인증 화면 운영 | `/oauth/authorize` 화면만 제공 |
| Backend | API + 회사 데이터 보유 | 회사 리스트 미노출 | 회사 데이터 보유하나 MCP에 전달 X |
| MCP 서버 | Tool / Resource 제공 | 회사 변경 Tool 없음 | OAuth 강제 플로우만 가능 |

### 2.2 변경 후 구조

회사 리스트 데이터는 **Backend(프론트백)가 정식으로 보유하고 노출하는 책임을 진다**. MCP 서버는 이 데이터를 가져와 3가지 패턴으로 사용자에게 제공한다.

| 구성요소 | 변경 사항 |
|---|---|
| **Backend** | 신규 API 1개 추가: `GET /mcp/auth/companies` — 토큰 인증된 사용자의 소속 회사 리스트 반환 |
| Frontend | 기존 `/oauth/authorize` 회사 선택 화면 유지 (Case C 검증용) |
| **MCP 서버** | 3개 Tool 추가: `list_companies` / `switch_company` / `switch_company_oauth` — 각각 다른 패턴으로 회사 변경 |

---

## 3. Backend 변경사항

### 3.1 신규 API: 회사 리스트 조회

MCP 서버가 회사 리스트를 조회하기 위한 API. **회사 리스트 데이터는 반드시 프론트백 서버가 보유하고 노출해야 한다.**

#### Endpoint

```
GET /mcp/auth/companies
```

#### Request Header

```
Authorization: Bearer {access_token}
```

#### Response 200

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

#### 필드 정의

| 필드 | 타입 | 필수 | 설명 |
|---|---|:---:|---|
| `company_code` | string | Y | 회사 고유 코드 (URL path 파라미터로 사용) |
| `company_name` | string | Y | 표시용 회사 한글명 |
| `role` | enum | Y | `ADMIN` / `MEMBER` / `VIEWER` 중 하나 |
| `is_current` | boolean | Y | 현재 토큰의 활성 회사 여부 |

#### Error Cases

| Status | 발생 조건 |
|:---:|---|
| 401 | 토큰 만료 또는 유효하지 않은 토큰 |
| 403 | 사용자가 어떤 회사에도 소속되지 않음 |

### 3.2 기존 API 재사용

토큰 발급 API는 기존 것을 그대로 사용한다. 회사 변경 시 새 토큰 발급은 동일 엔드포인트에서 처리.

```
POST /mcp/auth/token   (기존 — 변경 없음)
```

---

## 4. MCP 서버 변경사항

### 4.1 3개 Tool 동시 제공

회사 변경 패턴 3가지를 모두 Tool로 노출하여 클라이언트별 동작 가능 여부를 직접 비교한다.

| Tool 이름 | 패턴 | 핵심 동작 |
|---|:---:|---|
| `list_companies` | Tool 결과 | Backend의 `GET /mcp/auth/companies` 호출 결과를 그대로 반환. LLM이 사용자에게 보여주고 자연어로 선택 받음 |
| `switch_company` | Elicitation | `ctx.elicit()` 로 enum 선택지 표시. 클라이언트가 elicitation을 지원해야 동작 |
| `switch_company_oauth` | OAuth 재인증 | 브라우저로 `/oauth/authorize` 열어 회사 선택 화면 표시. 모든 클라이언트에서 동작 |

### 4.2 Tool A: `list_companies` (Tool 결과 패턴)

#### 동작 흐름

1. 사용자: "회사 바꿔줘" / "어느 회사들에 접근 가능해?"
2. LLM이 `list_companies` Tool 호출 (인자 없음)
3. MCP 서버 → Backend: `GET /mcp/auth/companies`
4. MCP 서버 → LLM: 회사 배열 반환
5. LLM이 사용자에게 표시 → 사용자가 자연어로 선택
6. LLM이 `switch_company_by_code(company_code="azflow")` 호출

#### Input Schema

```json
{ }
```

#### Output

```json
{
  "companies": [...],
  "current_company_code": "azflow"
}
```

#### 기대 결과

- Claude Code, Claude Desktop, ChatGPT **모두 동작 보장** (표준 Tool)
- UX는 자연어 매칭에 의존 → LLM의 매칭 정확도 검증 필요

### 4.3 Tool B: `switch_company` (Elicitation 패턴)

#### 동작 흐름

1. 사용자: "회사 바꿔줘"
2. LLM이 `switch_company` Tool 호출
3. MCP 서버 → Backend: `GET /mcp/auth/companies` (리스트 확보)
4. MCP 서버 → 클라이언트: `ctx.elicit()` with enum schema
5. 클라이언트가 선택 UI 표시 → 사용자 선택
6. MCP 서버가 선택값으로 새 토큰 발급 → 세션 업데이트

#### Elicitation Schema

```json
{
  "type": "object",
  "properties": {
    "company_code": {
      "type": "string",
      "enum": ["azflow", "vsventures"],
      "enumNames": ["에이지플로우", "벤처스퀘어"],
      "title": "변경할 회사를 선택하세요"
    }
  },
  "required": ["company_code"]
}
```

#### 기대 결과

- **Claude Code (CLI)**: 동작 예상 — Form mode 다이얼로그 표시
- **Claude Desktop**: 미동작 또는 capability 미선언 에러 가능 — **검증 대상**
- **ChatGPT**: 미지원 가능성 높음 — **검증 대상**

#### Fallback 처리

`ctx.elicit()` 호출 시 클라이언트가 elicitation capability를 declare하지 않으면 `-32602` 에러 또는 `Method not found` 에러가 반환된다. 이 경우 MCP 서버는 다음 메시지로 graceful degradation 처리:

```
이 클라이언트는 elicitation을 지원하지 않습니다.
list_companies 또는 switch_company_oauth Tool을 대신 사용해주세요.
```

### 4.4 Tool C: `switch_company_oauth` (OAuth 재인증 패턴)

#### 동작 흐름

1. 사용자: "회사 바꿔줘"
2. LLM이 `switch_company_oauth` Tool 호출
3. MCP 서버 → 클라이언트: 브라우저 URL 반환 (`/oauth/authorize?...`)
4. 클라이언트가 브라우저 열기 → Frontend 회사 선택 화면 표시
5. 사용자가 화면에서 회사 선택 → 콜백으로 새 토큰 발급

#### Output

```json
{
  "auth_url": "https://test.factsheet.kr/oauth/authorize?client_id=...",
  "message": "위 링크에서 회사를 선택해주세요"
}
```

#### 기대 결과

- 모든 클라이언트에서 동작 — 가장 안정적인 fallback
- UX 부담 큼 (브라우저 전환) — 마지막 옵션으로 활용

---

## 5. 테스트 케이스 매트릭스

### 5.1 검증 환경

| 클라이언트 | 연결 방식 | 비고 |
|---|---|---|
| Claude Code | Streamable HTTP | CLI 환경, elicitation 공식 지원 |
| Claude Desktop | Streamable HTTP (Custom Connector) | Pro/Max/Team/Enterprise 플랜 필요 |
| ChatGPT | Custom Connector (Beta) | Plus/Team/Enterprise, Deep Research 모드 권장 |

### 5.2 테스트 케이스

#### TC-01: `list_companies` Tool 호출

| 항목 | 내용 |
|---|---|
| 전제조건 | 테스트 사용자가 2개 이상의 회사에 소속되어 있음 |
| 입력 | "내가 접근 가능한 회사 목록 보여줘" |
| 기대 동작 | LLM이 `list_companies` 호출 → 회사 배열 받아 사용자에게 표시 |
| 성공 기준 | 회사명, 코드, 역할이 정확히 표시됨 |

#### TC-02: 자연어로 회사 선택 (Tool 패턴)

| 항목 | 내용 |
|---|---|
| 전제조건 | TC-01 완료 후 같은 세션 |
| 입력 | "벤처스퀘어로 바꿔줘" |
| 기대 동작 | LLM이 "벤처스퀘어" → `company_code="vsventures"`로 매칭하여 `switch_company_by_code` 호출 |
| 성공 기준 | 회사 변경 성공, 이후 다른 Tool 호출 시 vsventures 데이터 반환 |

#### TC-03: `switch_company` Elicitation 호출

| 항목 | 내용 |
|---|---|
| 전제조건 | 각 클라이언트별로 진행 |
| 입력 | "회사 변경할게" 후 LLM이 `switch_company` Tool 호출 |
| 기대 동작 | 클라이언트가 선택 UI 표시 → 사용자 선택 |
| 성공 기준 (CLI) | Claude Code에서 인터랙티브 다이얼로그 표시 |
| 성공 기준 (Desktop) | 다이얼로그 표시 또는 graceful 에러 메시지 |
| 실패 케이스 기록 | 에러 메시지, 에러 코드, 클라이언트 로그 |

#### TC-04: `switch_company_oauth` 브라우저 플로우

| 항목 | 내용 |
|---|---|
| 전제조건 | 각 클라이언트별로 진행 |
| 입력 | `switch_company_oauth` Tool 호출 |
| 기대 동작 | `auth_url` 반환 → 사용자가 브라우저에서 클릭 |
| 성공 기준 | Frontend 회사 선택 화면이 정상 표시되고 콜백으로 토큰 갱신 |

#### TC-05: 권한 없는 회사로 변경 시도

| 항목 | 내용 |
|---|---|
| 전제조건 | `company_code` 직접 지정 |
| 입력 | `switch_company_by_code(company_code="unknown")` |
| 기대 동작 | Backend가 403 반환 → MCP가 사용자에게 명확한 에러 전달 |
| 성공 기준 | "해당 회사에 접근 권한이 없습니다" 류의 메시지 |

#### TC-06: 데이터 격리 검증

| 항목 | 내용 |
|---|---|
| 전제조건 | azflow에서 vsventures로 변경 직후 |
| 입력 | 포트폴리오 조회 Tool 호출 |
| 기대 동작 | vsventures의 포트폴리오만 반환되고 azflow 데이터 노출 없음 |
| 성공 기준 | 데이터에 azflow 식별자가 일절 포함되지 않음 |

---

## 6. 결과 기록 양식

각 테스트 케이스를 클라이언트별로 실행한 후 아래 매트릭스에 기록한다.

### 6.1 동작 가능 여부 매트릭스

| Tool / 패턴 | Claude Code | Claude Desktop | ChatGPT |
|---|:---:|:---:|:---:|
| `list_companies` | ☐ Pass / ☐ Fail | ☐ Pass / ☐ Fail | ☐ Pass / ☐ Fail |
| `switch_company` (Elicitation) | ☐ Pass / ☐ Fail | ☐ Pass / ☐ Fail | ☐ Pass / ☐ Fail |
| `switch_company_oauth` | ☐ Pass / ☐ Fail | ☐ Pass / ☐ Fail | ☐ Pass / ☐ Fail |
| 자연어 매칭 정확도 | __ % | __ % | __ % |
| UX 만족도 (1–5) | __ / 5 | __ / 5 | __ / 5 |

### 6.2 결정 기준

3개 클라이언트 모두에서 Pass 한 패턴이 있으면 그 패턴을 Phase 1 정식 spec으로 채택한다. 없을 경우 우선순위:

1. **1순위**: 자연어 매칭 정확도가 90% 이상인 `list_companies` + `switch_company_by_code` 조합
2. **2순위**: `switch_company_oauth` (모든 환경 보장, UX 부담 감수)
3. **3순위**: 클라이언트별 분기 (Claude Code = Elicitation, 그 외 = Tool 결과)

---

## 7. 일정 및 산출물

### 7.1 일정

| 주차 | 담당 | 작업 내용 |
|:---:|:---:|---|
| Week 1 (D1–D3) | Factsheet BE | `GET /mcp/auth/companies` 엔드포인트 구현 및 테스트 |
| Week 1 (D3–D5) | Upflow | MCP 서버에 3개 Tool 추가 (`list_companies` / `switch_company` / `switch_company_oauth`) |
| Week 1 (D5) | 공동 | 테스트 서버 배포 및 스모크 테스트 |
| Week 2 (D1–D3) | Upflow | 3개 클라이언트 × 6개 테스트 케이스 실행 및 기록 |
| Week 2 (D4–D5) | Upflow | 결과 분석 보고서 작성 및 Phase 1 spec 확정안 제출 |

### 7.2 산출물

- 테스트 결과 매트릭스 (6.1 양식 채워서)
- 클라이언트별 동작 영상 또는 스크린샷
- 최종 권장 패턴 결정 보고서
- Phase 1 정식 spec 수정안 (회사 변경 로직 부분만)

### 7.3 Out of Scope

- 프로덕션 Factsheet API 수정 (이번 PRD는 테스트 서버에 한정)
- 회사 신규 추가 / 권한 변경 워크플로우
- 로그아웃 / 세션 종료 로직
- CUD 엔드포인트 통합 (Phase 2)

---

## 8. 부록

### 8.1 클라이언트별 Elicitation 지원 현황 (2026.05 기준)

| 클라이언트 | 지원 여부 | 비고 |
|---|:---:|---|
| Claude Code | **공식 지원** | Form mode + URL mode 모두 지원, 자동 다이얼로그 표시 |
| VS Code / Cursor | **공식 지원** | Command Palette 스타일 UI |
| MCP Inspector | **공식 지원** | 디버깅용 UI |
| Claude Desktop | **미확인** | capability 선언 여부 검증 필요 — 본 테스트의 핵심 대상 |
| ChatGPT | **미확인** | Custom Connector 베타 — 검증 필요 |

### 8.2 참고

- FastMCP Elicitation 공식 문서: https://gofastmcp.com (Elicitation 섹션)
- MCP Spec — `elicitation/create` method
- Claude Code MCP 가이드: https://code.claude.com/docs/en/mcp
