# 개인 거래/예산 관리 에이전트 — 설계 문서

원본 기획(`Personal_financial_management.txt`)을 기준으로, 실제 대화하면서 구현한 최종 설계를 정리한 문서.

## 1. 개요

- **목적**: Gemini Function Calling을 이용해서 자연어로 개인 거래 내역과 예산을 관리하는 에이전트
- **실행 환경**: VSCode 내부에서 파이썬으로 동작 (웹 서버 없음, CLI 전용)
- **사용 모델**: `gemini-3.6-flash`
- **API 키**: `.env`의 `GEMINI_API_KEY`
- **대화 기억**: `client.interactions.create(..., store=True)`로 매 턴을 Gemini 서버에 저장하고, 응답으로 받은 `interaction.id`를 다음 호출의 `previous_interaction_id`로 넘겨서 이어감. `가계부_도우미`는 이 id를 `data/session.json`에도 저장해뒀다가 **프로그램을 재시작해도 이전 대화를 이어서 기억**한다 (`'새 대화'`라고 말하면 초기화). 서버 쪽 세션이 만료됐으면 자동으로 새 대화로 재시도한다
- **입력 방식**: 번호/메뉴 선택 없이 처음부터 끝까지 자연어. 프로그램 시작 시 안내 배너만 출력

## 2. 파일 구조

`기본_CLI`와 `가계부_도우미`는 **완전히 독립적인 두 개의 폴더**다. 각자 자기 폴더 안에 `tools.py`/`storage.py`/`.env`/`requirements.txt` 사본을 따로 갖고 있고, 서로의 파일을 참조하지 않는다 (데이터도 각자 폴더 안의 `data/`에 따로 쌓인다).

**`기본_CLI/`는 여기서 개발을 멈추고 더 이상 갱신하지 않는다.** 앞으로의 기능 추가/개선은 전부 `가계부_도우미/` 쪽에서만 진행한다.

| 파일/폴더 | 역할 |
|---|---|
| `PLAN.md`, `Personal_financial_management.txt` | 루트에 공통으로 남아있는 설계 문서/원본 기획 |
| `기본_CLI/main.py` | 순수 텍스트 CLI 버전 (개발 중단, 스냅샷 그대로 유지) |
| `기본_CLI/tools.py`, `storage.py`, `.env`, `requirements.txt` | 위 버전 전용 사본 |
| `가계부_도우미/app.py` | 로직은 동일하고 `rich` 라이브러리로 Claude Code 스타일 터미널 UI(구분선 기반 레이아웃, 색상, 표, 마크다운, 스피너, 마스코트)를 입힌 버전 — **여기서 계속 발전시킬 버전** |
| `가계부_도우미/tools.py`, `storage.py`, `.env`, `requirements.txt` | 위 버전 전용 사본 |

## 3. 데이터 모델 (각 폴더의 `data/transactions.json`)

```json
{
  "transactions": [
    { "id": 1, "category": "식비", "date": "2026-08-28", "amount": 8000, "description": "점심값" }
  ],
  "budgets": { "식비": 100000 },
  "next_id": 2,
  "categories": ["식비", "필요 지출", "의류비", "운동", "일상생활", "기타"]
}
```

- `amount`는 부호 있는 숫자. 예산(`budgets`)에서 남은 돈을 `budget - sum(amount)`로 계산하므로,
  지출은 양수로, 수입/환불처럼 예산에 다시 채워지는 금액은 음수로 등록해야 한다 (0은 금지).
  이 규칙은 도구 설명과 시스템 프롬프트에 명시해서 Gemini가 지키도록 한다.
- `next_id`는 거래 등록 시마다 발급되는 고유 id 카운터 (삭제해도 재사용 안 함)
- `categories`는 파일이 없을 때 `storage.DEFAULT_CATEGORIES` 6개로 초기화됨

## 4. 카테고리 정책

