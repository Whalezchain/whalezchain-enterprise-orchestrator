from __future__ import annotations

from typing import Callable, Dict


class ExecutionRegistry:

    def __init__(self):
        self._handlers: Dict[str, Callable] = {}

    def register(
        self,
        action: str,
        handler: Callable,
    ):
        self._handlers[action] = handler

    def resolve(
        self,
        action: str,
    ) -> Callable:

        if action not in self._handlers:
            raise ValueError(
                f"unsupported execution action: {action}"
            )

        return self._handlers[action]

    def list_actions(self):
        return list(self._handlers.keys())


execution_registry = ExecutionRegistry()
