"""거래 내역 · 예산 · 카테고리 도구.

데이터는 storage.py(data/transactions.json)에 저장한다.
"""

import datetime
import json
import os

import storage
import undo


def get_categories():
    """현재 등록된 카테고리 목록을 반환한다."""
    return storage.load_data()["categories"]


def _save_snapshot(data):
    """변경 직전 상태를 되돌리기용으로 기억한다."""
    snapshot = undo.copy_of(data)
    undo.record(lambda: storage.save_data(snapshot))


# ---------------------------------------------------------------------------
# 1. transaction_registration
# ---------------------------------------------------------------------------
def transaction_registration(category, amount=None, description=None, budget=None):
    """거래(지출/수입)를 등록하고/하거나 카테고리 예산을 설정한다.
    amount 없이 budget만 주면 거래 없이 예산만 설정한다. 날짜는 자동으로 오늘 날짜가 기록되고, 0원 거래는 등록하지 않는다."""
    if amount is None and budget is None:
        return {"error": "등록할 금액(amount)이나 설정할 예산(budget) 중 하나는 있어야 합니다."}

    data = storage.load_data()

    if category not in data["categories"]:
        return {
            "message": (
                f"'{category}'는 존재하지 않는 카테고리입니다. "
                "category_registration으로 먼저 등록한 뒤 다시 시도해주세요."
            ),
            "categories": data["categories"],
        }

    _save_snapshot(data)

    transaction = None
    if amount is not None:
        if amount == 0:
            return {"error": "0원은 등록할 수 없습니다."}
        transaction = {
            "id": data["next_id"],
            "category": category,
            "date": datetime.datetime.now().strftime("%Y-%m-%d"),
            "amount": amount,
            "description": description or "",
        }
        data["transactions"].append(transaction)
        data["next_id"] += 1

    if budget is not None:
        data["budgets"][category] = budget

    storage.save_data(data)

    if transaction is None:
        return {
            "message": f"'{category}' 카테고리 예산을 {budget}원으로 설정했습니다.",
            "category": category,
            "budget": budget,
        }

    by_category = {}
    for tx in data["transactions"]:
        by_category.setdefault(tx["category"], []).append(tx)
    return by_category


transaction_registration_tool = {
    "type": "function",
    "name": "transaction_registration",
    "description": (
        "새로운 거래(지출 또는 수입)를 등록하고, 필요하면 카테고리 예산도 함께 설정한다. "
        "amount 없이 budget만 주면 거래를 등록하지 않고 예산만 설정한다. "
        "날짜는 오늘 날짜로 자동 기록되며, 금액이 0원이면 등록하지 않는다. "
        "amount와 budget 둘 다 없으면 호출할 수 없다. category는 반드시 이미 등록된 카테고리여야 하며, "
        "없는 카테고리면 category_registration으로 먼저 등록해야 한다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "거래/예산 카테고리. 이미 등록된 카테고리 중 하나여야 한다.",
            },
            "amount": {
                "type": "number",
                "description": (
                    "등록할 거래 금액. 지출과 수입(예: 월급) 모두 이 값으로 등록한다. "
                    "0은 허용되지 않는다. 거래 없이 예산만 설정하려면 생략한다."
                ),
            },
            "description": {
                "type": "string",
                "description": "이 거래에 대한 간단한 설명 (예: '점심 식사', '월급 입금'). amount를 등록할 때만 의미가 있다.",
            },
            "budget": {
                "type": "number",
                "description": (
                    "해당 카테고리에 새로 설정하거나 갱신할 예산(현재 가지고 있는 돈). "
                    "예산을 설정/변경할 필요가 있을 때만 입력하고, 없으면 생략한다."
                ),
            },
        },
        "required": ["category"],
    },
}


# ---------------------------------------------------------------------------
# 2. transaction_search
# ---------------------------------------------------------------------------
def transaction_search(category=None, date=None, query=None):
    """카테고리, 날짜, 검색어를 기준으로 등록된 거래 내역을 검색한다."""
    data = storage.load_data()

    results = []
    for tx in data["transactions"]:
        if category is not None and tx["category"] != category:
            continue
        if date is not None and tx["date"] != date:
            continue
        if query is not None and query not in tx["description"]:
            continue
        results.append(tx)

    if not results:
        return {"message": "일치하는 거래를 찾을 수 없습니다."}

    return [
        {"category": tx["category"], "date": tx["date"], "amount": tx["amount"]}
        for tx in results
    ]


