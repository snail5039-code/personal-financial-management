# 커리마 — 동작 흐름

`ROADMAP.md`가 "왜 이렇게 됐는지"라면, 이 문서는 **실제로 요청 하나가 들어왔을 때 코드가 어떤
순서로 움직이는지**를 정리한다.

## 1. 전체 그림

```
[사용자]
   │
   ├─ 터미널에 타이핑 ──────────────► app.py (대화형 CLI)
   │
   └─ "커리마"라고 음성으로 호출 ───► tray_app.py → voice_assistant.py
                                              │
                                    (같은 도구 파이프라인을 그대로 재사용)
                                              ▼
                                  tools/__init__.py (TOOLS/FUNCTION_MAP)
                                              │
                          tools/tools_budget.py / tools_todo.py / ... (도메인별 실행)
                                              │
                          data/*.json, google_api/*(구글 API), PC 제어 등
```

`app.py`와 `tray_app.py`는 완전히 다른 프로세스지만, 실제 "명령 처리"는 둘 다
`app.create_interaction()` / `app.execute_tool_call()`을 그대로 호출한다. 도구 목록도
공유(`tools.TOOLS`)하기 때문에, 새 도구를 하나 추가하면 대화형 CLI와 음성 웨이크워드 양쪽에
동시에 반영된다.

## 2. 대화 한 턴의 흐름 (`app.py`)

1. 사용자가 문장을 입력하면 `create_interaction(text, previous_interaction_id)`가
   `client.interactions.create(model=..., input=..., tools=tools.TOOLS, system_instruction=...)`를
   호출한다. `system_instruction`에는 그 순간의 실제 날짜/시각이 매번 새로 박혀서, "오늘"/
   "15분 후" 같은 상대적 표현을 Gemini가 절대 시각으로 변환해 도구를 호출하도록 유도한다.
   여기에 `tools.skills_summary_for_prompt()`가 만든 스킬 목록도 함께 붙는다 — 스킬의 **이름과
   한 줄 설명만** 올라가고, 절차 본문은 올라가지 않는다(아래 8번 참고).
2. 응답(`interaction.steps`)에 `type == "function_call"`이 있으면:
   - 그 도구가 `tools.CONFIRM_MESSAGES`에 등록돼 있으면 `_confirm_risky_action()`으로
     터미널에서 `진행할까요? (y/N)`을 먼저 묻는다. 취소하면 실제 함수는 안 부르고
     "취소됨" 결과만 만든다.
   - 등록 안 된 도구는 바로 `tools.FUNCTION_MAP[name](**args)`를 호출한다.
   - 각 결과를 `{"type": "function_result", "call_id":..., "result":[...]}`로 감싸서 모은다
     (화면 캡처처럼 이미지가 나오는 도구는 여기서 이미지 콘텐츠도 같이 붙인다).
3. 모은 결과들을 다시 `create_interaction(results, interaction.id)`로 넘긴다 — 이게 한 도구
   호출에 대한 "다음 턴"이 된다. `function_call`이 더 없어질 때까지 2~3을 반복한다.
4. 더 이상 `function_call`이 없으면 `interaction.output_text`를 화면에 출력하고,
   `previous_interaction_id`를 이번 `interaction.id`로 갱신해서 다음 사용자 입력을 기다린다.
5. `interaction.id`는 `data/session.json`에도 저장돼서, 프로그램을 껐다 켜도 대화가 이어진다
   ("새 대화"라고 말하면 초기화).

## 3. 트레이 앱(`tray_app.py`)의 백그라운드 스레드 4개

`run()`이 시작되면 데몬 스레드 4개(+ 다운로드 감시용 watchdog Observer)가 동시에 돈다. 전부
"한 번 실패해도 루프 자체가 죽으면 안 된다"는 원칙으로 각자 `try/except`로 감싸져 있다.

