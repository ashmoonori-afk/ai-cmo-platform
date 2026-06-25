from __future__ import annotations

from pathlib import Path


class AicmoError(Exception):
    pass


class WorkflowSpecError(AicmoError):
    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"{self.path}: {self.reason}"


class WorkflowExecutionError(AicmoError):
    def __init__(self, step_id: str, reason: str) -> None:
        self.step_id = step_id
        self.reason = reason
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"{self.step_id}: {self.reason}"


class RunNotFoundError(AicmoError):
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"run not found: {self.run_id}"


class RunConflictError(AicmoError):
    def __init__(self, run_id: str, reason: str) -> None:
        self.run_id = run_id
        self.reason = reason
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"run conflict for {self.run_id}: {self.reason}"


class StepTransitionError(AicmoError):
    def __init__(self, run_id: str, step_id: str, reason: str) -> None:
        self.run_id = run_id
        self.step_id = step_id
        self.reason = reason
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"invalid transition for {self.run_id}/{self.step_id}: {self.reason}"


class OnboardingError(AicmoError):
    def __init__(self, client: str, reason: str) -> None:
        self.client = client
        self.reason = reason
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"onboarding error for {self.client}: {self.reason}"
