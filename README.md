# Kaggriculture

Fresh build, scaffolded from a verified-mechanics report and now also a
real observation dump pulled from a live Kaggle run
(`tests/fixtures/sample_observation.json`). `mechanics.py`,
`state.py::size_keeper_pool()`, and the whole parsing layer in `agent.py`
are confirmed against real data, not guessed.

## Layout

```
src/kaggriculture/   the actual logic -- mechanics, state, strategy, agent
notebooks/           run_episode.ipynb -- clone, install, run a real episode
scripts/             build_submission.py, test_harness.py (non-notebook use)
submission/main.py   auto-generated, single-file, ready to submit as-is
tests/               unit tests, incl. tests against a REAL observation
```

## Why there's both `src/` and `submission/main.py`

Kaggle simulation competitions load the submitted file in isolation --
your repo's other files aren't present at grading time. `src/` is split
into modules for readability and testing; `submission/main.py` is the
same code auto-flattened into one file by `scripts/build_submission.py`,
already committed and ready to submit as-is.

**After any change under `src/kaggriculture/`, re-run the build and
commit the new output:**

```bash
python scripts/build_submission.py
```

## What's confirmed against real data -- don't re-derive

- The observation shape: `obs["farms"][obs["player"]]` is your farm;
  `money` lives on the farm dict; `tiles` is a 10x10 grid (list of 10
  rows of 10 cells), not a flat list; a cell is `None` (empty, plantable),
  the string `"LOCKED"` (unbought quadrant), or a dict once something is
  planted/built there; `unlocked_quadrants` is a list of name strings
  (`["NW"]`), not a count; there is exactly one farmer, given as a bare
  `[x, y]` pair with no id
- `mechanics.py` -- action vocabulary, crop yield/decay table, shed cap,
  hire cost formula, shop demand table
- `state.py::size_keeper_pool()` -- verified stable-pool formula
- `strategy.py::harvest_urgency()` -- decay-driven, reads
  `max_lifespan_step` directly instead of inferring decay
- `agent.py` now actually moves the farmer toward the highest-urgency
  task instead of doing nothing -- verified against the real sample
  observation, not just a synthetic one (`tests/test_agent_parsing.py`)

## What's still genuinely open

1. **The shape of an occupied tile.** The one real observation available
   is from turn 0, before anything was planted -- every unlocked cell is
   just `None`. The dict-shape fields in `TileState.from_raw()` (crop,
   yield_units, max_lifespan_step, ...) are carried over from the
   verified-mechanics report as a best guess, not confirmed against a
   real occupied cell yet.
2. **The exact action return format.** `agent()` currently returns a
   single flat list (e.g. `["WEST"]`, `["PLANT", "WHEAT"]`), replacing an
   earlier per-unit-id dict guess now that the real observation shows no
   unit ids at all. Still a guess.

**The fastest way to close both out**: `AGENTS.md` and `README.md` ship
*inside* the installed `kaggle_environments` package. Run this in the
notebook (or any cell with the package installed):

```python
import kaggle_environments, os

pkg_dir = os.path.dirname(kaggle_environments.__file__)
for root, dirs, files in os.walk(pkg_dir):
    if "AGENTS.md" in files:
        print(root)
```

Then `!cat <that path>/AGENTS.md` and `!cat <that path>/README.md`, and
share the output back. That very likely settles both open items directly
instead of more guess-and-test cycles.

**Not implemented yet, on purpose:**
- Selling (`strategy.py::shop_aware_sell_plan` exists but isn't called
  from `agent()`) -- deliberately left out until the return format is
  confirmed, since combining a move/tile-action with a market order in
  one turn isn't confirmed to work
- A real crop-selection heuristic for empty tiles (currently always
  plants WHEAT as a placeholder)
- Multiple farmers / hiring logic (there is exactly one farmer right now;
  parsing is written to handle more if `"farmer"` becomes a list of pairs,
  but that shape is unconfirmed)

## Deliberately left open (tunable -- resolve via real self-play, not a guess)

- `MAX_QUADRANTS` -- prior comments disagreed (2 vs. 3); real 9-game data
  shows all 9 winners reaching a 3rd quadrant by day 9-11, which favors 3,
  but that's not a direct A/B test
- Opening animal ratio -- the one undefeated player in the 9-game sample
  opened 0 goose / 3 cow / 2 sheep; every other winner opened 0/2/2
- Unit ceiling -- 13 held across all 9 real games, never exceeded

## Get this running on Kaggle, no local setup

1. Push to GitHub: `git init && git add . && git commit -m "..." && git
   remote add origin <url> && git push -u origin main`
2. Open `notebooks/run_episode.ipynb` on Kaggle (or paste its cells into
   a new notebook)
3. Turn **Internet ON** in the notebook's settings panel (right sidebar)
4. Edit `REPO_URL` in the first code cell
5. Run All

## Tests

```bash
pip install pytest
pytest tests/
```

`tests/test_agent_parsing.py` runs against a real observation
(`tests/fixtures/sample_observation.json`), not just hand-built synthetic
dicts -- the specific gap this project's earlier 50-test synthetic-obs
suite had. It confirms parsing is correct as far as one step-0 sample
allows; it can't confirm the two open items above.
