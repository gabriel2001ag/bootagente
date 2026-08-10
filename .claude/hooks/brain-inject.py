#!/usr/bin/env python3
"""Hook UserPromptSubmit: injeta contexto do Project Brain no Claude Code."""
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
        data = {}

    prompt = data.get("prompt") or ""
    brief = inject_context_for_prompt(prompt, hook_data=data)
    if brief:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": brief,
                    }
                },
                ensure_ascii=False,
            )
        )
    else:
        print("{}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
