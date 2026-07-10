# The ratification walk

How proposed entries become ratified: one entry at a time, presented, explained, and discussable, with a fast exit for users who want speed. The index (the numbered table, or the draft list when there are only a few entries) always comes first, so the user sees the whole set before the first question. The walk is the default; the accept-all sprint is the opt-out, chosen by the user, never proposed as the default.

## The walk

- Work through the entries in index order. Each gets one compact card: the rule or contract in one line, its evidence quoted with paths (when the entry carries evidence), the reality tag when the index carries one, and one line on why it earns its place in the ledger. No filler between cards.
- Ask per card with AskUserQuestion when available. Options, exactly and always: **accept**, **edit**, **reject**, **defer**, **accept all remaining**. The question text invites discussion: "or just reply to talk it through."
- "Accept all remaining" is in EVERY card's options, first card included: the five-minute sitting survives for a user who trusts the index.
- Plaintext fallback (AskUserQuestion unavailable, or a non-Claude agent): print the card, then exactly one line: `accept / edit <your wording> / reject / defer / accept all remaining, or just reply to talk it through.`

## The discussion loop

A reply that is none of the five options is discussion, never a verdict. Engage with it honestly (including "this rule is wrong": the user may be right and the edit option exists for exactly that), then re-ask the same card's question. If the reply is still neither a verdict nor a question after one re-ask, defer that entry, say so in one line, and move to the next card. Ambiguity never ratifies and never rejects.

## Outcomes

- **accept**: flip `status: ratified` in place, stamp `last_confirmed: <today, YYYY-MM-DD>` and `ratified_by: explicit`.
- **edit**: apply the user's wording in the file, then accept as above; the edit is the acceptance.
- **reject**: delete the file.
- **defer**: leave `status: proposed`, visible and inert. Deferring is a first-class outcome, not a failure; a deferred entry can be ratified in any later session.
- **accept all remaining**: confirm once in one line ("accepting this one and the N not yet shown"), then apply the accept outcome to this card and every card not yet visited. Entries already rejected or deferred earlier in the walk keep their outcome.

## The delegation branch

Delegation phrases in the walk ("just do it", "don't ask me", "you decide") never ratify anything: apply the Standing delegation rules in references/spec-quick-ref.md. Constraints are never delegable, so charter candidates stay `proposed` without an explicit per-card accept. Work items and decisions ratify directly only when a ratified `delegation-` charter entry covering their kind already exists: stamp `ratified_by: delegated` plus `last_confirmed` and say so in one line, skipping their cards. Absent that entry, offer the standing entry once, then leave everything `proposed` with a one-line explanation.

## Pace

One question per entry; with 12 entries and a decisive user that is still about five minutes. Never batch several entries into one question and never re-open a decided card: the per-item card is the contract, and "accept all remaining" is the only batch act.