transaction_search_tool = {
    "type": "function",
    "name": "transaction_search",
    "description": (
        "카테고리, 날짜, 검색어를 기준으로 등록된 거래 내역을 검색한다. "
        "조건은 모두 선택 입력이며 입력된 조건만 적용해 필터링한다. "
        "일치하는 거래가 없으면 찾을 수 없다고 안내한다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "검색할 거래 카테고리. 지정하지 않으면 모든 카테고리에서 검색한다.",
            },
            "date": {
                "type": "string",
                "description": "검색할 거래 날짜 (YYYY-MM-DD). 지정하지 않으면 날짜와 무관하게 검색한다.",
            },
            "query": {
                "type": "string",
                "description": "거래 설명에서 찾을 검색어. 지정하지 않으면 설명과 무관하게 검색한다.",
            },
        },
        "required": [],
    },
}


# ---------------------------------------------------------------------------
# 3. transaction_Modification
# ---------------------------------------------------------------------------
def transaction_Modification(id=None, category=None, date=None, amount=None, description=None):
    """id가 있으면 id로 거래를 찾아 category/date까지 새 값으로 바꾸고,
    id가 없으면 category/date를 검색 조건으로 거래를 찾아 amount/description만 새 값으로 바꾼다."""
    data = storage.load_data()

    if id is not None:
        target = next((tx for tx in data["transactions"] if tx["id"] == id), None)
        if target is None:
            return {"message": f"id {id}에 해당하는 거래를 찾을 수 없습니다."}
        if category is not None and category not in data["categories"]:
            return {
                "message": f"'{category}'는 존재하지 않는 카테고리라 변경할 수 없습니다.",
                "categories": data["categories"],
            }
    else:
        if category is None and date is None and description is None:
            return {"message": "id가 없으면 카테고리, 날짜, 설명 중 하나는 알려줘야 거래를 찾을 수 있습니다."}
        candidates = [
            tx for tx in data["transactions"]
            if (category is None or tx["category"] == category)
            and (date is None or tx["date"] == date)
            and (description is None or description in tx["description"])
        ]
        if not candidates:
            return {"message": "수정할 거래를 찾을 수 없습니다."}
        if len(candidates) > 1:
            return {
                "message": "조건에 맞는 거래가 여러 건이라 하나로 특정할 수 없습니다. 좀 더 구체적으로 알려주세요.",
                "candidates": candidates,
            }
        target = candidates[0]

    if amount is not None and amount == 0:
        return {"error": "0원으로는 수정할 수 없습니다."}

    _save_snapshot(data)

    if id is not None:
        if category is not None:
            target["category"] = category
        if date is not None:
            target["date"] = date
        if description is not None:
            target["description"] = description
    if amount is not None:
        target["amount"] = amount

    storage.save_data(data)
    return target


transaction_Modification_tool = {
    "type": "function",
    "name": "transaction_Modification",
    "description": (
        "거래 내역을 수정한다. id를 알고 있으면 id로 정확한 거래를 찾아 category/date/description을 "
        "원하는 값으로 바꾸고 amount도 새 값으로 수정한다. id를 모르면 category/date/description 중 "
        "하나 이상을 거래를 찾기 위한 조건(설명은 부분 일치)으로 사용해서 찾은 뒤 amount를 새 값으로 수정한다. "
        "조건에 맞는 거래가 없으면 찾을 수 없다고 안내하고, 여러 건이 검색되면 더 구체적인 정보를 요청한다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "id": {
                "type": "integer",
                "description": "수정할 거래의 id. 모르면 생략 가능하며, 이 경우 category/date/description으로 거래를 찾는다.",
            },
            "category": {
                "type": "string",
                "description": "id가 있으면 새로 바꿀 카테고리(이미 등록된 카테고리여야 함), id가 없으면 거래를 찾기 위한 카테고리 조건.",
            },
            "date": {
                "type": "string",
                "description": "id가 있으면 새로 바꿀 날짜(YYYY-MM-DD), id가 없으면 거래를 찾기 위한 날짜 조건(YYYY-MM-DD).",
            },
            "amount": {
                "type": "number",
                "description": "새로 바꿀 거래 금액. 0은 허용되지 않는다.",
            },
            "description": {
                "type": "string",
                "description": (
                    "id가 있으면 새로 바꿀 설명, id가 없으면 거래를 찾기 위한 설명 검색어 "
                    "(기존 설명에 이 텍스트가 포함되는 거래를 찾는다)."
                ),
            },
        },
        "required": [],
    },
}


