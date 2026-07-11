#!/usr/bin/env python3
# VENDORED: canonical copy at spec/scripts/export_claudemd.py. Edit there, then run tools/sync_scripts.py.
"""export_claudemd.py regenerates the managed pylgrim block in CLAUDE.md and
AGENTS.md from ratified ledger entries (spec section 7): constraints one line
each with a mode tag, ratified work items that still have open criteria as
checklists plus their In scope / Out of scope path lists (capped, verbatim
entries; natural-language out-of-scope items render as written), and a
pointer line. The identical block goes to both files: CLAUDE.md always,
AGENTS.md when the file exists. The export is ULID-ordered, deterministic,
and idempotent; a lone or reversed marker aborts the run.

Path lists are exported because the evaluation program showed agents comply
near-perfectly with task-scoped, path-precise context (bias-audit-1.md C1:
the oracle arm's format); the block now mirrors that format.
"""

import argparse
import os
import re
import sys

BEGIN = "<!-- pylgrim:begin -->"
END = "<!-- pylgrim:end -->"
MANAGED = "<!-- managed by pylgrim: edit .pylgrim/ entries, not this text -->"


def fail(message):
    print("error: %s" % message, file=sys.stderr)
    sys.exit(2)


def read_quoted(text, start):
    out = []
    i = start + 1
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            out.append({"\\": "\\", '"': '"'}.get(text[i + 1], "\\" + text[i + 1]))
            i += 2
            continue
        if ch == '"':
            return "".join(out), i + 1
        out.append(ch)
        i += 1
    return None, -1


def parse_scalar(fragment):
    fragment = fragment.strip()
    if fragment.startswith('"'):
        value, _ = read_quoted(fragment, 0)
        return value if value is not None else fragment
    # Strip a trailing comment from an unquoted value.
    for i, ch in enumerate(fragment):
        if ch == "#" and (i == 0 or fragment[i - 1] in " \t"):
            return fragment[:i].strip()
    return fragment


def parse_inline_map(text):
    """Parse '{ k: v, k2: \"v\" }' leniently; returns a dict."""
    result = {}
    text = text.strip()
    if not text.startswith("{"):
        return result
    i = 1
    while i < len(text) and text[i] != "}":
        colon = text.find(":", i)
        if colon < 0:
            break
        key = text[i:colon].strip().strip(",")
        i = colon + 1
        while i < len(text) and text[i] in " \t":
            i += 1
        if i < len(text) and text[i] == '"':
            value, after = read_quoted(text, i)
            i = after if after > 0 else len(text)
        else:
            j = i
            while j < len(text) and text[j] not in ",}":
                j += 1
            value = text[i:j].strip()
            i = j
        if key:
            result[key] = value
        if i < len(text) and text[i] == ",":
            i += 1
    return result


def parse_flow_list(text):
    """Parse '[a, "b", c]' leniently; returns a list of strings."""
    items = []
    text = text.strip()
    if not text.startswith("["):
        return items
    i = 1
    while i < len(text) and text[i] != "]":
        while i < len(text) and text[i] in " \t,":
            i += 1
        if i >= len(text) or text[i] == "]":
            break
        if text[i] == '"':
            value, after = read_quoted(text, i)
            if value is not None:
                items.append(value)
            i = after if after > 0 else len(text)
        else:
            j = i
            while j < len(text) and text[j] not in ",]":
                j += 1
            item = text[i:j].strip()
            if item:
                items.append(item)
            i = j
    return items


def parse_entry(path):
    """Lenient v0-subset read of one entry: returns (fields, body) where
    scalar fields are str, flow lists are list[str], and block lists hold
    dicts (inline-map items) or strings (plain items). The validator owns
    strictness; here malformed files abort with a pointer to validate.py."""
    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    if not lines or lines[0].strip() != "---":
        fail("%s has no frontmatter; run spec/scripts/validate.py first" % path)
    close = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close = i
            break
    if close is None:
        fail("%s has unterminated frontmatter; run spec/scripts/validate.py first" % path)
    fields = {}
    current_list = None
    for raw in lines[1:close]:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if raw[0] in " \t":
            if current_list is not None and stripped.startswith("- "):
                fragment = stripped[2:].strip()
                if fragment.startswith("{"):
                    current_list.append(parse_inline_map(fragment))
                else:
                    current_list.append(parse_scalar(fragment))
            continue
        current_list = None
        colon = raw.find(":")
        if colon < 0:
            continue
        key = raw[:colon].strip()
        rest = raw[colon + 1:].strip()
        if rest == "" or rest.startswith("#"):
            current_list = []
            fields[key] = current_list
        elif rest.startswith("["):
            fields[key] = parse_flow_list(rest)
        else:
            fields[key] = parse_scalar(rest)
    body = "\n".join(lines[close + 1:])
    return fields, body


