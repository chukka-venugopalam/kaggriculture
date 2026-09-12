# Kaggriculture

Fresh build, scaffolded from a verified-mechanics report rather than any
prior agent file's comments. `mechanics.py` and `state.py::size_keeper_pool()`
are confirmed against real `kaggle_environments` source; `strategy.py` is
new, built to model crop decay via `max_lifespan_step` — the single
biggest gap in every prior version — and real per-shop demand instead of
a shop-count proxy.

## Layout

```
src/kaggriculture/   the actual logic -- mechanics, state, strategy, agent
notebooks/           run_episode.ipynb -- clone, install, run a real episode
scripts/             build_submission.py, test_harness.py (non-notebook use)
submission/main.py   auto-generated, single-file, ready to submit as-is
tests/               unit tests for the confirmed-mechanics layer
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

## Get this running on Kaggle, no local setup

1. **Push this repo to GitHub.** Extract the zip, then from inside the
   folder:
   ```bash
   git init
   git add .
   git commit -m "Kaggriculture: fresh mechanics-verified build"
   git remote add origin https://github.com/YOUR_USERNAME/kaggriculture.git
   git push -u origin main
   ```
2. **Open `notebooks/run_episode.ipynb` on Kaggle** -- New Notebook, then
   File > Import Notebook (or paste its cells into a new one).
3. **Turn Internet ON** in the notebook's settings panel (right sidebar)
   -- required for both `git clone` and `pip install`.
4. **Edit `REPO_URL`** in the first code cell to your repo's URL.
5. **Run All.** It clones your repo, installs `kaggle-environments`, runs
   one real episode, and writes `sample_observation.json`.

## What's solid vs. what needs a quick check

**Solid, confirmed against the real engine -- don't re-derive:**
- `mechanics.py` -- action vocabulary, crop yield/decay table, shed cap,
  hire cost formula, shop demand table
- `state.py::size_keeper_pool()` -- verified stable-pool formula (fixes
  the same-day-hire pool-flip bug)
- `strategy.py::harvest_urgency()` -- decay-driven, reads
  `max_lifespan_step` directly instead of inferring decay

**Needs the notebook run above, once** -- both isolated to
`src/kaggriculture/agent.py` and marked `# VERIFY:` inline:
1. The exact top-level shape of `obs` for iterating tiles and units
2. The exact expected return format for actions

**Not implemented yet, on purpose:**
- Unit-to-tile movement/pathing (tasks are assigned with no travel step
  modeled)
- Real crop-selection heuristic for empty tiles (currently always plants
  WHEAT as a placeholder)

## Deliberately left open (tunable -- resolve via real self-play, not a guess)

- `MAX_QUADRANTS` -- prior comments disagreed (2 vs. 3); real 9-game data
  shows all 9 winners reaching a 3rd quadrant by day 9-11, which favors 3,
  but that's not a direct A/B test
- Opening animal ratio -- the one undefeated player in the 9-game sample
  opened 0 goose / 3 cow / 2 sheep; every other winner opened 0/2/2
- Unit ceiling -- 13 held across all 9 real games, never exceeded

Resolve these with real self-play (`env.run([agent_v1, agent_v2])` at
several seeds) once the schema checks above are done.

## Tests

```bash
pip install pytest
pytest tests/
```

Passing tests confirm the arithmetic and control flow are correct -- they
run against hand-built inputs, not the real engine. That's a materially
weaker claim than "works in a real episode," the same gap this project's
prior 50-test synthetic-obs suite had. Only the notebook / `test_harness.py`
run against the real engine closes that gap.