# ---------------------------------------------------------------------------
# 4. transaction_Delete
# ---------------------------------------------------------------------------
def transaction_Delete(id=None, category=None, date=None, query=None):
    """id, 또는 category/date/query(설명 부분 일치) 조합으로 거래를 찾아 삭제한다. 반환값은 삭제 알림 문구뿐이다."""
    data = storage.load_data()

    if id is not None:
        target = next((tx for tx in data["transactions"] if tx["id"] == id), None)
        if target is None:
            return {"message": f"id {id}에 해당하는 거래를 찾을 수 없어 삭제할 수 없습니다."}
    else:
        if category is None and date is None and query is None:
            return {"message": "id가 없으면 카테고리, 날짜, 검색어 중 하나는 알려줘야 삭제할 수 있습니다."}
        candidates = [
            tx for tx in data["transactions"]
            if (category is None or tx["category"] == category)
            and (date is None or tx["date"] == date)
            and (query is None or query in tx["description"])
        ]
        if not candidates:
            return {"message": "일치하는 거래를 찾을 수 없어 삭제할 수 없습니다."}
        if len(candidates) > 1:
            return {
                "message": "조건에 맞는 거래가 여러 건이라 하나로 특정할 수 없습니다. id를 알려주거나 더 구체적으로 말씀해주세요.",
                "candidates": candidates,
            }
        target = candidates[0]

    _save_snapshot(data)
    data["transactions"].remove(target)
    storage.save_data(data)
    return {
        "message": (
            f"id {target['id']} 거래({target['date']}, {target['category']}, "
            f"{target['amount']}원)를 삭제했습니다."
        )
    }


transaction_Delete_tool = {
    "type": "function",
    "name": "transaction_Delete",
    "description": (
        "id 또는 category/date/query(설명 일부 일치) 조합을 기준으로 거래를 삭제한다. "
        "id가 있으면 바로 그 거래를 삭제하고, 없으면 category/date/query로 거래를 찾아 삭제한다. "
        "조건에 맞는 거래가 없으면 삭제할 수 없다고 안내하고, 여러 건이 검색되면 더 구체적인 정보를 요청한다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "id": {
                "type": "integer",
                "description": "삭제할 거래의 id. 모르면 생략하고 category/date/query로 찾는다.",
            },
            "category": {
                "type": "string",
                "description": "삭제할 거래를 찾기 위한 카테고리 조건.",
            },
            "date": {
                "type": "string",
                "description": "삭제할 거래를 찾기 위한 날짜 조건 (YYYY-MM-DD).",
            },
            "query": {
                "type": "string",
                "description": "삭제할 거래를 찾기 위한 검색어. 거래 설명에 이 텍스트가 포함되는 거래를 찾는다.",
            },
        },
        "required": [],
    },
}


# ---------------------------------------------------------------------------
# 5. transaction_Budget_Management
# ---------------------------------------------------------------------------
def _budget_status(data, category, date):
    budget = data["budgets"].get(category)
    used_amount = sum(
        tx["amount"] for tx in data["transactions"]
        if tx["category"] == category and (date is None or tx["date"] == date)
    )
    return {
        "category": category,
        "date": date or datetime.datetime.now().strftime("%Y-%m-%d"),
        "budget": budget,
        "used_amount": used_amount,
        "remaining_amount": budget - used_amount,
    }


def transaction_Budget_Management(category=None, date=None):
    """카테고리에 설정된 예산에서 사용 금액을 뺀 남은 돈을 계산한다.
    category를 생략하면 예산이 설정된 모든 카테고리의 남은 돈을 보여준다."""
    data = storage.load_data()

    if category is None:
        if not data["budgets"]:
            return {"message": "설정된 예산이 없습니다."}
        return [_budget_status(data, cat, date) for cat in data["budgets"]]

    if category not in data["categories"]:
        return {"message": f"'{category}'는 존재하지 않는 카테고리라 예산을 찾을 수 없습니다."}

    if category not in data["budgets"]:
        return {"message": f"'{category}' 카테고리에 설정된 예산이 없어 찾을 수 없습니다."}

    return _budget_status(data, category, date)


