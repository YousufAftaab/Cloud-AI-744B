"""Explicit task state management tracking goals, steps, observations, and status."""

from typing import Optional

class TaskStep:
    def __init__(self, step_id: int, description: str, status: str = "pending"):
        self.step_id = step_id
        self.description = description
        self.status = status  # pending, running, success, failed, skipped

    def to_dict(self) -> dict:
        return {
            "id": self.step_id,
            "description": self.description,
            "status": self.status
        }

class TaskState:
    def __init__(self, goal: str = ""):
        self.goal = goal
        self.steps: list[TaskStep] = []
        self.current_step_id: int = 1
        self.tool_calls_count: int = 0
        self.completed_steps: list[int] = []
        self.failed_steps: list[int] = []
        self.is_active: bool = False

    def reset(self, goal: str = ""):
        self.goal = goal
        self.steps.clear()
        self.current_step_id = 1
        self.tool_calls_count = 0
        self.completed_steps.clear()
        self.failed_steps.clear()
        self.is_active = bool(goal)

    def add_step(self, description: str) -> TaskStep:
        step_id = len(self.steps) + 1
        step = TaskStep(step_id, description, status="pending")
        self.steps.append(step)
        self.is_active = True
        return step

    def get_current_step(self) -> Optional[TaskStep]:
        for s in self.steps:
            if s.step_id == self.current_step_id:
                return s
        return None

    def mark_step_status(self, step_id: int, status: str):
        for s in self.steps:
            if s.step_id == step_id:
                s.status = status
                if status == "success" and step_id not in self.completed_steps:
                    self.completed_steps.append(step_id)
                elif status == "failed" and step_id not in self.failed_steps:
                    self.failed_steps.append(step_id)
                break
        # Advance current step pointer if current step succeeded or skipped
        if self.current_step_id == step_id and status in ("success", "skipped"):
            self.current_step_id += 1

    def is_all_completed(self) -> bool:
        if not self.steps:
            return True
        return all(s.status in ("success", "skipped") for s in self.steps)

    def format_plan_for_context(self) -> str:
        """Format structured task state for LLM context injection."""
        if not self.steps:
            return ""
        lines = [f"[Current Plan: '{self.goal}']"]
        for s in self.steps:
            marker = "⏳" if s.status == "pending" else "▶️" if s.status == "running" else "✅" if s.status == "success" else "❌"
            current_tag = " (CURRENT)" if s.step_id == self.current_step_id else ""
            lines.append(f"  {marker} Step {s.step_id}: {s.description} [{s.status.upper()}]{current_tag}")
        return "\n".join(lines)