| 스레드/컴포넌트 | 주기 | 하는 일 |
|---|---|---|
| `_briefing_loop` | 30초마다 확인 | `data/schedule.json`의 설정 시각이 되면 뉴스 브리핑 알림 |
| `_start_download_watch` (watchdog) | 이벤트 기반 | 다운로드 폴더에 파일이 생기거나(`on_created`) 임시 파일이 완료 파일명으로 바뀌면(`on_moved`) 알림 |
| `_proactive_loop` | 60초마다 확인 | 구글 캘린더 일정이 설정 시간 전이면 알림(한 일정당 한 번만) |
| `voice_assistant.run_loop` | 계속 녹음 | 아래 4절 참고 |

트레이 아이콘 우클릭의 "커리마 열기"는 `_open_kurima()`가 같은 폴더의 `Kurima.exe`(개발
모드면 `python app.py`)를 새 콘솔로 띄우는 것뿐이고, 대화 내용 자체는 그 새 프로세스의
`app.py`가 독립적으로 처리한다(트레이 프로세스와 대화 세션을 공유하지 않음).

## 4. 음성 웨이크워드 흐름 (`voice_assistant.py`)

```
[계속 2.5초씩 녹음]
       │
  faster-whisper(base)로 인식 + hotwords="커리마" 힌트
       │
  "커리마"와 편집거리 ≤1? ──아니오──► 다시 녹음(반복)
       │ 예
      삐 소리
       │
  최대 5초 녹음, 말 끝나고 조용해지면 즉시 종료(무음 감지)
       │
  faster-whisper(small)로 명령 인식
       │
  handle_command(text) ──► create_interaction → function_call 반복 (2절과 동일 로직)
       │
       ├─ 위험한 도구(CONFIRM_MESSAGES)면: "진행할까요?" 되묻기(TTS) → 삐 → 답변 녹음
       │     → "네"류 단어로 시작하면 실행, 아니면(애매해도) 취소
       │
       └─ 최종 답변: 알림(마스코트 아이콘 + 효과음, 60자 넘으면 요약) + 음성(TTS)으로 전달
```

몇 가지 세부사항:
- 녹음된 오디오는 최대 진폭이 일정 이하(거의 무음)가 아니면 목표 크기까지 자동으로
  증폭한다(마이크 볼륨이 낮아도 인식률을 지키기 위함).
- TTS(`pyttsx3`)는 호출마다 새 엔진을 만들고 `pythoncom.CoInitialize()`/`CoUninitialize()`로
  감싼다 — 엔진을 재사용하거나 COM 초기화를 건너뛰면 두 번째 호출부터 실패하는 게 알려진
  문제라, 매번 새로 만드는 쪽을 택했다.

## 5. 구글 연동 흐름

구글 연동은 두 계층으로 나뉜다. `google_api/`는 구글 서버에 실제 요청을 보내는 부품이고
(Gemini용 스키마가 없다), `tools/tools_*.py`가 그걸 Gemini가 호출할 수 있게 포장한다.
Gemini를 거치지 않는 `tray_app.py`의 백그라운드 루프는 `google_api/`를 직접 호출한다.

- `google_api/google_auth.py`가 서비스 공용 인증 헬퍼: `data/<service>_token.json`이 있으면
  그걸로, 없거나 만료됐으면 `credentials.json`으로 OAuth 브라우저 로그인을 새로 띄운다.
- Gmail(`tools/tools_gmail.py`)·구글 캘린더(`tools/tools_calendar.py`)는 이 헬퍼를 통해 서비스
  객체를 얻고, 서비스별로 토큰을 분리 저장해서 권한이 서로 영향을 안 준다.
- `google_api/google_tasks.py`(할일)만 이 헬퍼를 안 쓰고 자기만의 인증 로직을 따로 갖고
  있다(중복 — `ROADMAP.md` 7절에 정리된 미해결 항목).
- 캘린더 일정 추가(`calendar_add_event`)는 `tools.CONFIRM_MESSAGES`에 등록돼 있어서 2/4절의
  확인 흐름을 그대로 타고, 실행되면 `undo.record()`로 되돌리기(일정 삭제)까지 등록된다.