transaction_Budget_Management_tool = {
    "type": "function",
    "name": "transaction_Budget_Management",
    "description": (
        "카테고리별로 설정된 예산(현재 가지고 있는 돈)에서 등록된 거래 금액을 뺀 남은 돈을 계산한다. "
        "category를 생략하면 예산이 설정된 모든 카테고리의 남은 돈을 함께 보여준다. "
        "date를 지정하면 그 날짜의 거래만으로 사용 금액을 계산하고, 지정하지 않으면 해당 카테고리의 "
        "전체 거래 금액으로 계산한다. 존재하지 않는 카테고리이거나 예산이 설정되지 않았으면 찾을 수 없다고 안내한다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "예산을 확인할 카테고리. 생략하면 예산이 설정된 모든 카테고리를 보여준다.",
            },
            "date": {
                "type": "string",
                "description": (
                    "사용 금액을 계산할 날짜 (YYYY-MM-DD). 지정하지 않으면 해당 카테고리의 "
                    "전체 거래 금액으로 계산한다."
                ),
            },
        },
        "required": [],
    },
}


# ---------------------------------------------------------------------------
# 6. transaction_Save_Json
# ---------------------------------------------------------------------------
def transaction_Save_Json(id=None, category=None, date=None, query=None):
    """id 또는 category/date/query 조건에 맞는 거래 내역을 JSON 파일로 저장한다."""
    data = storage.load_data()

    if id is not None:
        matched = [tx for tx in data["transactions"] if tx["id"] == id]
    else:
        matched = [
            tx for tx in data["transactions"]
            if (category is None or tx["category"] == category)
            and (date is None or tx["date"] == date)
            and (query is None or query in tx["description"])
        ]

    if not matched:
        return {"message": "조건에 맞는 거래 내역이 없어 JSON 파일로 저장할 수 없습니다."}

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"transactions_export_{timestamp}.json"
    filepath = os.path.join(os.path.dirname(__file__), "data", filename)

    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(matched, f, ensure_ascii=False, indent=2)

    return {
        "message": f"{len(matched)}건의 거래 내역을 '{filepath}' 파일로 저장했습니다.",
        "file_path": filepath,
        "transactions": matched,
    }


transaction_Save_Json_tool = {
    "type": "function",
    "name": "transaction_Save_Json",
    "description": (
        "id 또는 category/date/query(설명 부분 일치) 조건에 맞는 거래 내역을 JSON 파일로 저장해서 "
        "다운로드할 수 있게 한다. id가 있으면 해당 거래만 저장하고, 없으면 category/date/query로 필터링해서 "
        "저장한다. 아무 조건도 없으면 등록된 전체 거래 내역을 저장한다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "id": {
                "type": "integer",
                "description": "저장할 특정 거래의 id. 지정하면 이 거래 하나만 저장한다.",
            },
            "category": {
                "type": "string",
                "description": "저장할 거래를 찾기 위한 카테고리 조건.",
            },
            "date": {
                "type": "string",
                "description": "저장할 거래를 찾기 위한 날짜 조건 (YYYY-MM-DD).",
            },
            "query": {
                "type": "string",
                "description": "저장할 거래를 찾기 위한 검색어 (설명에 포함되는 텍스트).",
            },
        },
        "required": [],
    },
}


# ---------------------------------------------------------------------------
# 7. monthly_Transaction_History
# ---------------------------------------------------------------------------
def monthly_Transaction_History(month):
    """month(YYYY-MM)에 해당하는 거래 내역을 카테고리별로 묶어 마크다운 보고서로 저장한다."""
    data = storage.load_data()
    matched = [tx for tx in data["transactions"] if tx["date"].startswith(month)]

    if not matched:
        return {"message": f"{month}에 해당하는 거래 내역이 없습니다."}

    by_category = {}
    for tx in matched:
        by_category.setdefault(tx["category"], []).append(tx)

    lines = [f"# {month} 거래 내역", ""]
    total = 0
    for category, txs in by_category.items():
        category_total = sum(tx["amount"] for tx in txs)
        total += category_total
        lines.append(f"## {category} (소계: {category_total}원)")
        lines.append("")
        lines.append("| 날짜 | 금액 | 설명 |")
        lines.append("|---|---|---|")
        for tx in sorted(txs, key=lambda t: t["date"]):
            lines.append(f"| {tx['date']} | {tx['amount']}원 | {tx['description']} |")
        lines.append("")
    lines.append(f"**총 합계: {total}원**")

    markdown = "\n".join(lines)

    filename = f"monthly_report_{month}.md"
    filepath = os.path.join(os.path.dirname(__file__), "data", filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(markdown)

    return {
        "message": f"{month} 거래 내역을 '{filepath}' 파일로 저장했습니다.",
        "file_path": filepath,
        "markdown": markdown,
    }


monthly_Transaction_History_tool = {
    "type": "function",
    "name": "monthly_Transaction_History",
    "description": "월별 거래 내역을 조회하여 MarkDown 문서로 만들어서 저장한다",
    "parameters": {
        "type": "object",
        "properties": {
            "month": {
                "type": "string",
                "description": "조회할 거래 월 내역 (YYYY-MM 형식, 예: '2026-08')",
            },
        },
        "required": ["month"],
    },
}


# ---------------------------------------------------------------------------
# 8. category_registration
# ---------------------------------------------------------------------------
def category_registration(category):
    """새로운 카테고리를 카테고리 목록에 추가한다. 이미 있으면 등록하지 않는다."""
    data = storage.load_data()

    if category in data["categories"]:
        return {
            "message": f"'{category}'는 이미 존재하는 카테고리입니다.",
            "categories": data["categories"],
        }

    _save_snapshot(data)
    data["categories"].append(category)
    storage.save_data(data)
    return {
        "message": f"'{category}' 카테고리를 추가했습니다.",
        "categories": data["categories"],
    }


category_registration_tool = {
    "type": "function",
    "name": "category_registration",
    "description": "새로운 카테고리를 카테고리 목록에 등록한다. 이미 존재하는 카테고리면 등록하지 않고 안내한다.",
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "새로 등록할 카테고리 이름",
            },
        },
        "required": ["category"],
    },
}