def summary_line(body, fallback):
    """First non-empty body paragraph, wrapped lines joined, heading markers removed.

    A heading line is its own paragraph; otherwise consecutive non-empty lines
    join with spaces so a wrapped sentence renders whole in the exported block.
    """
    lines = body.split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i == len(lines):
        return fallback
    first = lines[i].strip()
    if first.startswith("#"):
        heading = re.sub(r"^#+\s*", "", first)
        if heading:
            return heading
        i += 1
    para = []
    while i < len(lines) and lines[i].strip():
        para.append(re.sub(r"^#+\s*", "", lines[i].strip()))
        i += 1
    return " ".join(para) or fallback


def slug_of(filename):
    stem = filename[:-3] if filename.endswith(".md") else filename
    return stem[27:] if len(stem) > 27 else stem


# Standing delegation (spec section 6.1): a ratified charter entry whose slug
# starts 'delegation-' grants auto-ratification for the entry kinds named in
# its body. Constraints can never be delegated, so only these are detectable.
DELEGATION_KIND_WORDS = (("work_item", ("work_item", "work item")),
                         ("decision", ("decision",)))


def delegated_kinds_of(name, fields, body):
    """Entry kinds one charter entry delegates, [] when it is not a ratified
    delegation entry."""
    if fields.get("status") != "ratified" or not slug_of(name).startswith("delegation-"):
        return []
    text = body.lower()
    return [kind for kind, needles in DELEGATION_KIND_WORDS
            if any(needle in text for needle in needles)]


def collect(ledger):
    """Return (constraints, work_items, delegated_kinds) from ratified
    entries, ULID-ordered."""
    constraints = []
    work_items = []
    delegated = []
    charter_dir = os.path.join(ledger, "charter")
    if os.path.isdir(charter_dir):
        for name in sorted(os.listdir(charter_dir)):
            if not name.endswith(".md"):
                continue
            fields, body = parse_entry(os.path.join(charter_dir, name))
            if fields.get("status") != "ratified":
                continue
            mode = fields.get("mode", "observe")
            constraints.append("- [%s] %s" % (mode, summary_line(body, slug_of(name))))
            for kind in delegated_kinds_of(name, fields, body):
                if kind not in delegated:
                    delegated.append(kind)
    work_dir = os.path.join(ledger, "work")
    if os.path.isdir(work_dir):
        for name in sorted(os.listdir(work_dir)):
            if not name.endswith(".md"):
                continue
            fields, body = parse_entry(os.path.join(work_dir, name))
            if fields.get("status") != "ratified":
                continue
            criteria = fields.get("criteria")
            if not isinstance(criteria, list):
                continue
            dict_criteria = [c for c in criteria if isinstance(c, dict)]
            if not any(c.get("status") == "open" for c in dict_criteria):
                continue
            title = summary_line(body, slug_of(name))
            checklist = []
            for c in dict_criteria:
                status = c.get("status", "open")
                text = c.get("text", "")
                box = "x" if status in ("satisfied", "waived") else " "
                suffix = " (%s)" % status if status in ("failed", "waived") else ""
                checklist.append("- [%s] %s%s" % (box, text, suffix))
            scope_paths = fields.get("scope_paths")
            out_of_scope = fields.get("out_of_scope")
            work_items.append((
                title,
                checklist,
                scope_paths if isinstance(scope_paths, list) else [],
                out_of_scope if isinstance(out_of_scope, list) else [],
            ))
    return constraints, work_items, delegated


# Path lists are capped so a work item with a sprawling scope cannot bloat
# the block; the ledger entry stays the full record.
PATH_CAP = 8


def path_lines(label, values):
    """Render one In scope / Out of scope list; [] when there is nothing."""
    items = [v for v in values if isinstance(v, str) and v.strip()]
    if not items:
        return []
    lines = ["", "%s:" % label]
    lines.extend("- %s" % v for v in items[:PATH_CAP])
    if len(items) > PATH_CAP:
        lines.append("- (+%d more)" % (len(items) - PATH_CAP))
    return lines


