#!/usr/bin/env python3
# VENDORED: canonical copy at spec/scripts/validate.py. Edit there, then run tools/sync_scripts.py.
"""validate.py is the executable form of the pylgrim v0 spec (spec/README.md).

It checks .pylgrim/ ledgers: filename grammar, the v0 frontmatter subset,
per-kind required fields and enums, criteria and evidence shapes, dates, and
redaction.toml. Where the spec prose and this script disagree, this script is
the v0 behavior. It never modifies file contents; the one repair it performs,
opt-in via --fix-names, renames invalidly named entry files to a fresh
'<ulid>-<slug>.md'. Exit code 0 means zero errors.
"""

import argparse
import datetime
import json
import os
import re
import secrets
import sys
import time

try:
    import tomllib
except ImportError:  # Python 3.10: fall back to a minimal reader below.
    tomllib = None

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

DIR_KIND = {"charter": "constraint", "work": "work_item", "decisions": "decision"}
KIND_DIR = {v: k for k, v in DIR_KIND.items()}

MODE_ENUM = ("observe", "advise", "enforce")
STATUS_ENUM = ("proposed", "ratified")
SOURCE_ENUM = ("map", "plan", "decide", "prompt-promotion", "finding", "manual")
CRITERION_STATUS_ENUM = ("open", "satisfied", "failed", "waived")
RATIFIED_BY_ENUM = ("explicit", "delegated")
SKILL_SOURCES = ("map", "plan", "decide")

FIELD_SPECS = {
    "constraint": {
        "required": ("kind", "mode", "source", "status"),
        "optional": ("scope_paths", "evidence", "last_confirmed", "ratified_by"),
    },
    "work_item": {
        "required": ("kind", "status", "scope_paths", "out_of_scope", "criteria", "source"),
        "optional": ("issue_ref", "last_confirmed", "ratified_by"),
    },
    "decision": {
        "required": ("kind", "source", "status"),
        "optional": ("last_confirmed", "ratified_by"),
    },
}

# Characters that force a plain scalar to be quoted (spec section 4).
PLAIN_FORBIDDEN = ":#{}[],"


def display_path(path):
    """Return a forward-slash path, relative to cwd when that is possible."""
    try:
        rel = os.path.relpath(path)
    except ValueError:  # different drive on Windows
        rel = os.path.abspath(path)
    return rel.replace("\\", "/")


class Report:
    def __init__(self):
        self.findings = []

    def add(self, level, path, field, message):
        self.findings.append(
            {"level": level, "path": display_path(path), "field": field, "message": message}
        )

    def error(self, path, field, message):
        self.add("ERROR", path, field, message)

    def warn(self, path, field, message):
        self.add("WARN", path, field, message)

    @property
    def error_count(self):
        return sum(1 for f in self.findings if f["level"] == "ERROR")

    @property
    def warning_count(self):
        return sum(1 for f in self.findings if f["level"] == "WARN")


# ---------------------------------------------------------------------------
# Frontmatter parsing: the v0 subset, nothing else.
# ---------------------------------------------------------------------------

def strip_comment(fragment):
    """Drop a trailing '# ...' comment from unquoted text (a '#' preceded by
    whitespace, or at position 0, starts a comment)."""
    for i, ch in enumerate(fragment):
        if ch == "#" and (i == 0 or fragment[i - 1] in " \t"):
            return fragment[:i].rstrip()
    return fragment.rstrip()


def read_quoted(text, start):
    """Read a double-quoted scalar beginning at text[start] == '\"'.
    Returns (value, index_after_closing_quote) or (None, -1) if unterminated."""
    out = []
    i = start + 1
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            out.append({"\\": "\\", '"': '"'}.get(nxt, "\\" + nxt))
            i += 2
            continue
        if ch == '"':
            return "".join(out), i + 1
        out.append(ch)
        i += 1
    return None, -1


def check_plain(value, lineno, key, err):
    """A plain (unquoted) scalar must not contain the characters that the v0
    subset reserves; the fix is always to double-quote the value."""
    for ch in value:
        if ch in PLAIN_FORBIDDEN or ch in "\"'":
            err(
                key,
                "line %d: unquoted value %r contains %r; the v0 subset requires "
                "double quotes around values containing any of : # { } [ ] , or quotes"
                % (lineno, value, ch),
            )
            return None
    if value.startswith(("|", ">")):
        err(key, "line %d: multiline scalars ('|', '>') are not in the v0 subset" % lineno)
        return None
    if value.startswith(("&", "*", "!")):
        err(key, "line %d: anchors, aliases, and tags are not in the v0 subset" % lineno)
        return None
    return value


