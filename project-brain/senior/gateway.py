from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.task import Task
from senior.codex_workspace_bridge import CodexWorkspaceBridge


@dataclass
class SeniorHandoff:
    task_id: int
    ready: bool
    integration: str
    instruction: str


class SeniorGateway(ABC):
    @abstractmethod
    def prepare(self, task: Task) -> SeniorHandoff:
        """Return an honest handoff descriptor without invoking external UI."""


class VSCodeCodexInvertedGateway(SeniorGateway):
    def __init__(self, bridge: CodexWorkspaceBridge):
        self.bridge = bridge

    def prepare(self, task: Task) -> SeniorHandoff:
        pending_ids = {pending.id for pending in self.bridge.pending()}
        ready = task.id in pending_ids
        return SeniorHandoff(
            task_id=task.id,
            ready=ready,
            integration="codex-vscode-inverted",
            instruction=f"brain senior context {task.id}" if ready else "",
        )