# ---------------------------------------------------------------------------
# 9. category_Modification
# ---------------------------------------------------------------------------
def category_Modification(old_category, new_category):
    """기존 카테고리 이름을 새 이름으로 바꾸고, 관련된 거래/예산도 함께 옮긴다."""
    data = storage.load_data()

    if old_category not in data["categories"]:
        return {"message": f"'{old_category}' 카테고리를 찾을 수 없습니다."}
    if new_category in data["categories"]:
        return {"message": f"'{new_category}'는 이미 존재하는 카테고리라 이름을 바꿀 수 없습니다."}

    _save_snapshot(data)
    data["categories"] = [
        new_category if c == old_category else c for c in data["categories"]
    ]
    for tx in data["transactions"]:
        if tx["category"] == old_category:
            tx["category"] = new_category
    if old_category in data["budgets"]:
        data["budgets"][new_category] = data["budgets"].pop(old_category)

    storage.save_data(data)
    return {
        "message": f"'{old_category}' 카테고리를 '{new_category}'(으)로 변경했습니다.",
        "categories": data["categories"],
    }


category_Modification_tool = {
    "type": "function",
    "name": "category_Modification",
    "description": (
        "기존 카테고리 이름을 새 이름으로 변경한다. 해당 카테고리로 등록된 모든 거래와 예산도 "
        "새 이름으로 함께 옮겨진다. 기존 카테고리가 없거나 새 이름이 이미 존재하면 변경할 수 없다고 안내한다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "old_category": {
                "type": "string",
                "description": "이름을 바꿀 기존 카테고리",
            },
            "new_category": {
                "type": "string",
                "description": "새로 바꿀 카테고리 이름",
            },
        },
        "required": ["old_category", "new_category"],
    },
}


# ---------------------------------------------------------------------------
# 10. category_Delete
# ---------------------------------------------------------------------------
def category_Delete(category):
    """카테고리를 목록에서 삭제한다. '기타'는 삭제할 수 없고, 해당 카테고리의 거래는 '기타'로 옮겨진다."""
    if category == "기타":
        return {"message": "'기타' 카테고리는 삭제할 수 없습니다."}

    data = storage.load_data()
    if category not in data["categories"]:
        return {"message": f"'{category}' 카테고리를 찾을 수 없어 삭제할 수 없습니다."}

    _save_snapshot(data)
    data["categories"].remove(category)
    for tx in data["transactions"]:
        if tx["category"] == category:
            tx["category"] = "기타"
    data["budgets"].pop(category, None)

    storage.save_data(data)
    return {
        "message": f"'{category}' 카테고리를 삭제했습니다. 해당 카테고리의 거래는 '기타'로 이동했습니다.",
        "categories": data["categories"],
    }


category_Delete_tool = {
    "type": "function",
    "name": "category_Delete",
    "description": (
        "카테고리를 목록에서 삭제한다. '기타'는 삭제할 수 없다. 존재하지 않는 카테고리면 "
        "삭제할 수 없다고 안내한다. 삭제된 카테고리의 거래는 '기타'로 옮겨지고, 예산 설정은 사라진다."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "삭제할 카테고리 이름",
            },
        },
        "required": ["category"],
    },
}


# ---------------------------------------------------------------------------