def parse_scalar_or_list(rest, lineno, key, err):
    """Parse the text after 'key:' on one line. Returns a str, a list of str,
    or None when the text is outside the subset (an error was recorded)."""
    rest = rest.strip()
    if rest.startswith('"'):
        value, after = read_quoted(rest, 0)
        if after < 0:
            err(key, "line %d: unterminated double-quoted scalar" % lineno)
            return None
        trailing = strip_comment(rest[after:]).strip()
        if trailing:
            err(key, "line %d: unexpected text %r after closing quote" % (lineno, trailing))
            return None
        return value
    if rest.startswith("["):
        return parse_inline_list(rest, lineno, key, err)
    if rest.startswith("{"):
        err(key, "line %d: flow mappings at the top level are not in the v0 subset; "
                 "inline maps are only allowed as '- { ... }' block list items" % lineno)
        return None
    if rest.startswith(("|", ">")):
        err(key, "line %d: multiline scalars ('|', '>') are not in the v0 subset; "
                 "write the value on one line, quoted if needed" % lineno)
        return None
    if rest.startswith("'"):
        err(key, "line %d: single-quoted scalars are not in the v0 subset; use double quotes" % lineno)
        return None
    plain = strip_comment(rest).strip()
    if plain == "":
        # 'key:' followed by nothing and no block list items; caller handles.
        return None
    return check_plain(plain, lineno, key, err)


def parse_inline_list(text, lineno, key, err):
    """Parse '[a, "b", c]'. Returns a list of str or None on error."""
    items = []
    i = 1
    expect_item = True
    closed_at = -1
    while i < len(text):
        ch = text[i]
        if ch in " \t":
            i += 1
            continue
        if ch == "]":
            closed_at = i
            break
        if ch == ",":
            if expect_item:
                err(key, "line %d: empty item in inline list (stray comma)" % lineno)
                return None
            expect_item = True
            i += 1
            continue
        if not expect_item:
            err(key, "line %d: missing comma between inline list items" % lineno)
            return None
        if ch == '"':
            value, after = read_quoted(text, i)
            if after < 0:
                err(key, "line %d: unterminated double-quoted scalar in inline list" % lineno)
                return None
            items.append(value)
            i = after
        else:
            j = i
            while j < len(text) and text[j] not in ",]":
                j += 1
            raw = text[i:j].strip()
            value = check_plain(raw, lineno, key, err)
            if value is None:
                return None
            items.append(value)
            i = j
        expect_item = False
    if closed_at < 0:
        err(key, "line %d: inline list is missing its closing ']'" % lineno)
        return None
    trailing = strip_comment(text[closed_at + 1:]).strip()
    if trailing:
        err(key, "line %d: unexpected text %r after ']'" % (lineno, trailing))
        return None
    return items


def parse_inline_map(text, lineno, key, err):
    """Parse '{ text: "...", status: open }'. Returns a dict or None."""
    if not text.startswith("{"):
        err(key, "line %d: block list items must be inline maps of the form "
                 "'- { key: value, ... }'; got %r" % (lineno, text))
        return None
    result = {}
    i = 1
    while True:
        while i < len(text) and text[i] in " \t":
            i += 1
        if i >= len(text):
            err(key, "line %d: inline map is missing its closing '}'" % lineno)
            return None
        if text[i] == "}":
            i += 1
            break
        colon = text.find(":", i)
        if colon < 0:
            err(key, "line %d: inline map entry has no ':' separator" % lineno)
            return None
        item_key = text[i:colon].strip()
        if not KEY_RE.match(item_key):
            err(key, "line %d: invalid inline map key %r" % (lineno, item_key))
            return None
        if item_key in result:
            err(key, "line %d: duplicate key %r in inline map" % (lineno, item_key))
            return None
        i = colon + 1
        while i < len(text) and text[i] in " \t":
            i += 1
        if i < len(text) and text[i] == '"':
            value, after = read_quoted(text, i)
            if after < 0:
                err(key, "line %d: unterminated double-quoted scalar in inline map" % lineno)
                return None
            i = after
        else:
            j = i
            while j < len(text) and text[j] not in ",}":
                j += 1
            raw = text[i:j].strip()
            value = check_plain(raw, lineno, key, err)
            if value is None:
                return None
            i = j
        result[item_key] = value
        while i < len(text) and text[i] in " \t":
            i += 1
        if i < len(text) and text[i] == ",":
            i += 1
        elif i < len(text) and text[i] == "}":
            continue
        elif i >= len(text):
            err(key, "line %d: inline map is missing its closing '}'" % lineno)
            return None
    trailing = strip_comment(text[i:]).strip()
    if trailing:
        err(key, "line %d: unexpected text %r after '}'" % (lineno, trailing))
        return None
    return result


