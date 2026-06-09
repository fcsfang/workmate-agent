from dataclasses import dataclass
from typing import Any, Callable, Dict, List


ToolHandler = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: Dict[str, Any]
    handler: ToolHandler

    def for_prompt(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "schema": self.schema,
        }


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, name: str, description: str, schema: Dict[str, Any], handler: ToolHandler) -> None:
        if name in self._tools:
            raise ValueError(f"tool already registered: {name}")
        self._tools[name] = ToolSpec(
            name=name,
            description=description,
            schema=schema,
            handler=handler,
        )

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def list_prompt_specs(self) -> List[Dict[str, Any]]:
        return [tool.for_prompt() for tool in self._tools.values()]

    def names(self) -> List[str]:
        return list(self._tools.keys())
