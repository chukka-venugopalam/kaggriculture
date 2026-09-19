"""
strategy.py — Task generation and prioritization.

Rewritten against the official tile schema (kind-discriminated: "PLANT",
"WEED", "COOP", "PASTURE", or empty). HARVEST priority is driven directly
by max_lifespan_step (decay) for one-time crops -- the single biggest gap
in every prior version of this project.

Known gaps, intentionally not solved here:
- Ongoing-crop (tomato/strawberry) decay isn't modeled: their
  max_lifespan_step is always -1 (the engine tracks their decay trigger
  by cumulative production count, not a step number), and that count
  isn't derivable from a single observation.
- Crop selection for empty tiles is a placeholder (always WHEAT).
- Only the main farmer is assigned a task; hands (once hiring is
  implemented) aren't scheduled yet.
"""

from __future__ import annotations
from dataclasses import dataclass

from mechanics import (
    CROPS,
    MARKET_PARAMS,
    MARKET_STARTING_INVENTORY,
    MAX_CONSECUTIVE_UNFED,
    MAX_CONSECUTIVE_UNWATERED,
    PRICE_FLOOR,
    TILES_PER_UNIT,
    decay_urgency,
    market_price,
    sell_impact,
)
from state import FarmState, TileState


@dataclass
class Task:
    kind: str
    tile: TileState
    urgency: float  # higher = more urgent; used to sort, not a fixed tier


BASE_URGENCY: dict[str, float] = {
    "FEED_CRITICAL": 100.0,
    "WATER_CRITICAL": 95.0,
    "HARVEST_DECAYING": 90.0,
    "PLACE": 80.0,
    "FEED_ROUTINE": 60.0,
    "PLANT_ABUNDANT": 65.0,  # see generate_tasks() -- only used when empty land >= unit count
    "WATER_ROUTINE": 55.0,
    "HARVEST_FRESH": 50.0,
    "CARE": 45.0,
    "DIG": 40.0,
    "BUILD": 35.0,
    "PLANT": 30.0,
    "FERTILIZE": 20.0,
    "COLLECT_FERTILIZER": 10.0,
}


# Any task at or above this urgency represents a genuine, unrecoverable
# loss if ignored this turn (FEED_CRITICAL/WATER_CRITICAL/HARVEST_DECAYING
# all sit here or above; PLACE also clears it but isn't loss-driven).
# Used to gate land-buying: expanding while this backlog is nonzero is
# exactly the pattern behind the confirmed over-expansion collapse (labor
# stayed flat while land tripled, and the original quadrant decayed to
# weeds while units were pulled toward newly-bought land).
CRITICAL_URGENCY_THRESHOLD: float = BASE_URGENCY["HARVEST_DECAYING"]


def critical_backlog_count(tasks: list[Task]) -> int:
    """How many pending tasks are at genuine-loss urgency right now."""
    return sum(1 for t in tasks if t.urgency >= CRITICAL_URGENCY_THRESHOLD)


def harvest_urgency(tile: TileState, current_step: int) -> float:
    """Decay-aware HARVEST urgency for a PLANT tile. Reads
    max_lifespan_step directly rather than inferring decay."""
    urgency = decay_urgency(tile.max_lifespan_step, current_step)
    if urgency > 0:
        return BASE_URGENCY["HARVEST_DECAYING"] + min(urgency, 10.0) * max(tile.yield_units, 1)
    if tile.yield_units > 0:
        return BASE_URGENCY["HARVEST_FRESH"]
    return 0.0