def parse_block_item(text, lineno, key, err):
    """Parse one '- ...' block list item: an inline map ('- { ... }') or a
    plain/quoted scalar ('- item' / '- "item"'). Returns dict, str, or None."""
    if text.startswith("{"):
        return parse_inline_map(text, lineno, key, err)
    if text.startswith('"'):
        value, after = read_quoted(text, 0)
        if after < 0:
            err(key, "line %d: unterminated double-quoted scalar" % lineno)
            return None
        trailing = strip_comment(text[after:]).strip()
        if trailing:
            err(key, "line %d: unexpected text %r after closing quote" % (lineno, trailing))
            return None
        return value
    if text.startswith("["):
        err(key, "line %d: nested lists are not in the v0 subset" % lineno)
        return None
    if text.startswith("'"):
        err(key, "line %d: single-quoted scalars are not in the v0 subset; "
                 "use double quotes" % lineno)
        return None
    if text.startswith(("|", ">")):
        err(key, "line %d: multiline scalars ('|', '>') are not in the v0 subset" % lineno)
        return None
    plain = strip_comment(text).strip()
    if plain == "":
        err(key, "line %d: empty block list item under %r" % (lineno, key))
        return None
    return check_plain(plain, lineno, key, err)


def parse_frontmatter(text, path, report):
    """Parse an entry file. Returns (fields, body) where fields maps key to
    (value, lineno); value is str, list[str], or list[dict]. Returns
    (None, None) when the frontmatter block itself is absent or unterminated.
    Subset violations are recorded as errors and the offending key omitted."""

    def err(field, message):
        report.error(path, field, message)

    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        err("frontmatter", "file must begin with '---' on line 1 (YAML frontmatter is required)")
        return None, None
    close = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            close = i
            break
    if close is None:
        err("frontmatter", "frontmatter opened on line 1 is never closed with '---'")
        return None, None

    fields = {}
    body = "\n".join(lines[close + 1:])
    n = 1
    while n < close:
        raw = lines[n]
        lineno = n + 1
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            n += 1
            continue
        if raw[0] in " \t":
            err("frontmatter",
                "line %d: unexpected indented line %r; nested mappings are not in the "
                "v0 subset (only '- ...' items under a bare 'key:' line)" % (lineno, stripped))
            n += 1
            continue
        colon = raw.find(":")
        if colon < 0:
            err("frontmatter", "line %d: expected 'key: value', got %r" % (lineno, stripped))
            n += 1
            continue
        key = raw[:colon].strip()
        if not KEY_RE.match(key):
            err("frontmatter", "line %d: invalid key %r" % (lineno, key))
            n += 1
            continue
        rest = raw[colon + 1:]
        rest_stripped = strip_comment(rest).strip()
        if rest_stripped == "":
            # Bare 'key:' introduces a block list: inline-map items
            # ('- { ... }', criteria and evidence) or plain-scalar items
            # ('- item' / '- "item"', string-list fields).
            items = []
            m = n + 1
            bad = False
            while m < close:
                sub = lines[m]
                sub_stripped = sub.strip()
                if not sub_stripped or sub_stripped.startswith("#"):
                    m += 1
                    continue
                if sub[0] not in " \t":
                    break
                if sub_stripped.startswith("- "):
                    item = parse_block_item(sub_stripped[2:].strip(), m + 1, key, err)
                    if item is None:
                        bad = True
                    else:
                        items.append(item)
                else:
                    err(key,
                        "line %d: expected a '- ...' block list item under %r; "
                        "nested mappings are not in the v0 subset" % (m + 1, key))
                    bad = True
                m += 1
            if not items and not bad:
                err(key, "line %d: %r has no value (bare 'key:' must be followed by "
                         "'- item' or '- { ... }' block list items)" % (lineno, key))
            elif not bad:
                if key in fields:
                    err("frontmatter", "line %d: duplicate key %r" % (lineno, key))
                else:
                    fields[key] = (items, lineno)
            n = m
            continue
        value = parse_scalar_or_list(rest, lineno, key, err)
        if value is not None:
            if key in fields:
                err("frontmatter", "line %d: duplicate key %r" % (lineno, key))
            else:
                fields[key] = (value, lineno)
        n += 1
    return fields, body