- 초기값 6개(식비/필요 지출/의류비/운동/일상생활/기타)이지만 **고정 목록이 아니라 데이터 파일에 저장되는 동적 목록**
- `transaction_registration`/`transaction_Modification`은 **등록된 카테고리가 아니면 거부**하고 `category_registration`부터 하라고 안내 (조용히 '기타'로 치환하지 않음)
- '기타'는 안전망 역할이라 **삭제 불가**
- 카테고리 삭제 시 그 카테고리의 거래는 자동으로 '기타'로 이동, 예산 설정은 삭제됨
- 카테고리 이름 변경 시 관련 거래/예산도 새 이름으로 함께 이동

## 5. Tool 명세 (`가계부_도우미` 기준 총 11개, `기본_CLI`는 10개에서 개발 중단)

원본 기획은 7개였으나, 대화 중 "예산만 등록", "새 카테고리 허용", "되돌리기" 요구가 나오면서 8~11번이 추가됨.

| # | 이름 | 주요 파라미터 | 동작 요약 | 예외 처리 |
|---|---|---|---|---|
| 1 | `transaction_registration` | category(필수), amount, description, budget | 거래 등록 및/또는 예산 설정. `amount` 없이 `budget`만 주면 거래 없이 예산만 설정 | amount·budget 둘 다 없으면 거부 / amount=0 거부 / 미등록 카테고리 거부 |
| 2 | `transaction_search` | category, date, query (모두 선택) | 조건에 맞는 거래를 (category, date, amount)만 골라 반환 | 매치 없으면 "찾을 수 없다" 안내 |
| 3 | `transaction_Modification` | id 또는 (category/date/description), amount | id 있으면 category/date/description을 새 값으로, id 없으면 그 필드들을 검색조건으로 써서 거래를 찾은 뒤 amount만 변경 | id 없음+조건 없음 거부 / 후보 0건·다건 처리 / amount=0 거부 / 미등록 카테고리로 변경 거부 |
| 4 | `transaction_Delete` | id 또는 (category/date/query) | id 또는 조건으로 찾아 삭제, 반환값은 알림 문구만 | 못 찾으면 삭제 불가 안내 / 다건이면 특정 요청 |
| 5 | `transaction_Budget_Management` | category(선택), date(선택) | 카테고리의 예산-사용금액=남은돈 계산. category 생략 시 전체 카테고리 조회 | 미등록/예산 미설정 카테고리 거부 |
| 6 | `transaction_Save_Json` | id 또는 (category/date/query) | 조건에 맞는 거래를 `data/transactions_export_*.json`으로 저장 | 매치 없으면 저장 불가 안내 |
| 7 | `monthly_Transaction_History` | month (YYYY-MM) | 해당 월 거래를 카테고리별로 묶어 `data/monthly_report_*.md`로 저장 | 해당 월 거래 없으면 안내 |
| 8 | `category_registration` | category | 새 카테고리를 목록에 추가 | 이미 있으면 거부 |
| 9 | `category_Modification` | old_category, new_category | 카테고리 이름 변경 + 관련 거래/예산 자동 이동 | 기존 없음/새 이름 중복 거부 |
| 10 | `category_Delete` | category | 카테고리 삭제, 관련 거래는 '기타'로 이동 | '기타' 삭제 거부 / 미등록 카테고리 거부 |
| 11 | `undo_last_action` (가계부_도우미 전용) | 없음 | 1~10번 중 데이터를 바꾸는 작업(등록/수정/삭제, 카테고리 등록/수정/삭제) 직전 상태로 한 단계 복원 | 되돌릴 작업이 없으면 안내. 스냅샷은 마지막 1건만 보관(다단계 undo 아님) |

## 6. 대화 처리 흐름 (`기본_CLI/main.py`, `가계부_도우미/app.py` 공통) — Gemini Interactions API