## 6. 되돌리기(`tools/undo.py`) 흐름

`tools/undo.py`는 "무엇을 되돌릴지"를 전혀 모르고, 각 도메인이 작업 직전에 `undo.record(fn)`으로
"되돌리는 함수"만 하나 등록해두는 구조다. `undo_last_action` 도구가 호출되면 마지막으로
등록된 함수 하나만 실행하고 비운다(다단계 undo 아님, 도메인 상관없이 전역 1건).

## 7. 설치 파일 빌드 흐름

```
소스(app.py, tray_app.py, tools/, google_api/, ...)
        │  pyinstaller kurima.spec
        ▼
dist/Kurima/  (Kurima.exe + KurimaTray.exe + _internal/ 공용 의존성)
        │  ISCC.exe kurima_setup.iss
        ▼
installer_output/KurimaSetup.exe
        │  gh release create (수동)
        ▼
GitHub Releases
```

`kurima.spec`은 `MERGE()`로 두 exe가 같은 `_internal` 의존성 폴더를 공유하게 만들어서
faster-whisper/ctranslate2처럼 큰 라이브러리를 두 번 안 담는다. 왜 `sys.executable` 기준
경로 분기, COM 캐시 회피, 콘솔 없는 환경에서의 stdin/stdout 처리, Rich 트루컬러 강제가
필요한지는 `ROADMAP.md` 6절에 정리돼 있다.

## 8. 스킬(`tools/tools_skill.py`) 흐름

도구는 "무엇을 할 수 있는지"를 늘리고, 스킬은 "있는 도구를 어떤 순서로 쓰는지"를 가르친다.
규칙을 전부 `system_instruction`에 넣으면 매 요청마다 통째로 실려서 토큰이 낭비되고, 지금
대화와 무관한 규칙까지 섞여 모델의 판단을 흐린다. 그래서 두 단계로 나눠 보여준다.

1. **목록만 미리 보여준다.** `build_system_instruction()`이 매번 `skills_summary_for_prompt()`를
   불러 `skills/*/SKILL.md`의 프론트매터(`name`, `description`)만 읽어 시스템 지시문 끝에 붙인다.
   본문(`body`)은 여기 넣지 않는다 — 이게 핵심이다.
2. **본문은 필요할 때 모델이 직접 읽어간다.** Gemini가 "이 요청은 이 스킬과 관련 있다"고 판단하면
   `read_skill(name)` 도구를 호출하고, 그 결과(`instructions`)에 적힌 절차를 따라 나머지 도구를
   순서대로 호출한다. 즉 스킬은 2번 흐름(도구 호출 루프) 안에서 평범한 도구 호출 한 번으로 시작된다.

설계상 정한 것:

- **`skills/`는 exe 안이 아니라 exe 옆에 둔다.** 설치해서 쓰는 사람도 다시 빌드하지 않고
  `SKILL.md`만 추가해서 스킬을 늘릴 수 있어야 한다. 그래서 `kurima.spec`의 `datas`가 아니라
  `kurima_setup.iss`의 `[Files]`에서 `{app}\skills`로 복사한다.
- **매번 파일을 새로 읽는다.** 캐시하지 않으므로 커리마를 켜둔 채 `SKILL.md`를 고쳐도 다음
  요청부터 반영된다.
- **스킬 파일이 깨져도 그 스킬만 건너뛴다.** 프론트매터가 없거나 인코딩이 깨졌으면 조용히
  제외하고 나머지는 정상 동작한다. `skills/` 폴더 자체가 없으면 빈 문자열이 돌아와서 스킬
  기능만 꺼지고 나머지 흐름은 이전과 완전히 동일하다.
- **항상 지켜야 하는 규칙은 스킬로 빼지 않는다.** 스킬은 모델이 관련 있다고 판단할 때만 읽히므로,
  금액 부호(지출 양수 / 수입·환불 음수)처럼 틀리면 데이터가 조용히 어긋나는 규칙은
  `system_instruction`에 그대로 남겨둔다.
