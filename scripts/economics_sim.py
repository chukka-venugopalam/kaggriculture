"""
Local economics sanity check -- NOT a game simulator.

This does not model tiles, movement, weeds, watering, or shop-unlock RNG
(none of that is confirmed well enough to fake without risking false
confidence). It exercises exactly one thing end to end, using only
confirmed formulas from mechanics.py: does repeatedly following
strategy.py's live-ROI crop selection + market-aware selling actually
self-diversify away from always planting the single highest-base-price
crop, the way the unit tests assert it should in isolation?

Model: N independent 1-tile "farms," each replanted the instant its crop
matures (first_yield_day ignored, always waits to max_yield_day for
max_yield -- the seed-to-harvest cycle CROPS already gives us) and its
full yield sold immediately. Market inventory carries over between
decisions and decays toward equilibrium between harvests via
per_turn_shop_demand at a fixed, generously-unlocked shop set (this
over-states real town demand, which only ramps up slowly across 30 days
as more shops unlock -- so this run is optimistic about how fast prices
recover, and still shows the rotation kicking in).
"""
from __future__ import annotations
import sys
sys.path.insert(0, "src/kaggriculture")

from collections import Counter
from mechanics import CROPS, MARKET_STARTING_INVENTORY, SHOPS, per_turn_shop_demand
from strategy import crop_roi

N_TILES = 25
N_DECISIONS = 60  # ~roughly one 30-day season's worth of replanting cycles, generously
SHOP_SET = list(SHOPS.keys())  # optimistic: every shop type unlocked from turn 1


def main() -> None:
    inventory = {name: MARKET_STARTING_INVENTORY for name in CROPS}
    prices_unused: dict[str, float] = {}
    demand = per_turn_shop_demand(SHOP_SET)  # per-turn drain, confirmed formula

    chosen = Counter()
    sequence: list[str] = []
    for _ in range(N_DECISIONS):
        pick = max(CROPS, key=lambda name: crop_roi(name, prices_unused, inventory))
        chosen[pick] += 1
        sequence.append(pick)

        profile = CROPS[pick]
        # N_TILES tiles all replant this crop and sell the full yield at once.
        inventory[pick] = inventory.get(pick, 0) + N_TILES * profile.max_yield
        # Town demand drains every product for the days this cycle took.
        for name in CROPS:
            drain = demand.get(name, 0.0) * 24 * profile.max_yield_day
            inventory[name] = max(0, inventory[name] - int(drain))

    print(f"{N_DECISIONS} planting decisions across {len(CROPS)} crops:")
    for name, count in chosen.most_common():
        print(f"  {name:12s} chosen {count:3d}x")
    print()
    print("First 20 picks in order:", sequence[:20])
    unique = len(chosen)
    print(f"\n{unique}/{len(CROPS)} distinct crops used", "-- diversifies" if unique > 1 else "-- STUCK ON ONE CROP")


if __name__ == "__main__":
    main()
