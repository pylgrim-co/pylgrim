# Criteria quality: checkable or it does not ship

A criterion names an observable outcome, a command exit, or a file state. Someone who was not in the planning conversation must be able to mark it `satisfied` or `failed` without asking anyone. "Works well" is banned, along with its cousins: "is clean", "is robust", "handles errors gracefully", "is performant", "is user friendly".

3 to 7 criteria per work item. Fewer than 3 usually means the work is underspecified; more than 7 usually means two work items are hiding in one.

## Worked pairs

**Bad:** `{ text: "search works well", status: open }`
**Good:** `{ text: "searching 'invoice' in the demo dataset returns the 3 seeded invoice records in under 2 seconds", status: open }`

**Bad:** `{ text: "code is well tested", status: open }`
**Good:** `{ text: "npm test exits 0 and includes at least one test per new public function in src/search/", status: open }`

**Bad:** `{ text: "handles errors gracefully", status: open }`
**Good:** `{ text: "a malformed CSV upload returns HTTP 422 with a body naming the first bad row, and nothing is written to the database", status: open }`

**Bad:** `{ text: "docs updated", status: open }`
**Good:** `{ text: "README.md gains a 'Search' section documenting both query flags; grep for '--fuzzy' finds it", status: open }`

The pattern: name the input, the action, and the observable result. Prefer something runnable (a test suite, a curl, a grep, a file's existence) over a judgment call. If a criterion needs a human eye (visual design, tone of copy), say exactly what the eye checks: "the empty state shows the illustration from designs/empty.png and a single CTA".

New criteria are always `status: open`. `satisfied`, `failed`, and `waived` are set later, when work is checked against the contract, never at planning time.

## Self-check before ratification

For each criterion ask: could a different agent, six weeks from now, mark this satisfied or failed using only the repo and a shell? If it needs the planning conversation, tighten it. If two criteria would always flip together, merge them. If one criterion hides three checks ("tested, documented, and deployed"), split it.

Numbers beat adjectives: "under 2 seconds" not "fast", "3 seeded records" not "the right results", "HTTP 422" not "a helpful error".

## scope_paths

Globs for what the work may touch. Tight but honest:

- Good: `["src/search/**", "tests/search/**", "README.md"]`
- Too broad: `["src/**"]` when the work lives in one subsystem
- Too narrow: individual files for work that will clearly add new ones

If the work creates a new directory, include its glob even though it does not exist yet.

## out_of_scope

Concrete refusals, not platitudes. Each item is something an agent could plausibly drift into and must not:

- Good: `["no schema or migration changes", "no changes under src/billing/", "no new runtime dependencies", "no API version bump"]`
- Bad: `["nothing unnecessary", "no scope creep", "keep it minimal"]`

Derive candidates from the plan's neighbors: the systems the work touches but must not change, the tempting adjacent refactors, the features explicitly cut from this round. A good out_of_scope item is one an agent can be warned against mid-session: "you are editing src/billing/, which this work item declares out of scope."