def generate_tasks(farm: FarmState) -> list[Task]:
    tasks: list[Task] = []

    # If there's at least as much unclaimed empty land as there are units
    # to work it, treat expansion (PLANT) as competitive with routine
    # upkeep instead of always losing to it. Without this, a small
    # established cluster of planted tiles generates recurring
    # WATER/HARVEST obligations that permanently outrank PLANT (30 <
    # WATER_ROUTINE's 55), so every unit gets absorbed into maintaining
    # the same few tiles forever and expansion never happens. Confirmed
    # in a real run: 4 units settled onto exactly 4 tiles and never grew
    # past them -- 21 of 25 NW tiles sat untouched the whole episode.
    # PLANT_ABUNDANT still loses to anything that risks an actual loss
    # (FEED_CRITICAL/WATER_CRITICAL/HARVEST_DECAYING/PLACE) -- only
    # routine upkeep yields to it.
    n_units = 1 + len(farm.hands)
    empty_count = sum(1 for t in farm.tiles if not t.locked and t.kind is None)

    # CRITICAL, confirmed-fixed here: fix #4 above (PLANT_ABUNDANT) had no
    # ceiling -- as long as empty_count >= n_units, it kept pushing units
    # to claim more land forever, regardless of how much was already
    # planted. Combined with land-buying, this is exactly what produced
    # the real over-expansion collapse: land tripled, labor stayed flat,
    # and the original quadrant decayed to weeds while units kept
    # chasing new empty tiles. Ceiling: once already-planted tiles reach
    # what this labor force can sustainably maintain (TILES_PER_UNIT,
    # mechanics.py -- derived from the one confirmed-good 25-tile/4-unit
    # data point), PLANT drops back to its low base priority so units
    # focus on upkeep of what's already planted instead of continuing to
    # expand past their own maintenance capacity.
    planted_count = sum(1 for t in farm.tiles if not t.locked and t.kind == "PLANT")
    labor_capacity = n_units * TILES_PER_UNIT
    room_to_expand = empty_count >= n_units
    under_labor_cap = planted_count < labor_capacity
    plant_urgency = (
        BASE_URGENCY["PLANT_ABUNDANT"] if (room_to_expand and under_labor_cap) else BASE_URGENCY["PLANT"]
    )

    for tile in farm.tiles:
        if tile.locked:
            continue  # every tile action no-ops on an unbought quadrant

        if tile.kind == "WEED":
            tasks.append(Task("DIG", tile, BASE_URGENCY["DIG"]))
            continue

        if tile.kind == "PLANT":
            u = harvest_urgency(tile, farm.step)
            if u > 0:
                tasks.append(Task("HARVEST", tile, u))
            if not tile.watered_today:
                grace_left = MAX_CONSECUTIVE_UNWATERED - tile.consecutive_unwatered
                key = "WATER_CRITICAL" if grace_left <= 1 else "WATER_ROUTINE"
                tasks.append(Task("WATER", tile, BASE_URGENCY[key]))
            if not tile.is_fertilized(farm.day):
                tasks.append(Task("FERTILIZE", tile, BASE_URGENCY["FERTILIZE"]))
            continue

        if tile.kind in ("COOP", "PASTURE"):
            if tile.animal is None:
                tasks.append(Task("PLACE", tile, BASE_URGENCY["PLACE"]))
            else:
                if tile.yield_units > 0:
                    tasks.append(Task("HARVEST", tile, BASE_URGENCY["HARVEST_FRESH"]))
                if not tile.fed_today:
                    grace_left = MAX_CONSECUTIVE_UNFED - tile.consecutive_unfed
                    key = "FEED_CRITICAL" if grace_left <= 1 else "FEED_ROUTINE"
                    tasks.append(Task("FEED", tile, BASE_URGENCY[key]))
                if not tile.cared_today:
                    tasks.append(Task("CARE", tile, BASE_URGENCY["CARE"]))
                if tile.fertilizer_available:
                    tasks.append(Task("COLLECT_FERTILIZER", tile, BASE_URGENCY["COLLECT_FERTILIZER"]))
            continue

        # tile.kind is None -- empty, unlocked, plantable
        tasks.append(Task("PLANT", tile, plant_urgency))

    tasks.sort(key=lambda t: t.urgency, reverse=True)
    return tasks


