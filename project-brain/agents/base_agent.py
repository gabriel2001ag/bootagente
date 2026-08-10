"""Base interface for all local deterministic agents (seção 17)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.enums import AgentResultStatus
from core.task import Task


@dataclass
class AgentResult:
    status: AgentResultStatus
    confidence: float
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == AgentResultStatus.OK


class Agent(ABC):
    name: str = "agent"

    @abstractmethod
    def run(self, task: Task, context: Any) -> AgentResult:
        """Execute the agent's deterministic logic against a task/context."""
