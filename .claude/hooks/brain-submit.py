#!/usr/bin/env python3
"""Hook Stop: registra aprendizado no Project Brain ao encerrar o turno."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "project-brain"))

from tools.brain_loop import submit_on_stop  # noqa: E402


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        data = {}

    if data.get("stop_hook_active"):
        print("{}")
        return 0

    result = submit_on_stop(hook_data=data)
    if result.get("ok"):
        msg = (
            f"Project Brain: tarefa #{result['task_id']} registrada "
            f"({result.get('evidence_count', 0)} evidência(s))."
        )
        learning = result.get("learning")
        if learning:
            msg += (
                f" Learning: {learning['rules']} rule(s), "
                f"{learning['patterns']} pattern(s), {learning['lessons']} lesson(s)."
            )
        print(json.dumps({"systemMessage": msg}, ensure_ascii=False))
    else:
        print("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