# ---------------------------------------------------------------------------
# Entry checks
# ---------------------------------------------------------------------------

def check_filename(path, report):
    name = os.path.basename(path)
    if not name.endswith(".md"):
        report.error(path, "filename", "entry files must end in '.md'")
        return
    stem = name[:-3]
    if len(stem) < 28 or stem[26] != "-":
        report.error(path, "filename",
                     "expected '<ulid>-<slug>.md': a 26-character ULID, a hyphen, then a slug")
        return
    ulid, slug = stem[:26], stem[27:]
    if not ULID_RE.match(ulid):
        report.error(path, "filename",
                     "ULID part %r is not 26 characters of Crockford base32 "
                     "(0-9 and A-Z excluding I, L, O, U)" % ulid)
    if len(slug) > 48:
        report.error(path, "filename",
                     "slug %r is %d characters; the maximum is 48" % (slug, len(slug)))
    if not SLUG_RE.match(slug):
        report.error(path, "filename",
                     "slug %r must be lowercase a-z, 0-9, and hyphens, with no "
                     "leading or trailing hyphen" % slug)


def check_iso_date(value, path, field, report):
    if not isinstance(value, str) or not DATE_RE.match(value):
        report.error(path, field,
                     "%r is not an ISO date; expected YYYY-MM-DD" % (value,))
        return
    try:
        datetime.date.fromisoformat(value)
    except ValueError as exc:
        report.error(path, field, "%r is not a valid calendar date: %s" % (value, exc))


def check_enum(value, allowed, path, field, report):
    if not isinstance(value, str):
        report.error(path, field, "expected a scalar, got %s" % type_name(value))
        return False
    if value not in allowed:
        report.error(path, field,
                     "invalid value %r; allowed: %s" % (value, ", ".join(allowed)))
        return False
    return True


def type_name(value):
    if isinstance(value, str):
        return "a scalar"
    if isinstance(value, list) and (not value or isinstance(value[0], dict)):
        return "a block list of inline maps"
    if isinstance(value, list):
        return "a list of scalars"
    return repr(type(value))


def check_map_items(items, allowed, required, path, field, report):
    """Validate block-list item shape for criteria and evidence."""
    for idx, item in enumerate(items, 1):
        label = "%s[%d]" % (field, idx)
        if not isinstance(item, dict):
            report.error(path, label, "expected an inline map '- { ... }'")
            continue
        unknown = sorted(set(item) - set(allowed))
        if unknown:
            report.error(path, label,
                         "unknown key(s) %s; %s items are { %s }" %
                         (", ".join(repr(u) for u in unknown), field, ", ".join(allowed)))
        for req in required:
            if req not in item or not str(item.get(req, "")).strip():
                report.error(path, label,
                             "missing or empty %r; %s items are { %s }" %
                             (req, field, ", ".join(allowed)))


