#!/usr/bin/env python3
# VENDORED: canonical copy at spec/scripts/new_entry.py. Edit there, then run tools/sync_scripts.py.
"""new_entry.py mints a new .pylgrim ledger entry: a real ULID filename plus a
kind-appropriate skeleton with status: proposed and FILL placeholders. It
prints only the created file's path to stdout, so callers can capture it.
"""

import argparse
import os
import secrets
import sys
import time

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
KIND_DIR = {"constraint": "charter", "work_item": "work", "decision": "decisions"}
SOURCES = ("map", "plan", "decide", "manual")


def mint_ulid(ts_ms=None):
    """Return a 26-character ULID: 48-bit millisecond timestamp then 80
    random bits, encoded in Crockford base32."""
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)
    value = ((ts_ms & ((1 << 48) - 1)) << 80) | secrets.randbits(80)
    chars = []
    for i in range(26):
        shift = 5 * (25 - i)
        chars.append(CROCKFORD[(value >> shift) & 31])
    return "".join(chars)


def valid_slug(slug):
    if not (1 <= len(slug) <= 48):
        return False
    if slug[0] == "-" or slug[-1] == "-":
        return False
    return all(c in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in slug)


def skeleton(kind, source):
    if kind == "constraint":
        return (
            "---\n"
            "kind: constraint\n"
            "mode: observe\n"
            "scope_paths: []  # FILL: glob paths this rule covers, or delete this line\n"
            "source: %s\n"
            "status: proposed\n"
            "---\n"
            "\n"
            "# FILL: one-line title for the rule\n"
            "\n"
            "FILL: the rule in prose, concrete enough that an agent reading it knows\n"
            "what not to do.\n" % source
        )
    if kind == "work_item":
        return (
            "---\n"
            "kind: work_item\n"
            "status: proposed\n"
            "scope_paths: []  # FILL: glob paths this work may touch\n"
            "out_of_scope: []  # FILL: REQUIRED non-empty, what this work must not touch\n"
            "criteria:\n"
            "  - { text: \"FILL: a checkable acceptance criterion\", status: open }\n"
            "source: %s\n"
            "---\n"
            "\n"
            "# FILL: one-line title for the work item\n"
            "\n"
            "FILL: context and pointers the criteria need.\n" % source
        )
    return (
        "---\n"
        "kind: decision\n"
        "source: %s\n"
        "status: proposed\n"
        "---\n"
        "\n"
        "# FILL: the decision in one line\n"
        "\n"
        "FILL: the why, the alternatives considered, and references to files or\n"
        "other entries by ULID.\n" % source
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Mint a new .pylgrim entry with a fresh ULID filename.")
    parser.add_argument("kind", choices=sorted(KIND_DIR))
    parser.add_argument("slug", help="lowercase a-z, 0-9, hyphens; max 48 chars; "
                                     "no leading or trailing hyphen")
    parser.add_argument("--source", choices=SOURCES, default="manual",
                        help="provenance of the entry (default: manual)")
    parser.add_argument("--dir", dest="ledger", default="./.pylgrim",
                        help="the .pylgrim directory to write into "
                             "(default: ./.pylgrim, created if missing)")
    args = parser.parse_args(argv)

    if not valid_slug(args.slug):
        print("error: invalid slug %r: use lowercase a-z, 0-9, and hyphens; at most "
              "48 characters; no leading or trailing hyphen" % args.slug, file=sys.stderr)
        return 2

    subdir = os.path.join(args.ledger, KIND_DIR[args.kind])
    os.makedirs(subdir, exist_ok=True)
    ulid = mint_ulid()
    path = os.path.join(subdir, "%s-%s.md" % (ulid, args.slug))
    if os.path.exists(path):
        print("error: refusing to overwrite existing file %s" %
              path.replace("\\", "/"), file=sys.stderr)
        return 1
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(skeleton(args.kind, args.source))
    print(path.replace("\\", "/"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
