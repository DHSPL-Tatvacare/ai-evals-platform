"""Analytics data types."""
from __future__ import annotations
from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class PopulationResult:
    run_id: UUID
    rows_inserted: int
    duration_ms: float
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": str(self.run_id),
            "rows_inserted": self.rows_inserted,
            "duration_ms": round(self.duration_ms, 2),
            "errors": self.errors,
        }
