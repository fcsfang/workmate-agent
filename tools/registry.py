from dataclasses import dataclass
from typing import Any, Callable, Dict, List


ToolHandler = Callable[[Dict[str, Any]], Dict[str, Any]]


@dataclass
class ToolSpec:
    name: str
    description: str
    schema: Dict[str, Any]
    handler: ToolHandler
    output_schema: Dict[str, Any]
    side_effects: List[str]
    read_only: bool

    def for_prompt(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema,
            "output_schema": self.output_schema,
            "side_effects": self.side_effects,
            "read_only": self.read_only,
        }

    def schema_export(self) -> Dict[str, Any]:
        return self.for_prompt()


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}

    def register(
        self,
        name: str,
        description: str,
        schema: Dict[str, Any],
        handler: ToolHandler,
        output_schema: Dict[str, Any] = None,
        side_effects: List[str] = None,
        read_only: bool = True,
    ) -> None:
        if name in self._tools:
            raise ValueError(f"tool already registered: {name}")
        self._tools[name] = ToolSpec(
            name=name,
            description=description,
            schema=schema,
            handler=handler,
            output_schema=output_schema or {"type": "object", "properties": {}, "additionalProperties": True},
            side_effects=side_effects or [],
            read_only=read_only,
        )

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def list_prompt_specs(self) -> List[Dict[str, Any]]:
        return [tool.for_prompt() for tool in self._tools.values()]

    def export_schemas(self) -> List[Dict[str, Any]]:
        return [tool.schema_export() for tool in self._tools.values()]

    def names(self) -> List[str]:
        return list(self._tools.keys())
