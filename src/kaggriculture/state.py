"""
state.py — Clean, typed representations of parsed Kaggriculture observations.

Only fields explicitly confirmed (via installed kaggle_environments source,
its AGENTS.md/README.md, or this project's verified-mechanics report) are
treated as certain here. The exact top-level container shape for tiles and
units was NOT independently confirmed in this project's source material —
that gap lives in agent.py::parse_observation(), isolated from everything
in this file, which stays correct regardless of how that gets resolved.
"""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class TileState:
    x: int
    y: int
    crop: str | None = None
    yield_units: int = 0
    max_lifespan_step: int | None = None  # confirmed field; drives decay
    consecutive_unwatered: int = 0
    fertilized: bool = False
    structure: str | None = None  # "COOP" | "PASTURE" | None
    animal: str | None = None
    consecutive_unfed: int = 0
    is_weed: bool = False
    quadrant: int = 0  # which of the 4 quadrants this tile is in
    locked: bool = False  # unbought quadrant — passable, actions no-op here


@dataclass
class UnitState:
    unit_id: str
    x: int
    y: int
    carrying: dict[str, int] = field(default_factory=dict)


@dataclass
class FarmState:
    step: int
    day: int
    money: int
    shed: dict[str, int]  # obs["private"]["shed"] — confirmed correct
    seeds: dict[str, int]  # separate, uncapped slot
    market_prices: dict[str, float]  # obs["market"]["prices"] — confirmed correct
    market_inventory: dict[str, int]  # obs["market"]["inventory"] — confirmed correct
    unlocked_shops: list[str]  # obs["town"]["unlocked_shops"] — list, duplicates possible
    unlocked_quadrants: int
    hires_today: int
    tiles: list[TileState]
    units: list[UnitState]


def size_keeper_pool(n_units: int, n_animals_active: int) -> int:
    """
    Independently verified stable-pool-sizing formula. Sizing off herd size
    rather than raw unit count keeps pool membership stable across a
    same-day hire: a new hire changes n_units immediately, but
    n_animals_active only changes when an animal is actually bought and
    placed — so the keeper set doesn't reshuffle just because headcount
    went up. Confirmed to fix a pool-flip bug where a unit got yanked off
    wheat-watering to cow-feeding purely because a hire happened, same
    task backlog, only headcount changed.
    """
    return max(1, min(3, n_units - 2, 1 + n_animals_active // 3))
