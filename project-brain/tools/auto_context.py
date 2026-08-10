#!/usr/bin/env python3
"""Abre tarefa no Brain e injeta contexto para o agente (Brain → Agente).

Uso:
    cd project-brain
    python -m tools.auto_context "Corrigir filtro de pedidos"
    python -m tools.auto_context "Título" --description "Detalhes" --json
"""
from __future__ import annotations

import argparse
import json
import sys

from tools.brain_loop import open_task


def main() -> int:
    parser = argparse.ArgumentParser(description="Carrega contexto do Brain para o agente")
    parser.add_argument("title", help="Título da tarefa")
    parser.add_argument("--description", default="", help="Descrição opcional")
    parser.add_argument("--task-id", type=int, default=None, help="Reusar tarefa existente")
    parser.add_argument("--json", action="store_true", help="Saída JSON completa")
    args = parser.parse_args()

    result = open_task(args.title, args.description, args.task_id)
    if not result.get("ok"):
        print(f"Erro: {result.get('error')}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(result["brief"])
        print(f"\n[OK] Task #{result['task_id']} — audit: {result['audit_dir']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
