#!/usr/bin/env python3
"""Hook beforeSubmitPrompt: injeta contexto do Project Brain no agente."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "project-brain"))

from tools.brain_loop import inject_context_for_prompt  # noqa: E402


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("{}")
        return 0

    prompt = data.get("prompt") or data.get("user_message") or ""
    brief = inject_context_for_prompt(prompt, hook_data=data)
    if brief:
        print(json.dumps({"additional_context": brief}, ensure_ascii=False))
    else:
        print("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
