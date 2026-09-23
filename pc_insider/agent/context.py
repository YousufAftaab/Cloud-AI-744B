"""Context manager: token budget tracking, observation condensation, and conversational pruning."""

from pc_insider.config import settings
from pc_insider.agent.task_state import TaskState
from pc_insider.memory.profile import pc_profile
from pc_insider.memory.memory_manager import memory_manager

MAX_CONTEXT_CHARS = 12500  # Leaves safety buffer within 4096 tokens

class ContextManager:
    def __init__(self, base_system_prompt: str):
        self.base_system_prompt = base_system_prompt

    def build_system_prompt(self, task_state: TaskState = None, query: str = "") -> str:
        """Compose dynamic system prompt with machine profile, active plan, and relevant memories."""
        sections = [self.base_system_prompt]

        # 1. Machine profile
        try:
            prof_str = pc_profile.to_compact_summary()
            sections.append(prof_str)
        except Exception:
            pass

        # 2. Relevant persistent memories
        if query:
            try:
                mems = memory_manager.search_relevant_memories(query)
                if mems:
                    mem_block = "[Relevant User Memories]:\n" + "\n".join(f"- {m}" for m in mems)
                    sections.append(mem_block)
            except Exception:
                pass

        # 3. Active task state / plan
        if task_state and task_state.is_active:
            plan_str = task_state.format_plan_for_context()
            if plan_str:
                sections.append(plan_str)

        return "\n\n".join(sections)

    def prune_and_assemble(self, system_prompt: str, messages: list[dict]) -> list[dict]:
        """Assemble message payload while enforcing strict character/token budget."""
        assembled = [{"role": "system", "content": system_prompt}]
        budget_remaining = MAX_CONTEXT_CHARS - len(system_prompt)

        chosen_messages = []
        total_used = 0

        for m in reversed(messages):
            content = m.get("content", "")
            clen = len(content)
            if total_used + clen <= budget_remaining:
                chosen_messages.insert(0, m)
                total_used += clen
            elif not chosen_messages:
                # If even the single latest message is large, clamp it
                avail = max(500, budget_remaining)
                trunc_m = dict(m)
                trunc_m["content"] = content[:avail]
                chosen_messages.insert(0, trunc_m)
                total_used += len(trunc_m["content"])
                break
            else:
                break

        pruned_count = len(messages) - len(chosen_messages)
        if pruned_count > 0:
            summary_notice = {
                "role": "system",
                "content": f"[Context Notice: {pruned_count} earlier conversation turn(s) archived to preserve token budget.]"
            }
            assembled.append(summary_notice)

        assembled.extend(chosen_messages)
        return assembled

    def format_tool_observation(self, tool_name: str, result_dict: dict, max_chars: int = 1500) -> str:
        """Format and condense tool result for clean LLM ingestion."""
        if not result_dict.get("success", False):
            err = result_dict.get("error", {})
            return f"[Tool Error in {tool_name}]: {err.get('type', 'Error')} - {err.get('message', 'Unknown error')}"

        data = result_dict.get("data", {})
        # If tool returned structured message or output
        text = ""
        if isinstance(data, dict):
            if "content" in data:
                text = data["content"]
            elif "output" in data:
                text = data["output"]
            elif "stdout" in data:
                text = data["stdout"]
            elif "message" in data:
                text = data["message"]
            else:
                text = str(data)
        else:
            text = str(data)

        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... [{len(text) - max_chars} characters truncated for context efficiency]"

        return f"[Tool Result for {tool_name}]:\n{text}"
