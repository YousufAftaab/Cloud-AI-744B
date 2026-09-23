"""Lightweight task planner: decomposes complex compound goals into structured steps."""

import re
from pc_insider.agent.task_state import TaskState

COMPLEXITY_PATTERNS = [
    re.compile(r'\b(then|after that|next|first|finally|and also)\b', re.IGNORECASE),
    re.compile(r'\b(create|write)\b.*\b(and|then)\b.*\b(run|test|execute)\b', re.IGNORECASE),
    re.compile(r'\b(fix|debug|refactor)\b.*\b(make sure|verify)\b', re.IGNORECASE),
    re.compile(r'\b(step\s*1|1\.\s+.*2\.\s+)', re.IGNORECASE),
]

class Planner:
    def is_complex_goal(self, user_prompt: str) -> bool:
        """Determine if a user request requires multi-step planning."""
        text = user_prompt.strip()
        # Fast path for short queries and greetings
        if len(text.split()) < 5:
            return False
        if text.lower().startswith(("hey", "hello", "hi", "how are you", "who are you", "what is")):
            return False

        for pat in COMPLEXITY_PATTERNS:
            if pat.search(text):
                return True
        return False

    def build_plan_from_prompt(self, user_prompt: str) -> TaskState:
        """Heuristically extract logical steps from a compound user prompt."""
        task = TaskState(goal=user_prompt)

        # Check for numbered list e.g. "1. do X 2. do Y"
        numbered = re.split(r'\d+\.\s+', user_prompt)
        if len(numbered) > 2:
            for item in numbered[1:]:
                clean = item.strip().rstrip(";,.")
                if clean:
                    task.add_step(clean)
            return task

        # Split on conjunctions
        parts = re.split(r'\b(?:then|and then|after that|next)\b', user_prompt, flags=re.IGNORECASE)
        if len(parts) > 1:
            for p in parts:
                clean = p.strip().rstrip(";,.")
                if clean:
                    task.add_step(clean)
            return task

        # Default fallback: single overall step
        task.add_step(user_prompt)
        return task

planner = Planner()
