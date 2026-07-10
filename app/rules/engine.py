from pathlib import Path
from typing import Any

import yaml

RULES_PATH = Path(__file__).parent / "rules.yaml"

_OPERATORS = {
    "gte": lambda field, value: field >= value,
    "lte": lambda field, value: field <= value,
    "gt": lambda field, value: field > value,
    "lt": lambda field, value: field < value,
    "eq": lambda field, value: field == value,
    "in": lambda field, value: field in value,
}


def load_rules(path: Path = RULES_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)["rules"]


def _rule_matches(rule: dict, context: dict[str, Any]) -> bool:
    # 단일 field/operator/value 규칙과, 여러 조건을 AND로 묶는 conditions 규칙을 모두 지원
    conditions = rule.get("conditions") or [{"field": rule["field"], "operator": rule["operator"], "value": rule["value"]}]
    for cond in conditions:
        field_value = context.get(cond["field"])
        if field_value is None:
            return False
        operator = _OPERATORS[cond["operator"]]
        if not operator(field_value, cond["value"]):
            return False
    return True


def evaluate(context: dict[str, Any], rules: list[dict] | None = None) -> list[dict]:
    rules = rules if rules is not None else load_rules()
    return [{"id": rule["id"], "message": rule["message"]} for rule in rules if _rule_matches(rule, context)]
