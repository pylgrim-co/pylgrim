# Privacy phase: semantic pass and comment proposals

The deterministic scanner belongs to the daemon. This pass is semantic: things only a reader notices. Proposals only ever tighten; loosening is a human act outside this skill.

## Semantic checklist

Look for, in paths first and file contents second:

- Client or customer names in directory names, fixture files, or test names ("tests/acme_corp/", "fixtures/walmart_orders.json").
- Unreleased-feature directories whose names leak roadmap ("src/features/project-titan/").
- Real-looking fixture data: plausible emails, full names, phone numbers, street addresses, tokens or keys committed as test data.
- Internal hostnames, staging URLs, employee usernames in configs or comments.
- Anything the inventory's deterministic privacy flags surfaced but the hard defaults do not already cover.

## What NOT to flag

- Public code and public APIs; the code being visible is the point of a repo.
- Generic test data: "user@example.com", "Jane Doe", "555-0100", lorem ipsum.
- Secrets already covered by the hard defaults (.env*, key files, secrets/ directories); they are excluded unconditionally and need no proposal.
- Open-source dependency names, public package registries, public issue links.

## The comment-proposal convention

Every proposal is a commented line with a reason. Nothing this skill writes to either file is active. Create the file if it does not exist.

In `redaction.toml` (content-shaped: strings and patterns):

```toml
# proposed(map): fixture data in tests/users.json looks like real customer emails
# patterns entry: "[a-z0-9._]+@acmecorp\\.com"

# proposed(map): client name appears in test titles
# literals entry: "Acme Corp"
```

In `.pylgrimignore` (path-shaped, gitignore syntax):

```gitignore
# proposed(map): directory name leaks an unreleased feature
# src/features/project-titan/

# proposed(map): fixtures exported from the production database
# tests/fixtures/prod-export/
```

## In-session review

Walk the proposals line by line with the same motion as charter ratification:

- **accept**: uncomment the entry line (the `# proposed(map)` reason line may stay as documentation or be removed, user's call).
- **reject**: remove both comment lines entirely.
- **defer**: leave commented. Visible and inert; the daemon re-surfaces it later.

Worked example. The proposal above, accepted, becomes an active line in `redaction.toml`:

```toml
# proposed(map): fixture data in tests/users.json looks like real customer emails
patterns = ["[a-z0-9._]+@acmecorp\\.com"]
```

If `patterns` already has an active list, append to it rather than adding a second `patterns` key. Same motion in `.pylgrimignore`: accepting uncomments `src/features/project-titan/` into an active ignore line.

Present all proposals in one short table (file, entry, reason) before the walk, so the user sees the whole surface at once. Report the tally in the closing summary: accepted, rejected, deferred.

## Tighten-only rules

- Never remove, narrow, or comment out an existing active rule in `redaction.toml` or `.pylgrimignore`.
- Never write a `!` negation in `.pylgrimignore`.
- Never propose changes to the hard defaults; they are unremovable by design.
- If an existing rule looks wrong or too broad, say so in chat and leave the file alone; editing it is the human's move.

If the code itself is the secret, say so and point at paths-only capture: redaction handles content-shaped leaks, `.pylgrimignore` handles path-shaped ones, and neither substitutes for keeping a truly sensitive repo local.
