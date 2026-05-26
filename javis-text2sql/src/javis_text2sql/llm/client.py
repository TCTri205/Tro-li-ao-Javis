from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel


SchemaT = TypeVar("SchemaT", bound=BaseModel)


class LLMClient(Protocol):
    async def structured_output(self, system: str, user: str, schema: type[SchemaT]) -> SchemaT:
        ...

    async def generate(self, system: str, user: str) -> str:
        ...
