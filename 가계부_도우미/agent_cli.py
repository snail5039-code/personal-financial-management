"""외부 AI CLI(클로드/코덱스)를 불러 쓰는 어댑터.

PC에 설치된 claude / codex 실행 파일을 그대로 호출한다. 각 CLI가 이미 로그인된
계정(구독)을 쓰기 때문에 별도의 API 키나 추가 과금이 필요 없다.

주의: 이 CLI들은 실행한 폴더의 파일을 읽고 수정할 수 있다. 그래서 작업 폴더를
호출하는 쪽에서 명시적으로 넘기도록 만들었다.
"""

import json
import re
import shutil
import subprocess
import uuid

# first_args: 모드에 들어와 처음 물어볼 때 / next_args: 같은 대화를 이어갈 때.
# 이걸 나눠야 "아까 말한 그거" 같은 대화가 통한다. 두 CLI 모두 첫 호출과
# 이어가기 호출의 인자 형태가 달라서 따로 둔다.
#
# {perm}은 읽기/쓰기 권한 인자가 들어갈 자리. 코덱스는 `exec resume`이
# --sandbox를 받지 않아 next_args에 {perm}이 없다. 그래서 권한을 바꿀 때는
# 대화를 새로 시작해야 실제로 반영된다(호출하는 쪽에서 그렇게 처리한다).
AGENTS = {
    "클로드": {
        "label": "클로드",
        "executable": "claude",
        "first_args": ["{perm}", "--session-id", "{session}", "-p"],
        "next_args": ["{perm}", "--resume", "{session}", "-p"],
        # 기본값이 이미 쓰기를 막으므로 읽기 전용에는 따로 줄 인자가 없다.
        "read_args": [],
        "write_args": ["--permission-mode", "acceptEdits"],
        "login_args": ["auth", "login"],
        "status_args": ["auth", "status"],
        "style": "bright_magenta",
    },
    "코덱스": {
        "label": "코덱스",
        "executable": "codex",
        "first_args": ["exec", "{perm}"],
        "next_args": ["exec", "resume", "--last"],
        "read_args": ["--sandbox", "read-only"],
        # workspace-write는 작업 폴더 안에서만 쓰기를 허용한다.
        "write_args": ["--sandbox", "workspace-write"],
        "login_args": ["login"],
        "status_args": ["login", "status"],
        "style": "bright_green",
    },
}

# CLI가 답변 앞뒤에 붙이는 잡음. 답변만 보여주려고 걷어낸다.
NOISE_PREFIXES = (
    "reasoning effort:",
    "reasoning summaries:",
    "session id:",
    "workdir:",
    "model:",
    "provider:",
    "approval:",
    "sandbox:",
    "reading additional input from stdin",
    "openai codex v",
)
# 타임스탬프가 붙은 내부 로그 줄 (예: 2026-08-28T06:08:03.584322Z ERROR ...)
NOISE_LOG_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z\s+(ERROR|WARN|INFO|DEBUG)\b")


def is_available(agent_key):
    """해당 CLI가 PC에 설치돼 있는지 확인한다."""
    return shutil.which(AGENTS[agent_key]["executable"]) is not None


def login(agent_key):
    """CLI 로그인 절차를 이 터미널에 그대로 띄운다.

    브라우저를 여는 대화형 OAuth 절차라 사용자가 직접 완료해야 한다. 그래서
    출력을 가로채지 않고(capture 하지 않고) 자식 프로세스가 터미널을 그대로
    쓰게 둔다. 가로채면 안내 문구도 안 보이고 입력도 먹지 않는다.
    """
    agent = AGENTS[agent_key]
    executable = shutil.which(agent["executable"])
    if executable is None:
        return {"error": f"'{agent['executable']}' 명령을 찾을 수 없습니다."}

    try:
        result = subprocess.run([executable, *agent["login_args"]])
    except OSError as e:
        return {"error": f"{agent['label']} 로그인 실행에 실패했습니다: {e}"}

    if result.returncode != 0:
        return {"error": "로그인이 완료되지 않았습니다."}
    return {"output": f"{agent['label']} 로그인이 끝났습니다."}


