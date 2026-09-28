"""Canvas operations: validation and last-writer-wins merging.

Mirrors `frontend/src/canvas/model.ts`. The document is a map of element entries
keyed by id; each entry carries a Lamport `version`, and deletions are kept as
tombstones, so applying operations is commutative and idempotent.
"""

from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter, ValidationError

from .models import MAX_TEXT, CamelModel

MAX_CHANGES_PER_OPERATION = 500
MAX_STROKE_POINTS = 20_000
MAX_ELEMENTS = 5_000

ComponentType = Literal[
    "service", "rounded", "rectangle", "ellipse", "text", "sticky", "boundary", "icon",
    "sql-db", "nosql-db", "cache", "object-storage", "warehouse",
    "queue", "stream", "pubsub",
    "client", "browser", "mobile", "api-gateway", "load-balancer", "cdn", "external-api",
    "server", "worker", "function", "cluster",
    "llm", "embedding", "vector-db", "agent",
]  # fmt: skip


class Stamp(CamelModel):
    clock: int = Field(ge=0)
    actor: str


class _ElementBase(CamelModel):
    id: str = Field(min_length=1, max_length=200)
    z: float
    group_id: str | None = None
    version: Stamp
    created_by: str
    created_at: str
    updated_by: str


class ShapeElement(_ElementBase):
    kind: Literal["shape"]
    component_type: ComponentType
    x: float
    y: float
    w: float = Field(gt=0)
    h: float = Field(gt=0)
    label: str = Field(max_length=MAX_TEXT)
    description: str | None = Field(default=None, max_length=MAX_TEXT)
    fill: str | None = None


class Endpoint(CamelModel):
    element_id: str | None = None
    anchor: Literal["auto", "top", "right", "bottom", "left"] | None = None
    x: float
    y: float


class ConnectorElement(_ElementBase):
    kind: Literal["connector"]
    from_: Endpoint = Field(alias="from")
    to: Endpoint
    routing: Literal["straight", "elbow", "curved"]
    arrow_start: bool
    arrow_end: bool
    label: str = Field(max_length=MAX_TEXT)
    dashed: bool
    color: str
    width: Literal[1, 2, 3]


class StrokeElement(_ElementBase):
    kind: Literal["stroke"]
    tool: Literal["pen", "highlighter"]
    points: list[float] = Field(max_length=MAX_STROKE_POINTS * 2)
    color: str
    width: float = Field(gt=0)


CanvasElement = Annotated[ShapeElement | ConnectorElement | StrokeElement, Field(discriminator="kind")]


class PutChange(CamelModel):
    type: Literal["put"]
    element: CanvasElement


class DeleteChange(CamelModel):
    type: Literal["delete"]
    id: str
    version: Stamp


Change = Annotated[PutChange | DeleteChange, Field(discriminator="type")]


class CanvasOperation(CamelModel):
    id: str = Field(min_length=1, max_length=200)
    actor_id: str
    changes: list[Change] = Field(max_length=MAX_CHANGES_PER_OPERATION)


_operation_adapter = TypeAdapter(CanvasOperation)


class InvalidOperation(ValueError):
    pass


def parse_operation(raw: Any) -> CanvasOperation:
    """Validate a raw operation. Raises InvalidOperation with a short message."""
    try:
        return _operation_adapter.validate_python(raw)
    except ValidationError as exc:
        err = exc.errors()[0]
        where = ".".join(str(p) for p in err.get("loc", ()))
        raise InvalidOperation(f"Invalid operation ({where}): {err.get('msg')}") from None


def entry_for(change: PutChange | DeleteChange) -> tuple[str, dict[str, Any]]:
    """The JSON entry a change writes: the element (camelCase, known fields only) or a tombstone."""
    if isinstance(change, PutChange):
        return change.element.id, change.element.model_dump(by_alias=True, exclude_unset=True)
    return change.id, {"id": change.id, "deleted": True, "version": change.version.model_dump()}


def _stamp_key(entry: dict[str, Any]) -> tuple[int, str]:
    version = entry["version"]
    return version["clock"], version["actor"]


def apply_operation(elements: dict[str, dict[str, Any]], op: CanvasOperation) -> dict[str, dict[str, Any]]:
    """Return a new element map with `op` applied under last-writer-wins rules."""
    result = dict(elements)
    for change in op.changes:
        element_id, entry = entry_for(change)
        current = result.get(element_id)
        if current is None or _stamp_key(entry) > _stamp_key(current):
            result[element_id] = entry
    return result


def is_tombstone(entry: dict[str, Any]) -> bool:
    return entry.get("deleted") is True


def live_count(elements: dict[str, dict[str, Any]]) -> int:
    return sum(1 for e in elements.values() if not is_tombstone(e))
