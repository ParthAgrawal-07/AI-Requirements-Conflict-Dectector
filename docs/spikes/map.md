# Spike — live-map library at 500 nodes / 2,000 edges (Sprint 0)

| | |
|---|---|
| **Owners** | Dhavni didi, Abhijeet |
| **Question** | Can the live map (US-14) stay usable with 500 requirement nodes and 2,000 finding edges, and with which library? |
| **Candidates** | React Flow 11 (already in `package.json`) · Cytoscape.js 3 |
| **Harness** | `frontend/src/features/prototypes/MapSpike.tsx` — open `/prototypes/map-spike` in `npm run dev` |
| **Status** | Harness ready. **Numbers below must be measured on a team laptop — none have been filled in yet.** |

## Method

1. `npm install` then `npm run dev` in `frontend/`; open `http://localhost:5173/prototypes/map-spike`.
2. Choose the library, keep 500 nodes / 2,000 edges (seeded, so both libraries draw the same graph).
3. Press **Measure**: the page pans the view for 5 s and reports the mean frames per second (`requestAnimationFrame`
   count ÷ elapsed time) and the time from mount to first paint.
4. Press **Apply delta** to add 10 nodes and 40 edges the way a `graph.delta` would, and note how long the update takes.
5. Repeat three times per library in Chrome with DevTools closed; record the median.

## Results (to fill in)

| Library | First paint (ms) | Pan FPS (median of 3) | Delta of 10 nodes / 40 edges (ms) | Machine |
|---|---|---|---|---|
| React Flow 11 | | | | |
| Cytoscape.js 3 | | | | |

## Decision rule

Pick the library with pan FPS ≥ 30 and delta < 200 ms (inside the 2 s NFR-32 budget with room for the network). If both
pass, prefer React Flow (already a dependency, React components for nodes, easier keyboard access). If neither passes,
fall back to the design's mitigation: cluster view by stakeholder group, 2-hop focus, and the table view.

## Decision

_Not decided yet — record the choice, the numbers that justified it, and the date here._