def crop_roi(crop_name: str, market_prices: dict[str, float], market_inventory: dict[str, int]) -> float:
    """Expected revenue per day of tile occupancy for a fresh planting,
    priced off the LIVE market (current inventory, via the confirmed
    market_price formula) rather than the crop's static base_price. This
    is what makes crop selection self-diversifying: as one crop's market
    gets glutted its price -- and therefore its ROI here -- drops, so the
    next planting decision naturally shifts to whatever's still scarce,
    with no explicit rotation rule needed.

    Conservative for TOMATO/STRAWBERRY: CropProfile doesn't carry a
    confirmed per-cycle yield for their ongoing production, so this only
    prices the guaranteed first harvest (max_yield). Their true ROI is
    higher than this; ranking is still valid, just biased low for them.
    """
    profile = CROPS[crop_name]
    inventory = market_inventory.get(crop_name)
    price = market_price(crop_name, inventory) if inventory is not None else market_prices.get(
        crop_name, profile.base_price
    )
    revenue = profile.max_yield * price - profile.seed_cost
    days = max(1, profile.max_yield_day)
    return revenue / days


def best_plantable_crop(farm: FarmState) -> str | None:
    """Highest live-ROI crop the farm can currently afford to seed (either
    already holding seed, or able to buy at least one)."""
    affordable = [
        name for name, profile in CROPS.items()
        if farm.seeds.get(name, 0) > 0 or farm.money >= profile.seed_cost
    ]
    if not affordable:
        return None
    return max(affordable, key=lambda name: crop_roi(name, farm.market_prices, farm.market_inventory))


# Half of each item's confirmed "anchor throughput" (MARKET_PARAMS' scale
# constant -- the game's own characteristic-volume figure for that item's
# curve) as a per-order batch cap. Meters glut-prone items (MELON/WOOL:
# small scale, steep "sq" above-equilibrium curve) into smaller sells
# across turns instead of dumping the whole shed and crashing the price
# against ourselves in one order; mild items (WHEAT: large scale, "log"
# curve) get a cap high enough it never actually binds.
def _glut_batch_cap(item: str) -> int:
    params = MARKET_PARAMS.get(item)
    if params is None:
        return 100
    scale = params[2]
    return max(10, round(scale * 0.5))


def market_aware_sell_plan(farm: FarmState, max_orders: int = 8) -> list[tuple[str, int]]:
    """
    Rank shed contents by net value (gross revenue minus this sale's own
    price impact) instead of raw quantity, using the confirmed market
    formula (mechanics.py::market_price/sell_impact). Two corrections on
    top of a pure greedy-by-value rank:

    - Glut-prone items are capped per order at _glut_batch_cap() rather
      than sold in full, so a big harvest doesn't crash its own price in
      one shot; the remainder waits for a later, less-impactful turn.
    - Once the shed is nearly full (SHED_CAPACITY=100, and overflow is
      discarded at end-of-day, not held), that metering is dropped and
      everything sells now -- losing money to impact beats losing the
      goods to overflow for free.
    - An item already sitting at PRICE_FLOOR is skipped (not worth
      selling into a crashed market) unless shed pressure forces it out
      anyway.
    """
    shed_total = sum(max(0, int(q or 0)) for q in farm.shed.values())
    pressure = shed_total >= 80

    rows: list[tuple[float, str, int]] = []
    for item, qty in farm.shed.items():
        qty = max(0, int(qty or 0))
        if qty <= 0:
            continue
        inventory = farm.market_inventory.get(item, MARKET_STARTING_INVENTORY)
        price = market_price(item, inventory)
        if price <= PRICE_FLOOR and not pressure:
            continue
        sell_qty = qty if pressure else min(qty, _glut_batch_cap(item))
        net_value = sell_qty * price - sell_impact(item, inventory, sell_qty)
        rows.append((net_value, item, sell_qty))

    rows.sort(key=lambda r: r[0], reverse=True)
    return [(item, qty) for _, item, qty in rows[:max_orders]]