def build_block(ledger):
    constraints, work_items, delegated = collect(ledger)
    lines = [BEGIN, MANAGED, ""]
    if constraints:
        lines.append("## Constraints")
        lines.append("")
        lines.extend(constraints)
        lines.append("")
    if work_items:
        lines.append("## Active work")
        lines.append("")
        for title, checklist, scope_paths, out_of_scope in work_items:
            lines.append("### %s" % title)
            lines.append("")
            lines.extend(checklist)
            lines.extend(path_lines("In scope", scope_paths))
            lines.extend(path_lines("Out of scope", out_of_scope))
            lines.append("")
    lines.append("Skills: log settled decisions with the pylgrim-decide skill; "
                 "plan new work into the ledger with pylgrim-plan; re-map repo "
                 "intent with pylgrim-map.")
    lines.append("")
    if delegated:
        lines.append("Delegated ratification is active for: %s." % ", ".join(delegated))
        lines.append("")
    lines.append("Full ledger: .pylgrim/ holds the ratified entries this block is "
                 "generated from; edit there, then re-run "
                 "spec/scripts/export_claudemd.py.")
    lines.append(END)
    return "\n".join(lines), len(constraints), len(work_items)


def splice(existing, block, name="CLAUDE.md"):
    """Insert or replace the managed block in the existing target-file text.
    Aborts on lone, reversed, or duplicated markers."""
    lines = existing.split("\n")
    begins = [i for i, l in enumerate(lines) if l.strip() == BEGIN]
    ends = [i for i, l in enumerate(lines) if l.strip() == END]
    if len(begins) > 1 or len(ends) > 1:
        fail("%s contains duplicated pylgrim markers; remove the extras by "
             "hand, then re-run (the exporter refuses to guess)" % name)
    if len(begins) != len(ends):
        fail("%s contains a lone pylgrim marker (%s without %s); restore "
             "the pair by hand, then re-run (the exporter refuses to guess)" %
             ((name,) + ((BEGIN, END) if begins else (END, BEGIN))))
    if not begins:
        base = existing
        if base and not base.endswith("\n"):
            base += "\n"
        if base:
            base += "\n"
        return base + block + "\n"
    if begins[0] > ends[0]:
        fail("%s contains reversed pylgrim markers (%s appears before %s); "
             "restore the order by hand, then re-run (the exporter refuses to guess)" %
             (name, END, BEGIN))
    new_lines = lines[:begins[0]] + block.split("\n") + lines[ends[0] + 1:]
    result = "\n".join(new_lines)
    if not result.endswith("\n"):
        result += "\n"
    return result


def render_target(path, block):
    """Return (existing_text_or_None, new_content) for one target file."""
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8", newline="") as fh:
            existing = fh.read()
        return existing, splice(existing, block, os.path.basename(path))
    return None, block + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Regenerate the managed pylgrim block in CLAUDE.md and, "
                    "when the file exists, AGENTS.md.")
    parser.add_argument("--repo-root", default=".",
                        help="repository root containing .pylgrim/ and CLAUDE.md "
                             "(default: current directory)")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if CLAUDE.md or AGENTS.md is stale; never writes")
    args = parser.parse_args(argv)

    root = os.path.abspath(args.repo_root)
    ledger = os.path.join(root, ".pylgrim")
    if not os.path.isdir(ledger):
        fail("no .pylgrim directory at %s" % ledger.replace("\\", "/"))

    # CLAUDE.md is always a target (created if absent); AGENTS.md only when it
    # already exists (the map skill's consolidation phase may create it).
    targets = [os.path.join(root, "CLAUDE.md")]
    agents_md = os.path.join(root, "AGENTS.md")
    if os.path.isfile(agents_md):
        targets.append(agents_md)

    block, n_constraints, n_work = build_block(ledger)
    exit_code = 0
    for path in targets:
        existing, new_content = render_target(path, block)
        display = path.replace("\\", "/")
        if args.check:
            if existing is None:
                print("stale: %s does not exist; run export_claudemd.py to create it"
                      % display)
                exit_code = 1
            elif existing != new_content:
                print("stale: the pylgrim block in %s does not match the ledger; "
                      "run export_claudemd.py to regenerate it" % display)
                exit_code = 1
            else:
                print("%s is up to date" % display)
            continue
        if existing == new_content:
            print("%s unchanged (%d constraints, %d active work items)" %
                  (display, n_constraints, n_work))
            continue
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_content)
        verb = "created" if existing is None else "updated"
        print("%s %s (%d constraints, %d active work items)" %
              (display, verb, n_constraints, n_work))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
