"""스킬 도구 - skills/ 폴더의 SKILL.md 지시문을 필요할 때만 읽어온다.

규칙을 전부 시스템 지시문에 넣으면 매 요청마다 통째로 실려서 토큰이 낭비되고, 지금 대화와
상관없는 규칙까지 섞여 모델의 판단을 흐린다. 그래서 스킬은 '이름 + 한 줄 설명'만 시스템
지시문에 올려두고(skills_summary_for_prompt), 모델이 필요하다고 판단할 때 read_skill로
본문을 직접 읽어가게 한다.

스킬 하나 = skills/<이름>/SKILL.md 파일 하나. 형식:

    ---
    name: monthly-report
    description: 월말 가계부 정리 절차 (이 한 줄만 시스템 지시문에 올라간다)
    ---

    (여기부터 본문 - 모델이 read_skill로 읽어갈 지시문)

폴더만 추가하면 코드를 안 고쳐도 스킬이 늘어난다. 매번 파일을 새로 읽으므로 커리마를 켜둔
채로 SKILL.md를 고쳐도 다음 호출에 바로 반영된다.

스킬 파일이 깨져 있어도(프론트매터 없음, 인코딩 오류 등) 그 스킬만 조용히 건너뛰고 나머지는
정상 동작한다 - 스킬 하나 때문에 에이전트 전체가 죽는 일은 없어야 한다.
"""

import os
import sys

# PyInstaller로 얼린 실행 파일 안에서는 __file__ 기반 경로가 exe가 실제로 있는 폴더를
# 가리키지 않는다 - sys.executable 기준으로 잡아야 skills를 exe 옆에서 제대로 찾는다.
# exe 안에 넣지 않고 옆에 두는 이유: 설치해서 쓰는 사람도 다시 빌드하지 않고 SKILL.md만
# 추가해서 스킬을 늘릴 수 있어야 한다.
_THIS_DIR = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.dirname(__file__))
SKILLS_DIR = os.path.join(_THIS_DIR, "skills")


def _parse_front_matter(text):
    """SKILL.md 맨 위의 '---' 블록을 (메타 dict, 본문)으로 나눈다.

    pyyaml에 의존하지 않으려고 직접 파싱한다. 스킬 프론트매터는 'key: value' 한 줄짜리
    항목만 쓰므로 이 정도로 충분하다. 프론트매터가 없으면 ({}, 전체 텍스트)를 돌려준다.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    meta = {}
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return meta, "\n".join(lines[i + 1:]).strip()
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip()

    # 닫는 '---'가 없으면 프론트매터로 보지 않는다.
    return {}, text


def _load_one(folder_name):
    """스킬 폴더 하나를 읽어 {name, description, body}로 만든다. 실패하면 None."""
    path = os.path.join(SKILLS_DIR, folder_name, "SKILL.md")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None

    meta, body = _parse_front_matter(text)
    return {
        # 프론트매터에 name이 없으면 폴더명을 쓴다.
        "name": meta.get("name") or folder_name,
        "description": meta.get("description", ""),
        "body": body,
    }


def list_skills():
    """skills/ 폴더의 스킬 목록을 이름순으로 돌려준다. 폴더가 없으면 빈 목록."""
    if not os.path.isdir(SKILLS_DIR):
        return []

    skills = []
    for folder_name in sorted(os.listdir(SKILLS_DIR)):
        if folder_name.startswith("."):
            continue
        skill = _load_one(folder_name)
        if skill is not None:
            skills.append(skill)
    return skills


def skills_summary_for_prompt():
    """시스템 지시문에 붙일 스킬 목록 문구를 만든다. 스킬이 없으면 빈 문자열.

    본문(body)은 여기 넣지 않는다 - 그게 스킬의 핵심이다.
    """
    skills = list_skills()
    if not skills:
        return ""

    lines = [f"- {s['name']}: {s['description']}" for s in skills]
    return (
        "아래는 특정 작업을 할 때 따라야 할 절차가 적힌 '스킬' 목록입니다. "
        "설명을 보고 지금 하려는 일과 관련 있다고 판단되면, 먼저 read_skill로 그 스킬의 "
        "내용을 읽고 거기 적힌 절차를 그대로 따르세요. 관련 없으면 읽지 않아도 됩니다.\n"
        + "\n".join(lines)
    )


# ---------------------------------------------------------------------------
# read_skill
# ---------------------------------------------------------------------------
def read_skill(name):
    """스킬 본문(SKILL.md 지시문)을 읽어온다."""
    skills = list_skills()
    target = next((s for s in skills if s["name"] == name), None)
    if target is None:
        available = ", ".join(s["name"] for s in skills) or "(없음)"
        return {"message": f"'{name}' 스킬을 찾을 수 없습니다. 사용 가능한 스킬: {available}"}

    return {
        "name": target["name"],
        "description": target["description"],
        "instructions": target["body"],
    }


read_skill_tool = {
    "type": "function",
    "name": "read_skill",
    "description": (
        "시스템 지시문에 목록으로 안내된 '스킬' 중 하나의 상세 절차를 읽어온다. "
        "지금 하려는 작업과 관련된 스킬이 목록에 있으면 작업을 시작하기 전에 이 도구로 먼저 "
        "읽고, 돌려받은 instructions에 적힌 절차를 그대로 따른다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "읽을 스킬 이름 (시스템 지시문의 스킬 목록에 있는 이름)"},
        },
        "required": ["name"],
    },
}
