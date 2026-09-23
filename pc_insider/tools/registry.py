"""Centralized tool registry with parameter validation, structured results, and security integration."""

import time
from typing import Callable, Any, Optional
from pc_insider.security.gate import security_gate
from pc_insider.logger import log_tool_result

class Tool:
    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable[[dict], dict],
        validator: Optional[Callable[[dict], tuple[bool, str]]] = None,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler
        self.validator = validator

    def to_ollama_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable[[dict], dict],
        validator: Optional[Callable[[dict], tuple[bool, str]]] = None,
    ):
        tool = Tool(name, description, parameters, handler, validator)
        self._tools[name] = tool
        return handler

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_schemas(self) -> list[dict]:
        return [t.to_ollama_schema() for t in self._tools.values()]

    def execute(self, name: str, args: dict, bypass_prompt: bool = False) -> dict:
        """Execute a tool through the security gate with timing and structured output."""
        tool = self.get(name)
        if not tool:
            return {
                "success": False,
                "tool": name,
                "data": None,
                "error": {"type": "UnknownTool", "message": f"Tool '{name}' is not registered."}
            }

        # 1. Parameter validation
        if tool.validator:
            ok, err_msg = tool.validator(args)
            if not ok:
                return {
                    "success": False,
                    "tool": name,
                    "data": None,
                    "error": {"type": "ValidationError", "message": err_msg}
                }

        # 2. Security permission gate
        perm = security_gate.check_permission(name, args, bypass_prompt=bypass_prompt)
        if not perm.allowed:
            return {
                "success": False,
                "tool": name,
                "data": None,
                "error": {
                    "type": "PermissionDenied",
                    "message": f"Action blocked by security gate ({perm.risk.value}): {perm.reason}"
                }
            }

        # 3. Execution with timing
        t0 = time.time()
        try:
            res = tool.handler(args)
            duration = time.time() - t0
            success = res.get("success", False)
            err = res.get("error", {}).get("message") if not success and res.get("error") else None
            log_tool_result(name, success, duration, error=err)
            return res
        except Exception as e:
            duration = time.time() - t0
            log_tool_result(name, False, duration, error=str(e))
            return {
                "success": False,
                "tool": name,
                "data": None,
                "error": {"type": "ExecutionException", "message": str(e)}
            }

tool_registry = ToolRegistry()