def check_entry(path, expected_kind, repo_root, report):
    check_filename(path, report)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        report.error(path, "file", "cannot read file: %s" % exc)
        return
    fields, body = parse_frontmatter(text, path, report)
    if fields is None:
        return

    values = {k: v[0] for k, v in fields.items()}

    # kind: presence, enum, directory agreement.
    effective_kind = expected_kind
    if "kind" not in values:
        report.error(path, "kind", "missing required field 'kind' "
                     "(constraint, work_item, or decision)")
    else:
        kind = values["kind"]
        if not isinstance(kind, str):
            report.error(path, "kind", "expected a scalar, got %s" % type_name(kind))
        elif kind not in KIND_DIR:
            report.error(path, "kind",
                         "invalid kind %r; allowed: constraint, work_item, decision" % kind)
        else:
            effective_kind = kind
            if expected_kind and kind != expected_kind:
                report.error(path, "kind",
                             "kind %r belongs in '%s/' but this file is in '%s/' "
                             "(which holds kind %r)" %
                             (kind, KIND_DIR[kind], KIND_DIR[expected_kind], expected_kind))
    if effective_kind is None:
        return  # No directory context and no usable kind: nothing more to check.

    spec = FIELD_SPECS[effective_kind]
    known = set(spec["required"]) | set(spec["optional"])
    for key in spec["required"]:
        if key not in values:
            report.error(path, key,
                         "missing required field %r for kind %r" % (key, effective_kind))
    for key in sorted(set(values) - known):
        report.warn(path, key,
                    "unknown field %r for kind %r (unknown fields are ignored)" %
                    (key, effective_kind))

    if "status" in values:
        check_enum(values["status"], STATUS_ENUM, path, "status", report)
    if "source" in values:
        check_enum(values["source"], SOURCE_ENUM, path, "source", report)
    if "mode" in values and effective_kind == "constraint":
        check_enum(values["mode"], MODE_ENUM, path, "mode", report)
    if "last_confirmed" in values:
        check_iso_date(values["last_confirmed"], path, "last_confirmed", report)
    elif values.get("status") == "ratified":
        report.error(path, "last_confirmed",
                     "required when status is 'ratified' (stamp the ratification date, "
                     "YYYY-MM-DD)")
    if "issue_ref" in values and not isinstance(values["issue_ref"], str):
        report.error(path, "issue_ref", "expected a scalar, got %s" % type_name(values["issue_ref"]))
    if "ratified_by" in values:
        ok = check_enum(values["ratified_by"], RATIFIED_BY_ENUM, path, "ratified_by", report)
        if ok and values.get("status") == "proposed":
            report.warn(path, "ratified_by",
                        "'ratified_by' on a proposed entry is meaningless until "
                        "ratified (it records how the ratification act happened)")

    for key in ("scope_paths", "out_of_scope"):
        if key in values:
            value = values[key]
            if not isinstance(value, list) or any(isinstance(i, dict) for i in value):
                report.error(path, key,
                             "expected a list of strings (inline [a, \"b\"] or block "
                             "'- item' form), got %s" % type_name(value))
    oos = values.get("out_of_scope")
    if effective_kind == "work_item" and isinstance(oos, list) and \
            not any(isinstance(i, dict) for i in oos) and len(oos) == 0:
        report.error(path, "out_of_scope",
                     "must be non-empty on work items: name at least one thing this "
                     "work must not touch")

    if "criteria" in values:
        criteria = values["criteria"]
        if not isinstance(criteria, list) or not all(isinstance(i, dict) for i in criteria):
            report.error(path, "criteria",
                         "expected a block list of '- { text: \"...\", status: open }' items, "
                         "got %s" % type_name(criteria))
        elif len(criteria) == 0:
            report.error(path, "criteria", "must contain at least one criterion")
        else:
            check_map_items(criteria, ("text", "status"), ("text", "status"),
                            path, "criteria", report)
            for idx, item in enumerate(criteria, 1):
                status = item.get("status")
                if status and status not in CRITERION_STATUS_ENUM:
                    report.error(path, "criteria[%d].status" % idx,
                                 "invalid value %r; allowed: %s" %
                                 (status, ", ".join(CRITERION_STATUS_ENUM)))

    if "evidence" in values:
        evidence = values["evidence"]
        if not isinstance(evidence, list) or not all(isinstance(i, dict) for i in evidence):
            report.error(path, "evidence",
                         "expected a block list of '- { path: \"...\", note: \"...\" }' items, "
                         "got %s" % type_name(evidence))
        else:
            check_map_items(evidence, ("path", "note"), ("path",), path, "evidence", report)
            if repo_root:
                for idx, item in enumerate(evidence, 1):
                    epath = item.get("path")
                    if not epath:
                        continue
                    # Strip :line or :start-end suffixes before resolving.
                    bare = re.sub(r"(:\d+(?:-\d+)?)+$", "", epath)
                    target = os.path.normpath(os.path.join(repo_root, bare))
                    if not os.path.exists(target):
                        report.warn(path, "evidence[%d].path" % idx,
                                    "path %r does not resolve relative to repo root %r" %
                                    (epath, display_path(repo_root)))

    if values.get("source") in SKILL_SOURCES and values.get("mode") in ("advise", "enforce"):
        report.warn(path, "mode",
                    "mode %r on a skill-sourced entry (source: %s); skills write "
                    "mode: observe, the ramp to advise/enforce is a human act" %
                    (values["mode"], values["source"]))

    if body is not None and body.strip() == "":
        report.warn(path, "body", "empty body: the prose after the frontmatter is the entry")