1. `create_interaction(input_data, previous_interaction_id)` 헬퍼가 `client.interactions.create(model=MODEL, input=..., previous_interaction_id=..., tools=tools.TOOLS, store=True, system_instruction=...)`를 호출. `tools.py`의 dict 스키마를 **변환 없이 그대로** `tools=`에 전달 가능 (Interactions API의 `Function` 타입과 필드가 일치함: `type`/`name`/`description`/`parameters`)
2. `system_instruction`에 오늘 날짜를 박아둬서 "오늘/어제/이번 달" 같은 상대 날짜 표현을 Gemini가 YYYY-MM-DD·YYYY-MM으로 변환해 도구를 호출하도록 유도
3. while 루프: 사용자 입력 → `create_interaction(user_input, previous_interaction_id)` → `interaction.steps` 중 `type == "function_call"`인 것들을 `execute_tool_call()`로 실행 → 결과를 `{"type": "function_result", "call_id":..., "result":[...]}` 형태로 만들어 다시 `create_interaction(function_results, interaction.id)`로 전달 → function_call이 더 없으면 `interaction.output_text` 출력
4. 매 호출마다 `previous_interaction_id = interaction.id`로 갱신해서 다음 턴에 이어붙임
5. 종료 조건: 사용자가 "종료" 입력
6. **동기(sync) 방식 유지**: `client.aio.interactions.create`(비동기 클라이언트)와 `asyncio.gather`로 한 턴 안의 여러 function_call을 동시 실행하는 것도 가능하지만, `tools.py` 함수들이 전부 로컬 JSON 파일 I/O라 병렬화해도 체감 이득이 거의 없고 턴과 턴 사이는 어차피 순차적일 수밖에 없어서(다음 요청이 이전 요청의 `interaction.id`에 의존) 굳이 async로 바꾸지 않기로 함

## 7. 원본 기획 대비 달라진 점

| 원본 기획 | 최종 구현 | 이유 |
|---|---|---|
| tools 7개 | tools 10개 (category_* 3개 추가) | 등록 안 된 새 카테고리를 다루기 위해 |
| `amount` 필수 | `amount` 선택 (budget만으로 호출 가능) | 거래 없이 예산만 설정하는 케이스 지원 |
| 수정/삭제 시 `id` 필수 뉘앙스 | `id` 선택, 없으면 category/date/description/query로 특정 | "그 거래 얼마로 바꿔줘"처럼 id 모르는 자연어 지원 |
| 카테고리 고정 목록 | 동적 목록 + 관리 도구(8~10) | 스펙의 "카테고리 = [...] 등등"이 확장 가능성을 내포 |
| 번호 메뉴 UI 고려 | 자연어 유지 + 시작 안내 배너만 추가 | 번호 메뉴는 Function Calling의 존재 의의와 상충 |
| (중간 시행착오) `client.chats.create()` 세션 재사용으로 구현 | 최종적으로 `client.interactions.create(previous_interaction_id, store=True)`로 재구현 | 처음엔 `interactions.create`/`store=True`를 OpenAI Responses API 패턴으로 잘못 판단했으나, 실제로 Gemini SDK(`google-genai` 2.3.0+)에 동일한 이름의 **Interactions API**가 존재함을 확인하고 교체 |

## 8. 실행 방법

두 폴더가 완전히 독립적이라, 각 폴더 안에서 각자 설치/실행한다.

**기본 CLI (순수 텍스트, 개발 중단)**
```bash
cd 기본_CLI
pip install -r requirements.txt
python main.py
```

**가계부 도우미 (Claude Code 스타일 UI, 계속 발전 중)**
```bash
cd 가계부_도우미
pip install -r requirements.txt
python app.py
```

각 폴더 안의 `.env`에 `GEMINI_API_KEY`가 이미 들어있으며(두 폴더 모두 동일한 키를 각자 들고 있음), VSCode 통합 터미널 사용을 권장 (콘솔 인코딩 이슈로 두 스크립트 모두 `sys.stdout.reconfigure(encoding="utf-8")` 처리됨).

## 9. 사용법 (예시)

번호/메뉴 선택 없이 전부 자연어로 입력하면 된다. 실행하면 뜨는 안내 배너에도 아래 내용이 요약되어 있다.