def auth_status(agent_key):
    """로그인 상태를 확인한다."""
    agent = AGENTS[agent_key]
    executable = shutil.which(agent["executable"])
    if executable is None:
        return {"error": f"'{agent['executable']}' 명령을 찾을 수 없습니다."}

    try:
        result = subprocess.run(
            [executable, *agent["status_args"]],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"error": f"상태 확인에 실패했습니다: {e}"}

    text = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()

    # 클로드는 JSON으로 상태를 주기 때문에 읽기 좋게 풀어준다.
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"output": _clean_output(text, "") or "(상태 정보 없음)"}

    if data.get("loggedIn"):
        return {"output": f"로그인됨 (방식: {data.get('authMethod', '알 수 없음')})"}
    return {"output": "로그인되어 있지 않습니다. '로그인'이라고 입력해 로그인해주세요."}


def _clean_output(text, prompt):
    """CLI가 붙이는 메타데이터/내부 로그/입력 되울림을 걷어내고 중복 줄을 없앤다."""
    cleaned = []
    seen = set()
    for line in text.splitlines():
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered.startswith(NOISE_PREFIXES) or NOISE_LOG_PATTERN.match(stripped):
            continue
        if stripped in ("--------", "user", prompt.strip()):
            continue
        # CLI가 같은 오류를 두 번 뱉는 경우가 있어 중복은 한 번만 남긴다.
        if stripped and stripped in seen:
            continue
        if stripped:
            seen.add(stripped)
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def new_session_id():
    """모드에 들어갈 때마다 새 대화를 열기 위한 id."""
    return str(uuid.uuid4())


def _build_args(agent, is_first, session_id, allow_write):
    template = agent["first_args"] if is_first else agent["next_args"]
    perm = agent["write_args"] if allow_write else agent["read_args"]

    args = []
    for part in template:
        if part == "{perm}":
            args.extend(perm)
        elif part == "{session}":
            args.append(session_id or "")
        else:
            args.append(part)
    return args


def ask_agent(agent_key, prompt, cwd=None, timeout=600, session_id=None, is_first=True,
              allow_write=False):
    """CLI에 프롬프트를 넘기고 답변을 받아온다.

    session_id와 is_first를 넘기면 같은 대화를 이어간다(앞선 질문을 기억한다).
    allow_write가 True면 CLI가 작업 폴더의 파일을 직접 고칠 수 있다.
    성공하면 {"output": ...}, 실패하면 {"error": ...}를 준다.
    """
    agent = AGENTS[agent_key]
    executable = shutil.which(agent["executable"])
    if executable is None:
        return {
            "error": (
                f"'{agent['executable']}' 명령을 찾을 수 없습니다. "
                f"{agent['label']} CLI가 설치돼 있는지 확인해주세요."
            )
        }

    args = _build_args(agent, is_first, session_id, allow_write)

    try:
        result = subprocess.run(
            [executable, *args, prompt],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            timeout=timeout,
            # stdin을 막지 않으면 codex가 stdin을 마저 읽으려 하면서
            # 사용자가 커리마에 치는 입력을 가로챈다.
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"{timeout}초 안에 답이 오지 않아 중단했습니다."}
    except OSError as e:
        return {"error": f"{agent['label']} 실행에 실패했습니다: {e}"}

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    if result.returncode != 0:
        # 로그인 만료/사용량 초과 같은 안내가 stderr로 오므로 그대로 보여준다.
        return {"error": _clean_output(stderr or stdout, prompt) or "알 수 없는 오류가 발생했습니다."}

    # codex는 답변을 stderr로 내보내기도 해서 stdout이 비면 stderr를 쓴다.
    answer = _clean_output(stdout or stderr, prompt)
    return {"output": answer or "(빈 응답)"}
