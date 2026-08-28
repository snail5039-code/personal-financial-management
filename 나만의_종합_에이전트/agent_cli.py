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
        # --output-format json으로 받으면 답변과 함께 토큰/비용/모델이 같이 온다.
        "first_args": ["{perm}", "{model}", "--session-id", "{session}", "-p",
                       "--output-format", "json"],
        "next_args": ["{perm}", "{model}", "--resume", "{session}", "-p",
                      "--output-format", "json"],
        # 기본값이 이미 쓰기를 막으므로 읽기 전용에는 따로 줄 인자가 없다.
        "read_args": [],
        "write_args": ["--permission-mode", "acceptEdits"],
        "model_flag": "--model",
        "model_examples": ["opus", "sonnet", "haiku", "fable"],
        "json_output": True,
        "login_args": ["auth", "login"],
        "status_args": ["auth", "status"],
        # 플랜 한도는 대화형에서만 볼 수 있다. 여기서 안내할 명령어.
        "limit_command": "/usage",
        "style": "bright_magenta",
    },
    "코덱스": {
        "label": "코덱스",
        "executable": "codex",
        "first_args": ["exec", "{perm}", "{model}"],
        # exec resume은 --sandbox/-m을 받지 않는다.
        # 세션 id를 잡아냈으면 그걸 쓰고, 못 잡았으면 --last로 물러선다.
        # (--last는 다른 터미널에서 돌린 코덱스 대화를 이어받을 수 있다.)
        "next_args": ["exec", "resume", "{session_or_last}"],
        "read_args": ["--sandbox", "read-only"],
        # workspace-write는 작업 폴더 안에서만 쓰기를 허용한다.
        "write_args": ["--sandbox", "workspace-write"],
        "model_flag": "--model",
        "model_examples": ["gpt-5-codex", "o3"],
        # 코덱스의 --json은 이벤트 스트림(JSONL)이라 지금은 쓰지 않는다.
        "json_output": False,
        "login_args": ["login"],
        "status_args": ["login", "status"],
        # 코덱스에서 한도를 보는 명령은 아직 확인하지 못했다. 확인되면 채운다.
        "limit_command": None,
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
# 코덱스가 출력하는 세션 id. 대화를 정확히 이어가려고 걷어내기 전에 잡아둔다.
SESSION_ID_PATTERN = re.compile(r"session id:\s*([0-9a-fA-F-]{32,40})")


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


def run_interactive(agent_key):
    """CLI를 대화형으로 띄워 터미널을 그대로 넘긴다.

    플랜 한도(/usage) 같은 정보는 대화형 화면에서만 볼 수 있어서, 로그인과
    같은 방식으로 출력을 가로채지 않고 자식 프로세스에 터미널을 맡긴다.
    """
    agent = AGENTS[agent_key]
    executable = shutil.which(agent["executable"])
    if executable is None:
        return {"error": f"'{agent['executable']}' 명령을 찾을 수 없습니다."}

    try:
        subprocess.run([executable])
    except OSError as e:
        return {"error": f"{agent['label']} 실행에 실패했습니다: {e}"}
    return {"output": f"{agent['label']}에서 돌아왔습니다."}


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


def _build_args(agent, is_first, session_id, allow_write, model=None):
    template = agent["first_args"] if is_first else agent["next_args"]
    perm = agent["write_args"] if allow_write else agent["read_args"]

    args = []
    for part in template:
        if part == "{perm}":
            args.extend(perm)
        elif part == "{model}":
            if model:
                args.extend([agent["model_flag"], model])
        elif part == "{session}":
            args.append(session_id or "")
        elif part == "{session_or_last}":
            args.append(session_id or "--last")
        else:
            args.append(part)
    return args


def _parse_json_result(stdout):
    """claude --output-format json 응답에서 답변과 사용량을 뽑는다."""
    data = json.loads(stdout)

    if data.get("is_error"):
        return {"error": data.get("result") or "알 수 없는 오류가 발생했습니다."}

    # modelUsage는 {"claude-opus-5[1m]": {...}} 형태라 첫 항목을 쓴다.
    model_usage = data.get("modelUsage") or {}
    model_key = next(iter(model_usage), None)
    info = model_usage.get(model_key, {}) if model_key else {}
    usage = data.get("usage") or {}

    sent = (
        usage.get("input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
    )
    return {
        "output": (data.get("result") or "").strip() or "(빈 응답)",
        "stats": {
            "model": info.get("canonicalModel") or model_key or "알 수 없음",
            "sent_tokens": sent,
            "output_tokens": usage.get("output_tokens", 0),
            "cost_usd": data.get("total_cost_usd") or 0.0,
            "context_window": info.get("contextWindow"),
            "duration_ms": data.get("duration_ms") or 0,
        },
    }


def ask_agent(agent_key, prompt, cwd=None, timeout=600, session_id=None, is_first=True,
              allow_write=False, model=None):
    """CLI에 프롬프트를 넘기고 답변을 받아온다.

    session_id와 is_first를 넘기면 같은 대화를 이어간다(앞선 질문을 기억한다).
    allow_write가 True면 CLI가 작업 폴더의 파일을 직접 고칠 수 있다.
    성공하면 {"output": ..., "stats": {...}}, 실패하면 {"error": ...}를 준다.
    (stats는 사용량을 주는 CLI에서만 들어있다.)
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

    args = _build_args(agent, is_first, session_id, allow_write, model)

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

    if agent["json_output"]:
        try:
            return _parse_json_result(stdout)
        except (json.JSONDecodeError, TypeError):
            # JSON이 아니면 평문으로 온 것이므로 그대로 보여준다.
            pass

    # codex는 답변을 stderr로 내보내기도 해서 stdout이 비면 stderr를 쓴다.
    raw = stdout or stderr
    answer = _clean_output(raw, prompt)
    result = {"output": answer or "(빈 응답)"}

    # 세션 id를 찾으면 알려준다. 다음 질문에서 이 대화를 정확히 이어가는 데 쓴다.
    found = SESSION_ID_PATTERN.search(stderr or "") or SESSION_ID_PATTERN.search(raw)
    if found:
        result["cli_session_id"] = found.group(1)
    return result
