# Harvest sources: what to read, what a candidate looks like

Reading budgets are hard bounds, not suggestions. Sample within them and move on. Evidence notes quote the source verbatim; paths are repo-relative with `:line` where possible. Harvest in the table's order: highest yield first, history last.

## Per-artifact table

| artifact | where to look | budget | what a candidate looks like |
|---|---|---|---|
| CLAUDE.md / CLAUDE.local.md | repo root, then subdirs | whole file, up to 400 lines | Any imperative rule ("never", "always", "do not", "must") becomes a constraint quoting the line. Skip the pylgrim-managed block if present. |
| AGENTS.md / AGENTS.override.md | repo root, then subdirs | whole file, up to 400 lines | Same as CLAUDE.md. Merge duplicates across the two, citing both. |
| Cursor rules | .cursorrules, .cursor/rules/*.mdc | up to 5 files, 200 lines each | Behavioral rules only; skip tone and formatting preferences unless a config enforces them. |
| Copilot rules | .github/copilot-instructions.md, .github/instructions/*.instructions.md | up to 5 files, 200 lines each | Same treatment as CLAUDE.md. |
| Other agent files | GEMINI.md, CONVENTIONS.md, .windsurfrules, .windsurf/rules/, .clinerules (file or dir), .roorules, .roo/rules/, .goosehints, .junie/guidelines.md | up to 5 files, 200 lines each | Same treatment as CLAUDE.md; merge duplicates across all agent files into one candidate citing each source. |
| CODEOWNERS | .github/, docs/, root | whole file | Owned paths become protected-path constraints with `scope_paths`. |
| ADRs | docs/adr/, docs/decisions/, adr/ | up to 10 most recent: title, status, decision section | Each accepted ADR becomes a decision entry: the decision in one line, the why in two. Superseded ADRs: only the superseding one. Soft cap 10 decisions total. |
| README and docs | README.md, CONTRIBUTING.md, docs/ | headings, plus any section titled conventions, architecture, or contributing; 300 lines total | Stated invariants and prohibitions only. Descriptions of what the code does are not constraints. |
| Lint configs | .eslintrc*, ruff.toml, pyproject [tool.*], clippy.toml, .editorconfig, biome.json | presence and top-level keys only, no rule-by-rule reading | Awareness constraints only, one per toolchain: "CI already gates X; pylgrim notes this and never re-enforces it." |
| CI workflows | .github/workflows/*.yml, .gitlab-ci.yml, Jenkinsfile | job and step names, up to 10 files | Required checks become awareness constraints. Deploy jobs touching protected environments become protected-path or process constraints. |
| Git history | last 200 commit subjects | subjects only, no diffs | Reverts, and "fix"/"never"/"don't" repeated against one path, suggest a constraint. Propose it labeled as inference, commit hashes as evidence paths. |
| Branch protection | not readable offline | n/a | Infer only from artifacts in the repo (CODEOWNERS, PR templates, required checks named in CI). Never guess platform settings. |

Precedence: tool-specific formats (cursor, windsurf, cline, roo, copilot, and the rest) outrank AGENTS.md within their own tool. Harvest all of them anyway and record provenance; the ledger, not any one file, is the source of truth.

## Example extractions

**Imperative rule in an agent file.** `CLAUDE.md:12` reads "Never edit generated files under src/gen/; regenerate with make codegen":

```yaml
scope_paths: ["src/gen/**"]
evidence:
  - { path: "CLAUDE.md:12", note: "Never edit generated files under src/gen/; regenerate with make codegen" }
```
Body: Files under src/gen/ are generated; edit the generator and run make codegen, never the output.

**Duplicate rule across artifacts.** `AGENTS.md:8` and `.cursor/rules/db.mdc:3` both forbid raw SQL in handlers. One candidate, two evidence items:

```yaml
evidence:
  - { path: "AGENTS.md:8", note: "No raw SQL outside the repository layer" }
  - { path: ".cursor/rules/db.mdc:3", note: "handlers must go through the repo classes, never raw SQL" }
```

**Conflicting rule across artifacts.** When two sources DISAGREE on the same behavioral rule, still produce ONE candidate, carrying BOTH evidence items. The body states the conflict neutrally: which file says what, quoted, and never silently picks a side. At ratification the table marks the entry CONFLICT; the user's accept or edit resolves it, and the ratified wording becomes the truth. `CLAUDE.md:9` says "Always use npm; never yarn" while `GEMINI.md:4` says "Use yarn for all installs":

```yaml
evidence:
  - { path: "CLAUDE.md:9", note: "Always use npm; never yarn" }
  - { path: "GEMINI.md:4", note: "Use yarn for all installs" }
```
Body: CONFLICT between sources: CLAUDE.md says "Always use npm; never yarn" while GEMINI.md says "Use yarn for all installs". Ratification decides which wording holds.

**CI awareness.** `.github/workflows/ci.yml` has a `typecheck` job:

```yaml
evidence:
  - { path: ".github/workflows/ci.yml:31", note: "run: npm run typecheck" }
```
Body: CI already gates type checking via npm run typecheck; pylgrim notes this and never re-enforces it.

**Protected path.** `CODEOWNERS` line "/migrations/ @org/dba":

```yaml
scope_paths: ["migrations/**"]
evidence:
  - { path: ".github/CODEOWNERS:8", note: "/migrations/ @org/dba" }
```
Body: Changes under migrations/ are owned by @org/dba and require their review.

**ADR to decision entry.** `docs/adr/0007-use-sqlite.md`, status Accepted, decision section reads "We will use SQLite with WAL mode for the job queue":

```yaml
kind: decision
evidence:
  - { path: "docs/adr/0007-use-sqlite.md:9", note: "We will use SQLite with WAL mode for the job queue" }
```
Body: Use SQLite (WAL mode) for the job queue. Why: no operational dependency the deploy story cannot absorb; volume fits.

**History inference.** Three commit subjects revert changes to `config/routing.yaml`:

```yaml
scope_paths: ["config/routing.yaml"]
evidence:
  - { path: "a1b2c3d", note: "Revert 'simplify routing table'" }
  - { path: "e4f5a6b", note: "Revert 'routing cleanup round 2'" }
```
Body: Inferred from history: changes to config/routing.yaml keep getting reverted; treat it as hands-off without an owner's sign-off.

## What is never a candidate

- Platitudes: "write clean code", "keep it simple", "follow best practices".
- Restatements of what the code plainly does.
- Tool preferences with no behavioral consequence ("we like tabs"), unless a config enforces them, in which case they are one awareness constraint.
- Anything you cannot quote from a file or commit in the repo.
- Rules about people and process that no artifact evidences ("the team prefers...").

## Manual inventory checklist (no-Python path)

When inventory.py cannot run, gather these by hand with `ls`, `git log`, and targeted reads:

1. `git log --oneline -20` for recent activity (skip if not a git repo).
2. List the repo root and one level down; note the main languages by extension.
3. Check for each intent artifact in the table above; record which exist and their sizes.
4. Check for an existing `.pylgrim/`, a knowledge-graph directory (`.understand/` or similar), `.pylgrimignore`, `redaction.toml`.
5. Note obvious privacy flags: `.env*` files tracked in git, fixture directories with real-looking data, client names in directory names.

Then proceed with the normal phases, respecting the same budgets, and say the inventory was manual.
