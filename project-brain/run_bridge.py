"""Entry point: python -m bridge.http_server ou python run_bridge.py

Exemplos:
  python run_bridge.py
  python run_bridge.py --port 9000
  python run_bridge.py --project C:\\Users\\eu\\Documents\\erp
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bridge.http_server import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
