#!/usr/bin/env python3
"""Fecha tarefa no Brain e registra aprendizado (Agente → Brain).

Uso:
    cd project-brain
    python -m tools.auto_submit "Título da tarefa"
    python -m tools.auto_submit --task-id 42 --file resultado.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tools.brain_loop import close_task


def main() -> int:
    parser = argparse.ArgumentParser(description="Submete tarefa concluída ao Project Brain")
    parser.add_argument("title", nargs="?", default=None, help="Título (opcional se --task-id ou tarefa ativa)")
    parser.add_argument("--description", default="", help="Descrição da tarefa")
    parser.add_argument("--task-id", type=int, default=None, help="ID de tarefa existente")
    parser.add_argument("--file", type=Path, default=None, help="JSON com rules/patterns/lessons/evidence")
    parser.add_argument("--summary", default=None, help="Resumo curto da conclusão")
    parser.add_argument("--json", action="store_true", help="Saída JSON")
    args = parser.parse_args()

    result = close_task(
        title=args.title,
        description=args.description,
        task_id=args.task_id,
        learning_file=args.file,
        summary=args.summary,
    )

    if not result.get("ok"):
        print(f"Erro: {result.get('error', result.get('reason', 'desconhecido'))}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        msg = f"[OK] Tarefa #{result['task_id']} submetida ({result['evidence_count']} evidência(s))"
        learning = result.get("learning")
        if learning:
            msg += (
                f" — learning: {learning['rules']} rule(s), "
                f"{learning['patterns']} pattern(s), {learning['lessons']} lesson(s)"
            )
        print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
