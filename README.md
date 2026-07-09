# pylgrim

**The intent layer for AI-driven development.** pylgrim keeps a per-repo ledger of your project's intent: the constraints it lives by, the work it has agreed to do, and the decisions behind both. Agents get briefed with it at session start, warned against it during work, and gated by it in CI. pylgrim remembers, briefs, warns, blocks, gates, and reports. It never writes or modifies your code.

## What ships today

The cold-start layer: three agent skills and the open `.pylgrim/` ledger format. They are standalone-useful with nothing else installed, make zero network calls, and burn no tokens beyond your own agent's.

| Skill | What it does |
|---|---|
| `pylgrim-map` | Excavates an existing repo's implicit intent (CLAUDE.md, AGENTS.md, CODEOWNERS, ADRs, docs, configs, git history) into a proposed charter of at most 15 evidence-backed constraints, ratified line by line in about five minutes. Includes a tighten-only privacy pass. |
| `pylgrim-plan` | Shapes a feature plan into a work-item contract: checkable acceptance criteria, scope paths, and a mandatory out-of-scope list, exported to CLAUDE.md. A plan session is ten minutes, not a ceremony. |
| `pylgrim-decide` | Captures a decision and its why mid-work, without breaking flow. |

The skills follow the [Agent Skills open standard](https://agentskills.io): they work in Claude Code, Codex, Cursor, Gemini CLI, and every other adopting agent. The skills work on every Claude tier; the judgment-heavy phases (map's harvest and curation) are at their best on sonnet-class models or better.

## Install

```bash
# any agent that supports skills (recommended)
npx skills add pylgrim-co/pylgrim

# Claude Code plugin
/plugin marketplace add pylgrim-co/pylgrim

# manual: copy skills/* into .claude/skills/ or .agents/skills/
```

## The ledger

`.pylgrim/` is markdown with YAML frontmatter, committed to your repo, synced by git. The format is an open, versioned spec; the full spec and the rest of the loop open up as they ship. Two rules carry the whole design:

1. **Excavate and ratify, never author.** Skills surface intent that already exists and show their evidence. Nothing takes effect without your explicit per-entry approval.
2. **Only ratified entries are ever exported, injected, or enforced.**

## Product laws

- No per-person scores, ever.
- Nothing is injected into a session without explicit human ratification.
- pylgrim never writes or modifies code. No auto-fix, ever.
- Facts gate, opinions advise. "Cannot judge" is a first-class verdict.
- Blocking is earned: observe, then advise, then enforce, per rule, by your choice. Fail open, always.
- Initialization never sends. The skills make no network calls at all.

## Roadmap

Capture, deterministic checks, a `pylgrim check` gate for CI, and a local web viewer are the next phases, milestone-gated. The full spec and the rest of the loop open up as they ship.

MIT licensed.
