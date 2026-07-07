from __future__ import annotations

from pathlib import Path


class AicmoError(Exception):
    pass


class WorkflowSpecError(AicmoError):
    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")


class WorkflowExecutionError(AicmoError):
    def __init__(self, step_id: str, reason: str) -> None:
        self.step_id = step_id
        self.reason = reason
        super().__init__(f"{step_id}: {reason}")


class RunNotFoundError(AicmoError):
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"run not found: {run_id}")


class RunConflictError(AicmoError):
    def __init__(self, run_id: str, reason: str) -> None:
        self.run_id = run_id
        self.reason = reason
        super().__init__(f"run conflict for {run_id}: {reason}")


class StepTransitionError(AicmoError):
    def __init__(self, run_id: str, step_id: str, reason: str) -> None:
        self.run_id = run_id
        self.step_id = step_id
        self.reason = reason
        super().__init__(f"invalid transition for {run_id}/{step_id}: {reason}")


class OnboardingError(AicmoError):
    def __init__(self, client: str, reason: str) -> None:
        self.client = client
        self.reason = reason
        super().__init__(f"onboarding error for {client}: {reason}")