# ---------------------------------------------------------------------------
# redaction.toml
# ---------------------------------------------------------------------------

def fallback_read_toml(text):
    """Minimal reader for the redaction.toml shape ('key = [strings]') used
    only when tomllib is unavailable (Python 3.10)."""
    data = {}
    pending_key = None
    buffer = ""
    for line in text.split("\n"):
        stripped = line.strip()
        if pending_key is None:
            if not stripped or stripped.startswith("#"):
                continue
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*(.*)$", stripped)
            if not m:
                raise ValueError("unparseable line: %r" % stripped)
            pending_key, buffer = m.group(1), m.group(2)
        else:
            buffer += " " + stripped
        if pending_key is not None and buffer.rstrip().endswith("]"):
            inner = buffer.strip()
            if not (inner.startswith("[") and inner.endswith("]")):
                raise ValueError("expected an array for %r" % pending_key)
            strings = re.findall(r'"((?:[^"\\]|\\.)*)"|\'([^\']*)\'', inner[1:-1])
            data[pending_key] = [
                a.encode("utf-8").decode("unicode_escape") if a else b for a, b in strings
            ]
            pending_key, buffer = None, ""
    if pending_key is not None:
        raise ValueError("unterminated array for %r" % pending_key)
    return data


def check_redaction(path, report):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        report.error(path, "file", "cannot read file: %s" % exc)
        return
    try:
        if tomllib is not None:
            data = tomllib.loads(raw.decode("utf-8"))
        else:
            data = fallback_read_toml(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        report.error(path, "toml", "redaction.toml does not parse as TOML: %s" % exc)
        return
    known = ("literals", "patterns", "paths")
    for key in sorted(set(data) - set(known)):
        report.warn(path, key, "unknown key %r; redaction.toml keys are: %s" %
                    (key, ", ".join(known)))
    for key in known:
        if key not in data:
            continue
        value = data[key]
        if not isinstance(value, list) or not all(isinstance(i, str) for i in value):
            report.error(path, key, "%r must be an array of strings" % key)
            continue
        if key == "patterns":
            for idx, pattern in enumerate(value, 1):
                try:
                    re.compile(pattern)
                except re.error as exc:
                    report.warn(path, "patterns[%d]" % idx,
                                "regex %r does not compile: %s" % (pattern, exc))


# ---------------------------------------------------------------------------
# Filename repair (--fix-names)
# ---------------------------------------------------------------------------

def mint_ulid(ts_ms=None):
    """26-character ULID: 48-bit millisecond timestamp then 80 random bits,
    Crockford base32 (kept in sync with new_entry.py; duplicated so this
    script stays standalone when vendored)."""
    if ts_ms is None:
        ts_ms = int(time.time() * 1000)
    value = ((ts_ms & ((1 << 48) - 1)) << 80) | secrets.randbits(80)
    return "".join(CROCKFORD[(value >> (5 * (25 - i))) & 31] for i in range(26))


def sanitize_slug(text):
    """Force text into the slug grammar: lowercase, invalid characters become
    hyphens, at most 48 characters, no leading or trailing hyphen."""
    slug = "".join(
        ch if ch in "abcdefghijklmnopqrstuvwxyz0123456789-" else "-"
        for ch in text.lower()
    )[:48].strip("-")
    return slug or "entry"


def filename_valid(path):
    """Does the basename pass the filename grammar? (check_filename, quietly)"""
    probe = Report()
    check_filename(path, probe)
    return probe.error_count == 0


def fix_names(paths, stream=None):
    """Rename every discovered entry file whose name fails the filename
    grammar to '<fresh ULID>-<sanitized existing slug>.md'. Content is never
    touched, so the repair is always safe; valid names are never renamed, so
    the pass is idempotent. Prints each rename. Returns the paths list with
    explicitly named files replaced by their new locations."""
    stream = stream or sys.stdout
    discovery = Report()  # discovery-time findings re-surface in the validate pass
    jobs = []
    for path in paths:
        jobs.extend(expand_target(path, discovery))
    renames = {}
    for job in jobs:
        if job[0] != "entry" or filename_valid(job[1]):
            continue
        entry = job[1]
        name = os.path.basename(entry)
        stem = name[:-3] if name.endswith(".md") else name
        # Keep the human half: the slug after a ULID-shaped prefix, else the
        # whole stem, sanitized either way.
        slug_source = stem[27:] if len(stem) >= 28 and stem[26] == "-" else stem
        parent = os.path.dirname(entry)
        target = os.path.join(parent, "%s-%s.md" % (mint_ulid(), sanitize_slug(slug_source)))
        while os.path.exists(target):
            target = os.path.join(parent, "%s-%s.md" % (mint_ulid(), sanitize_slug(slug_source)))
        os.replace(entry, target)
        renames[os.path.abspath(entry)] = target
        print("renamed %s -> %s" % (display_path(entry), display_path(target)),
              file=stream)
    return [renames.get(os.path.abspath(p), p) for p in paths]


# ---------------------------------------------------------------------------
# Target discovery and CLI
# ---------------------------------------------------------------------------

def repo_root_for_entry(path):
    """Walk up from an entry file looking for a '.pylgrim' ancestor; the repo
    root is that ancestor's parent. Returns None when there is none."""
    current = os.path.dirname(os.path.abspath(path))
    while True:
        if os.path.basename(current) == ".pylgrim":
            return os.path.dirname(current)
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def expand_target(path, report):
    """Turn one CLI PATH into a list of jobs: ('entry', file, expected_kind,
    repo_root) and ('redaction', file) tuples."""
    jobs = []
    ap = os.path.abspath(path)
    if os.path.isfile(ap):
        name = os.path.basename(ap)
        if name == "redaction.toml":
            jobs.append(("redaction", ap))
        elif name.endswith(".md"):
            parent = os.path.basename(os.path.dirname(ap))
            jobs.append(("entry", ap, DIR_KIND.get(parent), repo_root_for_entry(ap)))
        else:
            report.error(ap, "path",
                         "not a ledger file: expected a '.md' entry or redaction.toml")
        return jobs
    if os.path.isdir(ap):
        if os.path.basename(ap) == ".pylgrim":
            ledger, root = ap, os.path.dirname(ap)
        elif os.path.isdir(os.path.join(ap, ".pylgrim")):
            ledger, root = os.path.join(ap, ".pylgrim"), ap
        else:
            report.error(ap, "path",
                         "no .pylgrim directory found at %r (pass a repo root, a "
                         ".pylgrim directory, or entry files)" % display_path(ap))
            return jobs
        for sub, kind in sorted(DIR_KIND.items()):
            subdir = os.path.join(ledger, sub)
            if not os.path.isdir(subdir):
                continue
            for name in sorted(os.listdir(subdir)):
                if name.endswith(".md"):
                    jobs.append(("entry", os.path.join(subdir, name), kind, root))
        redaction = os.path.join(ledger, "redaction.toml")
        if os.path.isfile(redaction):
            jobs.append(("redaction", redaction))
        return jobs
    report.error(ap, "path", "path does not exist: %r" % display_path(ap))
    return jobs


def run(paths):
    """Validate every PATH. Returns (report, files_checked)."""
    report = Report()
    jobs = []
    for path in paths:
        jobs.extend(expand_target(path, report))
    for job in jobs:
        if job[0] == "entry":
            check_entry(job[1], job[2], job[3], report)
        else:
            check_redaction(job[1], report)
    return report, len(jobs)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate .pylgrim ledgers against the pylgrim v0 spec.")
    parser.add_argument("paths", nargs="*", default=None, metavar="PATH",
                        help="repo root, .pylgrim directory, or entry files "
                             "(default: current directory)")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="emit findings as a JSON list")
    parser.add_argument("--fix-names", action="store_true", dest="fix_names",
                        help="rename entry files whose names fail the filename "
                             "grammar to '<fresh ULID>-<sanitized slug>.md' "
                             "(content untouched), then validate")
    args = parser.parse_args(argv)
    paths = args.paths or ["."]

    if args.fix_names:
        paths = fix_names(paths, stream=sys.stderr if args.as_json else sys.stdout)
    report, files_checked = run(paths)
    if args.as_json:
        print(json.dumps(report.findings, indent=2))
    else:
        for f in report.findings:
            print("%s %s %s: %s" % (f["level"], f["path"], f["field"], f["message"]))
        print("%d file(s) checked: %d error(s), %d warning(s)" %
              (files_checked, report.error_count, report.warning_count))
    return 0 if report.error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
