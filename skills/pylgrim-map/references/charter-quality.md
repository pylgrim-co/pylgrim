# Charter quality: what makes a constraint worth writing

A constraint is checkable or briefable: an agent reading it knows a specific thing not to do, or a specific gate that already exists. If neither, it is not a constraint.

## Three good entries

**1. Protected generated code**
```yaml
kind: constraint
mode: observe
source: map
status: proposed
scope_paths: ["src/gen/**"]
evidence:
  - { path: "CLAUDE.md:12", note: "Never edit generated files under src/gen/; regenerate with make codegen" }
```
Body: Files under src/gen/ are generated. Edit the generator and run make codegen; never edit the output directly.

Why it is good: names paths, names the alternative action, quotes its source.

**2. CI awareness**
```yaml
kind: constraint
mode: observe
source: map
status: proposed
evidence:
  - { path: ".github/workflows/ci.yml:31", note: "run: npm run typecheck" }
```
Body: CI already gates type checking via npm run typecheck; pylgrim notes this and never re-enforces it. Expect PRs to fail until it passes.

Why it is good: awareness framing, no duplicate enforcement, still briefable.

**3. Data-handling rule from docs**
```yaml
kind: constraint
mode: observe
source: map
status: proposed
scope_paths: ["src/api/**"]
evidence:
  - { path: "docs/security.md:44", note: "Request bodies must never be written to logs, including at debug level" }
```
Body: Never log request bodies anywhere under src/api/, at any log level.

Why it is good: an agent can be warned against it mid-session on a concrete action.

## Three bad entries

**1. The platitude.** Body: "Write clean, maintainable code." Not checkable, not briefable, warns against nothing. Banned by name, along with "keep it simple" and "follow best practices".

**2. The paraphrase.** Evidence note reads "the docs say to be careful with the database". A paraphrase is not evidence. Quote the line or drop the candidate.

**3. The invention.** Body: "All new services must use gRPC", derived from noticing two services use gRPC. Two examples are a pattern, not a rule. Excavation proposes only what an artifact states or history demonstrates (repeated reverts, repeated fixes); it never authors policy.

## Evidence norms

- Every candidate carries at least one evidence item: `{ path, note }`.
- `path` is repo-relative, with `:line` whenever the source is a specific line.
- `note` quotes the source verbatim, trimmed to the relevant clause.
- Merged duplicates keep one evidence item per source.
- Evidence survives ratification; it is provenance, not scaffolding.

## Reality tags at ratification

Every candidate row in the ratify table carries exactly one `reality` label answering "does the code appear to follow this rule?". The tag is derived from evidence the harvest already gathered plus at most 2 spot-checked files per candidate; never run a new scanning phase for it, and the five-minute sitting must survive.

- `followed`: what you already read (or up to 2 spot-checked files) shows the rule holding in practice.
- `contradicted (one example path)`: something violates the rule; cite exactly one example path, no more.
- `not checked`: nothing in hand settles it and the spot-check budget is spent.

The honesty rule: `not checked` is a first-class honest label, same spirit as cannot_judge; never guess. A wrong `followed` teaches the user to distrust every tag; an honest `not checked` costs nothing.

## The specificity ladder

Rank candidates by how far up they sit; cut from the bottom.

1. Quoted imperative rule with paths and an alternative action ("never X under Y; do Z instead").
2. Quoted imperative rule without paths.
3. Structural fact with teeth (CODEOWNERS, required CI check).
4. Inference from repeated history (reverts, repeated fixes on one path), flagged as inference.
5. Inference from structure alone. Weakest; propose only in artifact-poor repos and say it is an inference.
