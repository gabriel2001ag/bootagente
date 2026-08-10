"""Enumerations shared across Project Brain (seções 7, 14, 15)."""
from __future__ import annotations

from enum import Enum


class TaskStatus(str, Enum):
    NEW = "NEW"
    ANALYZING = "ANALYZING"
    SENIOR_REQUIRED = "SENIOR_REQUIRED"
    SENIOR_RUNNING = "SENIOR_RUNNING"
    LOCAL_EXECUTION = "LOCAL_EXECUTION"
    WAITING_REVIEW = "WAITING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SeniorStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    MANUAL_HANDOFF = "MANUAL_HANDOFF"
    UNAVAILABLE = "UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_ERROR = "AUTH_ERROR"
    QUOTA_EXCEEDED = "QUOTA_EXCEEDED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class Decision(str, Enum):
    AUTO_EXECUTE_ALLOWED = "AUTO_EXECUTE_ALLOWED"
    PATCH_REQUIRES_REVIEW = "PATCH_REQUIRES_REVIEW"
    ANALYSIS_ONLY = "ANALYSIS_ONLY"
    REQUIRES_SENIOR = "REQUIRES_SENIOR"


class TaskCategory(str, Enum):
    VALIDATION = "validation"
    DATABASE = "database"
    UI = "ui"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    UNKNOWN = "unknown"


class AgentResultStatus(str, Enum):
    OK = "OK"
    NO_MATCH = "NO_MATCH"
    REQUIRES_SENIOR = "REQUIRES_SENIOR"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class ExecutionMode(str, Enum):
    SENIOR = "SENIOR"
    WORKSPACE_HANDOFF = "WORKSPACE_HANDOFF"
    LOCAL_FALLBACK = "LOCAL_FALLBACK"
    WAITING_FOR_SENIOR = "WAITING_FOR_SENIOR"


class RoutingMode(str, Enum):
    LOCAL = "LOCAL"
    HYBRID = "HYBRID"
    SENIOR = "SENIOR"
    ANALYSIS_ONLY = "ANALYSIS_ONLY"
    WAITING_FOR_SENIOR = "WAITING_FOR_SENIOR"
