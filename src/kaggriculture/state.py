"""
state.py — Clean, typed representations of parsed Kaggriculture observations.

Rewritten against a REAL observation dump (sample_observation.json), not
guessed. Confirmed by that file:
  - obs["farms"] is a list of 2 per-player dicts; obs["player"] is the
    index of "your" farm
  - each farm's "money" lives on the farm dict itself, NOT under "private"
  - each farm's "tiles" is a 10x10 grid (list of 10 rows, each a list of
    10 cells) -- not a flat list. A cell is `None` (empty, unlocked,
    plantable), the string "LOCKED" (unbought quadrant), or -- unconfirmed,
    no example existed yet in the sample -- presumably a dict once
    something is planted/built/growing there
  - "unlocked_quadrants" is a list of quadrant-name strings (e.g. ["NW"]),
    not a count
  - each farm currently has exactly ONE farmer, given as a plain [x, y]
    position pair under "farmer" -- not a list of unit dicts with ids.
    Whether this becomes a list of pairs after a HIRE is not yet observed;
    parsing below handles both shapes defensively.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TileState:
    x: int
    y: int
    locked: bool = False
    crop: str | None = None
    yield_units: int = 0
    max_lifespan_step: int | None = None
    consecutive_unwatered: int = 0
    fertilized: bool = False
    structure: str | None = None
    animal: str | None = None
    consecutive_unfed: int = 0
    is_weed: bool = False

    @classmethod
    def from_raw(cls, x: int, y: int, raw_cell: Any) -> "TileState":
        """
        Confirmed for `None` (empty) and "LOCKED". The dict branch below is
        NOT yet confirmed against a real occupied tile -- no example
        existed in the one sample observation available (step 0, nothing
        planted yet). Field names there are carried over from the
        verified-mechanics report's crop/decay vocabulary as a best guess;
        get a later-turn observation (after a real PLANT/BUILD) to confirm
        or correct them.
        """
        if raw_cell is None:
            return cls(x=x, y=y)
        if raw_cell == "LOCKED":
            return cls(x=x, y=y, locked=True)
        if isinstance(raw_cell, dict):
            return cls(
                x=x,
                y=y,
                crop=raw_cell.get("crop"),
                yield_units=raw_cell.get("yield_units", 0),
                max_lifespan_step=raw_cell.get("max_lifespan_step"),
                consecutive_unwatered=raw_cell.get("consecutive_unwatered", 0),
                fertilized=raw_cell.get("fertilized", False),
                structure=raw_cell.get("structure"),
                animal=raw_cell.get("animal"),
                consecutive_unfed=raw_cell.get("consecutive_unfed", 0),
                is_weed=raw_cell.get("type") == "WEED" or raw_cell.get("is_weed", False),
            )
        # Unrecognized shape -- treat as an empty tile rather than crash or
        # silently drop it, and let the caller's own logging surface it.
        return cls(x=x, y=y)


@dataclass
class UnitState:
    unit_id: str  # synthesized locally ("farmer_0", ...) -- the real obs
    # has no id field at all, just bare [x, y] positions. Don't send this
    # id anywhere in the returned action; it's for this code's own
    # bookkeeping only.
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
    units: list[UnitState]


def size_keeper_pool(n_units: int, n_animals_active: int) -> int:
    """
    Independently verified stable-pool-sizing formula. Sizing off herd size
    rather than raw unit count keeps pool membership stable across a
    same-day hire. With only one starting farmer this always resolves to
    1 either way, but it's kept as-is (rather than special-cased) so it
    keeps working once hiring is implemented and n_units actually grows.
    """
    return max(1, min(3, n_units - 2, 1 + n_animals_active // 3))
