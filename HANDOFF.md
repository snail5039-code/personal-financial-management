# 커리마 세션 인수인계

이 세션(2026-08-28~29)에서 커리마를 "진짜 자비스처럼" 만드는 로드맵을 Phase 1~5까지 전부
구현했다. 그런데 사용자가 실제로 켜서 써보다가 **버그 2개**를 발견했고, 그걸 다음 세션에서
고치기로 하고 여기서 끊었다. 아래 순서대로 읽으면 바로 이어서 작업할 수 있다.

## 지금 프로젝트 상태

- 메인 코드는 `나만의_종합_에이전트/` 폴더 (`기본_CLI/`는 개발 중단된 옛날 버전, 건드리지 않음).
- 기능 목록·구조는 [README.md](README.md), 설정 안 된 것/직접 해야 할 것은 [TODO.md](TODO.md) 참고.
- 로드맵 전체 근거: [커리마 진화 로드맵](https://claude.ai/code/artifact/ca3b191b-bd63-4eb1-bd08-2f5a6a336e08) 아티팩트.
- 전체 기능 테스트 체크리스트: [커리마 테스트 체크리스트](https://claude.ai/code/artifact/d6fc3965-213e-4294-b59a-be737d2eff5a) 아티팩트 (사용자가 지금 이걸 보면서 테스트하다가 아래 버그를 발견함).
- 이번 세션에서 만든 도구가 총 52개. `tools.py`의 `REGISTRY`/`CONFIRM_MESSAGES`가 전체 지도 역할.
- `requirements.txt`에 이번 세션에 새로 추가된 라이브러리가 많음(psutil/pyperclip/Pillow/
  send2trash/pycaw/comtypes/pystray/winotify/watchdog/pyttsx3/sounddevice/numpy/
  faster-whisper/pypdf/python-docx). **사용자가 `pip install -r requirements.txt`를
  다시 돌렸는지부터 확인할 것** — 버그 2번의 가장 유력한 원인이다.

## 버그 1 — 폴더 이름으로 물어보면 엉뚱한 걸 찾음

**재현**: "게임 폴더 안에 뭐 있어?"라고 물어봄.

**실제로 일어난 일** (스크린샷으로 확인됨): Gemini가 `file_search(query='게임')`와
`local_search(query='게임')`를 호출함. 두 도구 다 "게임"이라는 **문자열이 파일명/문서
내용에 포함된 것**만 찾는 도구라서, 바탕화면에 있는 "게임_실행화면1.jpg" 같은 무관한
파일들과 "GestureOS 소개서"처럼 게임을 언급한 문서만 나열됨. 사용자가 원한 "게임이라는
이름의 폴더 안에 들어있는 파일 목록"은 전혀 보여주지 못함.

**원인** (코드로 확인 완료): [tools_file.py](나만의_종합_에이전트/tools_file.py)의
`file_search`는 `os.walk`의 `filenames`만 훑고 `dirnames`(폴더 이름)는 매치 대상이 아니다.
그리고 애초에 "폴더 하나를 지정해서 그 안의 파일/하위폴더 목록을 나열하는" 도구 자체가
없다 — `file_search`(파일명 검색)·`file_open`·`file_read_text`·`file_copy`·`file_move`·
`file_rename`·`file_delete`·`local_search`(문서 내용 검색) 중에 이 역할을 하는 게 없음.

**해야 할 일**:
1. `tools_file.py`에 디렉터리 목록 조회 도구 추가. 예:
   ```python
   def file_list_directory(path):
       """지정한 폴더 바로 안에 있는 파일·하위폴더 목록을 나열한다 (재귀 X)."""
       if not os.path.isdir(path):
           return {"error": f"'{path}' 폴더를 찾을 수 없습니다."}
       entries = os.listdir(path)
       ...
   ```
2. **폴더 자체를 이름으로 찾는 기능도 필요할 가능성 높음** — 사용자가 폴더의 정확한
   경로를 모르고 "게임 폴더"라고만 말하는 게 자연스러운 시나리오이기 때문. `file_search`에
   `dirnames`도 매치하도록 확장하거나, 별도로 `file_find_folder(name)` 같은 걸 만들지 결정
   필요. (개인적으로는 file_search를 확장해서 파일이든 폴더든 이름이 일치하면 같이
   돌려주고, 결과에 `"type": "file"|"folder"`를 표시하는 쪽이 도구를 하나 덜 늘려서 깔끔할
   것 같음 — 다음 세션에서 판단.)
3. `app.py`의 `build_system_instruction()`에 "폴더 안 내용을 물어보면 file_list_directory를
   쓰고, local_search/file_search(내용·이름 검색)로 오해하지 말라"는 안내를 추가해서 Gemini가
   도구를 헷갈리지 않게 할 것.
4. 새 도구는 `tools.py`의 `REGISTRY`에 등록, 위험한 동작이 아니라 `CONFIRM_MESSAGES`는 필요 없음.

## 버그 2 — `tray_app.py`가 켜자마자 바로 꺼짐 (제일 급함)

사용자가 실제로 `python tray_app.py`를 실행했더니 트레이 아이콘이 안 뜨거나 바로 꺼졌다고 함.
이것 때문에 이 세션에서 만든 아래 기능들이 전부 사용자 환경에서는 테스트가 안 된 상태:
- 다운로드 완료 알림
- 선제적 일정 알림(회의 알림)
- 자동 아침 브리핑
- 음성 웨이크워드

**중요**: 이전 세션(나, Claude)이 `tray_app.py`를 subprocess로 여러 번 띄워서 트레이 아이콘이
실제로 뜨고 10초 넘게 정상적으로 살아있는 것, 알림이 실제로 화면에 뜨는 것까지 스크린샷으로
확인했었다. 그런데 **사용자의 실제 실행 환경에서는 재현되지 않음** — 즉 코드 자체보다는
환경 차이(의존성 미설치, 실행 방식, 콘솔 창 문제 등)일 가능성이 높다.

**아직 실제 에러 메시지를 못 봤다.** 다음 세션에서 제일 먼저 할 일은 **추측해서 고치지 말고
사용자에게 실제 에러 메시지부터 받는 것**이다.

**확인할 가설들 (우선순위 순)**:
1. **`pip install -r requirements.txt`를 이번 세션 작업 이후 다시 안 돌렸을 가능성.**
   이번 세션에 pystray/winotify/watchdog/pyttsx3/sounddevice/faster-whisper 등이 새로
   추가됐는데, 이게 하나라도 안 깔려 있으면 `import` 단계에서 바로 죽는다 — "바로 꺼짐"
   증상과 정확히 일치한다. **제일 먼저 이것부터 확인.**
2. 터미널을 안 열어놓고 `tray_app.py`를 더블클릭으로 실행했다면, 에러가 나도 콘솔 창이
   바로 닫혀서 사용자가 메시지를 못 봤을 수 있다. `cmd`나 PowerShell을 먼저 열고
   `python tray_app.py`로 실행해서 창이 안 닫히고 에러가 그대로 보이게 해야 진단 가능.
3. `voice_assistant.py`가 처음 실행될 때 Whisper 모델을 다운로드하는데, 이게 다른 이유로
   실패하면(네트워크, 권한 등) 어떻게 되는지 재점검 필요. 다만 이건 별도 스레드라서 거기서
   예외가 나도 메인 프로세스가 죽지는 않을 것으로 예상됨 (스레드 예외는 전파 안 됨) — 그래도
   확인 필요.
4. `winotify`로 첫 알림(`notify(ASSISTANT_NAME, "백그라운드에서 실행 중입니다...")`)을 보내는
   부분이 메인 스레드에서 실행되는데, 여기서 예외가 나면 `icon.run()`까지 도달을 못 하고
   전체가 죽을 수 있음 — 알림 권한/설정 문제일 가능성.

**다음 세션 진행 순서**:
1. 사용자에게 "cmd나 PowerShell 창을 먼저 열고, 그 안에서 `cd 나만의_종합_에이전트` →
   `python tray_app.py`로 실행해서 무슨 메시지가 뜨는지 그대로 복사해서 보여달라"고 요청.
2. 에러 메시지 받으면 그걸 바탕으로 정확한 원인 픽스.
3. 버그 1(폴더 검색)도 같이 처리.
4. 두 개 다 고치고 나면, 사용자가 TODO.md에 있는 "직접 테스트해봐야 할 것"들을 이어서
   테스트하면 된다.

## 다음 세션 시작 프롬프트 (사용자가 이렇게 말하면 됨)

> 이 프로젝트 [HANDOFF.md](HANDOFF.md) 읽고 이어서 작업해줘. tray_app.py가 켜자마자
> 바로 꺼지는 버그부터 봐줄래? 터미널 열어서 `python tray_app.py` 직접 실행해봤는데
> [여기에 실제로 뜬 에러 메시지나 화면 캡처 붙여넣기].

(에러 메시지를 미리 받아두고 세션을 시작하면 훨씬 빨리 고칠 수 있다.)
