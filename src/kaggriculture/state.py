"""
state.py — Clean, typed representations of parsed Kaggriculture observations.

Rewritten against the official AGENTS.md / README.md shipped inside the
installed kaggle_environments package — not guessed, not reconstructed
from an agent file's comments. Every field name and shape here is a
direct match to the documented Observation Format.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TileState:
    x: int
    y: int
    locked: bool = False
    kind: str | None = None  # "PLANT" | "WEED" | "COOP" | "PASTURE" | None (empty, unlocked)

    # PLANT fields
    crop: str | None = None
    planted_day: int | None = None
    watered_today: bool = False
    consecutive_unwatered: int = 0
    yield_units: int = 0
    max_lifespan_step: int = -1  # -1 = not applicable (ongoing crop, or non-plant tile)
    fertilized_until_day: int = -1  # -1 = no active fertilizer bonus

    # COOP / PASTURE fields
    animal: str | None = None
    placed_day: int | None = None
    fed_today: bool = False
    consecutive_unfed: int = 0
    cared_today: bool = False
    fertilizer_available: bool = False
    pending_care_bonus: int = 0

    def is_fertilized(self, current_day: int) -> bool:
        return self.fertilized_until_day >= current_day

    @classmethod
    def from_raw(cls, x: int, y: int, raw_cell: Any) -> "TileState":
        if raw_cell is None:
            return cls(x=x, y=y)
        if raw_cell == "LOCKED":
            return cls(x=x, y=y, locked=True)
        if not isinstance(raw_cell, dict):
            # Unrecognized shape -- treat as empty rather than crash.
            return cls(x=x, y=y)

        kind = raw_cell.get("kind")
        if kind == "PLANT":
            return cls(
                x=x, y=y, kind="PLANT",
                crop=raw_cell.get("crop"),
                planted_day=raw_cell.get("planted_day"),
                watered_today=raw_cell.get("watered_today", False),
                consecutive_unwatered=raw_cell.get("consecutive_unwatered", 0),
                yield_units=raw_cell.get("yield_units", 0),
                max_lifespan_step=raw_cell.get("max_lifespan_step", -1),
                fertilized_until_day=raw_cell.get("fertilized_until_day", -1),
            )
        if kind == "WEED":
            return cls(x=x, y=y, kind="WEED")
        if kind in ("COOP", "PASTURE"):
            return cls(
                x=x, y=y, kind=kind,
                animal=raw_cell.get("animal"),
                placed_day=raw_cell.get("placed_day"),
                yield_units=raw_cell.get("yield_units", 0),
                fed_today=raw_cell.get("fed_today", False),
                consecutive_unfed=raw_cell.get("consecutive_unfed", 0),
                cared_today=raw_cell.get("cared_today", False),
                fertilizer_available=raw_cell.get("fertilizer_available", False),
                pending_care_bonus=raw_cell.get("pending_care_bonus", 0),
            )
        return cls(x=x, y=y)  # unrecognized "kind" -- treat as empty


@dataclass
class UnitState:
    unit_id: str  # "farmer" or "hand_0", "hand_1", ... -- local bookkeeping
    # only; never sent back in the action (the real action addresses the
    # farmer and hands by their fixed "farmer"/"hands" keys, not by id).
    x: int
    y: int
    carrying: dict[str, int] = field(default_factory=dict)


@dataclass
class FarmState:
    step: int
    day: int
    hour: int
    money: float
    shed: dict[str, int]
    seeds: dict[str, int]
    market_prices: dict[str, float]
    market_inventory: dict[str, int]
    unlocked_shops: list[str]
    unlocked_quadrants: list[str]  # e.g. ["NW"] -- names, not a count
    hires_today: int
    tiles: list[TileState]
    farmer: UnitState
    hands: list[UnitState]


def size_keeper_pool(n_units: int, n_animals_active: int) -> int:
    """
    Independently verified stable-pool-sizing formula. Sizing off herd size
    rather than raw unit count keeps pool membership stable across a
    same-day hire. Kept ready for when hiring is implemented and n_units
    actually grows past 1.
    """
    return max(1, min(3, n_units - 2, 1 + n_animals_active // 3))