| 하고 싶은 것 | 이렇게 말하면 됨 |
|---|---|
| 거래 등록 | "오늘 점심 만원 썼어", "어제 커피값 4천원", "월급 300만원 들어왔어" |
| 예산만 설정 (거래 없이) | "식비 예산 30만원으로 잡아줘" |
| 거래 + 예산 동시 등록 | "차량 유지비로 세차 만원 등록하고 예산은 20만원으로 잡아줘" |
| 검색 | "이번 달 식비 내역 보여줘", "커피 들어간 거래 찾아줘" |
| 수정 (id 몰라도 됨) | "어제 그 거래 7천원으로 바꿔줘", "점심 먹은 거 설명을 회식으로 바꿔줘" |
| 삭제 (id 몰라도 됨) | "방금 등록한 거 지워줘", "커피 거래 삭제해줘" |
| 예산 조회 (카테고리 하나) | "식비 예산 얼마 남았어?" |
| 예산 조회 (전체) | "지금 예산 얼마 남았어?" |
| JSON 파일로 저장 | "이번 달 거래 내역 json으로 저장해줘" |
| 월별 보고서(Markdown) | "8월 내역 정리해줘" |
| 새 카테고리 추가 | "차량 유지비 카테고리 추가해줘" |
| 카테고리 이름 변경 | "의류비를 옷값으로 이름 바꿔줘" |
| 카테고리 삭제 | "차량 유지비 카테고리 지워줘" (단, '기타'는 삭제 불가) |
| 되돌리기 (`가계부_도우미` 전용) | "방금 그거 취소해줘", "되돌려줘" |
| 도움말 다시 보기 (`가계부_도우미` 전용, 로컬 명령어) | "도움말" |
| 대화 초기화 (`가계부_도우미` 전용, 로컬 명령어) | "새 대화" 또는 "초기화" |
| 종료 | "종료" |

**주의할 점**
- 등록 전에 없는 카테고리를 쓰면 등록이 거부되고, 먼저 카테고리를 추가하라고 안내한다.
- 수정/삭제 시 조건(날짜/카테고리/설명)에 맞는 거래가 여러 건이면, 어떤 걸 말하는지 더 구체적으로 알려달라고 되묻는다.
- "오늘", "어제", "이번 달" 같은 상대적 표현은 실행 시점의 실제 날짜를 기준으로 자동 변환된다.
- 결과 파일(JSON 내보내기, 월별 보고서)은 각 폴더 안의 `data/` 폴더에 저장된다.
- "도움말"/"새 대화"/"초기화"는 Gemini를 거치지 않고 `가계부_도우미/app.py`가 로컬에서 바로 처리하는 명령어다.
- `가계부_도우미`는 예산을 초과한 카테고리를 표에서 ⚠로 표시하고, 카테고리별 예산 조회 시 사용률 막대와 지출 비중 차트를 함께 보여준다.

## 10. 현재 상태 요약 (세션 마무리 시점)

**완료된 것**
- `가계부_도우미`: tool 11개(원본 7개 + 카테고리 관리 3개 + undo), 대화 영구 기억(`data/session.json`), 예산 초과 경고/사용률 막대/지출 비중 차트, '도움말'·'새 대화' 로컬 명령어
- UI를 Panel(박스) 기반에서 `console.rule()`/평문/`Table.grid` 기반으로 전환 — 좁은 터미널에서도 깨지지 않도록 개선, 40칸 너비로 강제 테스트해서 확인 완료
- `기본_CLI`: 여기서 개발 중단, 스냅샷으로만 유지 (더 이상 갱신 안 함)
- GitHub 공개 레포에 전부 커밋/푸시됨: https://github.com/snail5039-code/personal-financial-management (`.env`/`data/`는 `.gitignore`로 제외)

**미해결/확인 필요**
- 사용자가 실제 콘솔에서 창을 줄였을 때 여전히 레이아웃이 흐트러지는 현상이 있었음. 코드 자체는 40칸 강제 테스트로 정상 렌더링 확인됨 → **원인이 "터미널이 실시간 크기 변경을 파이썬에 제대로 안 알려주는 것"인지, 다른 문제인지 다음 세션에서 재확인 필요** (스크립트 실행 *전에* 원하는 창 크기로 맞춰놓고 실행했을 때도 깨지는지 확인하는 게 다음 진단 포인트)

**다음에 고려할 방향 (합의된 우선순위)**
- 우선은 계속 터미널(rich) 안에서 다듬기
- 어느 정도 다듬어지면 `textual` 라이브러리로 전역 앱(마우스/스크롤 지원되는 미니 GUI)으로 전환하는 것을 고려하기로 함 (아직 미착수)

**커밋 규칙**: 한국어 + `feat:`/`fix:`/`refactor:` 같은 conventional 접두사 유지
