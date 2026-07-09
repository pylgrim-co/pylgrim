#!/usr/bin/env python3
# VENDORED: canonical copy at spec/scripts/inventory.py. Edit there, then run tools/sync_scripts.py.
"""inventory.py collects deterministic repository facts for the pylgrim map
skill: git history shape, existing intent artifacts (CLAUDE.md, ADRs, lint
configs, CI workflows, manifests), a tree summary, knowledge-graph output
directories, and mechanical privacy flags. It reports facts only; every
judgment about what the facts mean belongs to the skill reading them.
"""

import argparse
import fnmatch
import json
import os
import subprocess
import sys

SKIP_DIRS = {".git"}

SINGLE_ARTIFACTS = [
    "CLAUDE.md",
    "CLAUDE.local.md",
    "AGENTS.md",
    "AGENTS.override.md",
    "GEMINI.md",
    "CONVENTIONS.md",
    ".cursorrules",
    ".windsurfrules",
    ".clinerules",
    ".roorules",
    ".goosehints",
    ".junie/guidelines.md",
    ".github/copilot-instructions.md",
    "CODEOWNERS",
    ".github/CODEOWNERS",
    "docs/CODEOWNERS",
    "README.md",
    "CONTRIBUTING.md",
    "package.json",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "Gemfile",
    "pom.xml",
    "ruff.toml",
    ".rubocop.yml",
    "clippy.toml",
    "biome.json",
]

ROOT_GLOB_ARTIFACTS = [".eslintrc*", "eslint.config.*"]
# Tool-specific rule DIRECTORIES (reported with a file count, like .cursor/rules).
RULE_DIRS = [".cursor/rules", ".windsurf/rules", ".clinerules", ".roo/rules"]
DOCS_DIR_PREFIXES = ["adr", "decisions", "architecture"]
PRIVACY_DIR_NAMES = {"fixtures", "testdata", "seeds"}
PRIVACY_DIR_THRESHOLD = 20


def fwd(path):
    return path.replace("\\", "/")


def run_git(root, *args):
    """Run one git command; returns stdout or None on any failure."""
    try:
        proc = subprocess.run(
            ["git"] + list(args), cwd=root, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def git_facts(root):
    inside = run_git(root, "rev-parse", "--is-inside-work-tree")
    if inside is None or inside.strip() != "true":
        return {"available": False,
                "note": "not a git repository (or git is not installed)"}
    facts = {"available": True}
    head = run_git(root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head:
        facts["default_branch"] = head.strip().split("/", 1)[-1]
    else:
        current = run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
        facts["default_branch"] = current.strip() if current else "(unknown)"
    log = run_git(root, "log", "-30", "--pretty=%s")
    facts["recent_commit_subjects"] = log.strip().split("\n") if log and log.strip() else []
    branches = run_git(root, "branch", "--format=%(refname:short)")
    facts["local_branches"] = sorted(branches.strip().split("\n")) if branches and branches.strip() else []
    names = run_git(root, "log", "--name-only", "-200", "--pretty=format:")
    counts = {}
    if names:
        for line in names.split("\n"):
            line = line.strip()
            if line:
                counts[line] = counts.get(line, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:20]
    facts["top_changed_paths"] = [{"path": p, "changes": c} for p, c in top]
    return facts


def first_line_of(path):
    """First markdown heading in the file, else the first non-empty line,
    truncated to 120 characters."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            head = [next(fh, "") for _ in range(50)]
    except OSError:
        return ""
    fallback = ""
    for line in head:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return stripped[:120]
        if not fallback:
            fallback = stripped[:120]
    return fallback


def describe_file(root, rel):
    full = os.path.join(root, rel)
    return {"path": fwd(rel), "bytes": os.path.getsize(full),
            "first_line": first_line_of(full)}


def count_files(path):
    total = 0
    for _, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        total += len(files)
    return total


def intent_artifacts(root):
    found = []
    for rel in SINGLE_ARTIFACTS:
        full = os.path.join(root, rel)
        if os.path.isfile(full):
            found.append(describe_file(root, rel))
    for pattern in ROOT_GLOB_ARTIFACTS:
        try:
            names = sorted(os.listdir(root))
        except OSError:
            names = []
        for name in names:
            if fnmatch.fnmatch(name, pattern) and os.path.isfile(os.path.join(root, name)):
                found.append(describe_file(root, name))

    gh_instructions = os.path.join(root, ".github", "instructions")
    if os.path.isdir(gh_instructions):
        for name in sorted(os.listdir(gh_instructions)):
            rel = ".github/instructions/" + name
            if name.endswith(".instructions.md") and os.path.isfile(os.path.join(root, rel)):
                found.append(describe_file(root, rel))

    dirs = []
    for rel in RULE_DIRS:
        full = os.path.join(root, *rel.split("/"))
        if os.path.isdir(full):
            dirs.append({"path": rel, "files": count_files(full)})
    docs = os.path.join(root, "docs")
    if os.path.isdir(docs):
        for name in sorted(os.listdir(docs)):
            lowered = name.lower()
            if any(lowered.startswith(p) for p in DOCS_DIR_PREFIXES):
                full = os.path.join(docs, name)
                rel = "docs/" + name
                if os.path.isdir(full):
                    dirs.append({"path": rel, "files": count_files(full)})
                else:
                    found.append(describe_file(root, rel))

    workflows = []
    wf_dir = os.path.join(root, ".github", "workflows")
    if os.path.isdir(wf_dir):
        workflows = sorted(n for n in os.listdir(wf_dir)
                           if n.endswith((".yml", ".yaml")))
    return {"files": found, "dirs": dirs, "ci_workflows": workflows}


def tree_summary(root):
    top_dirs = []
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        entries = []
    for name in entries:
        full = os.path.join(root, name)
        if os.path.isdir(full) and name not in SKIP_DIRS:
            top_dirs.append({"dir": name, "files": count_files(full)})
    ext_counts = {}
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in files:
            _, ext = os.path.splitext(name)
            ext = ext.lower() if ext else "(none)"
            ext_counts[ext] = ext_counts.get(ext, 0) + 1
    top_exts = sorted(ext_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    return {"top_level_dirs": top_dirs,
            "extension_histogram": [{"ext": e, "files": c} for e, c in top_exts]}


def knowledge_graphs(root):
    found = []
    for name in (".understand", "understand", ".pylgrim"):
        full = os.path.join(root, name)
        if os.path.isdir(full):
            found.append({"path": name, "files": count_files(full)})
    # understand-anything writes knowledge-graph.json into its output dir.
    try:
        for name in sorted(os.listdir(root)):
            full = os.path.join(root, name)
            if os.path.isdir(full) and name not in SKIP_DIRS and \
                    os.path.isfile(os.path.join(full, "knowledge-graph.json")) and \
                    not any(f["path"] == name for f in found):
                found.append({"path": name, "files": count_files(full)})
    except OSError:
        pass
    return found


def privacy_flags(root):
    """Deterministic flags only: file names and mechanical counts. Whether a
    flag matters is the map skill's question, not this script's."""
    env_files = []
    key_files = []
    big_fixture_dirs = []
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        rel_dir = os.path.relpath(dirpath, root)
        rel_dir = "" if rel_dir == "." else fwd(rel_dir)
        for name in sorted(files):
            rel = name if not rel_dir else rel_dir + "/" + name
            if fnmatch.fnmatch(name, ".env*"):
                env_files.append(rel)
            if fnmatch.fnmatch(name, "*.pem") or fnmatch.fnmatch(name, "*.key") \
                    or fnmatch.fnmatch(name, "id_rsa*"):
                key_files.append(rel)
        base = os.path.basename(dirpath)
        if base in PRIVACY_DIR_NAMES:
            n = count_files(dirpath)
            if n > PRIVACY_DIR_THRESHOLD:
                big_fixture_dirs.append({"path": rel_dir or base, "files": n})
    return {"env_files": env_files, "key_shaped_files": key_files,
            "large_fixture_dirs": big_fixture_dirs}


def build(root):
    return {
        "repo_root": fwd(os.path.abspath(root)),
        "git": git_facts(root),
        "intent_artifacts": intent_artifacts(root),
        "tree": tree_summary(root),
        "knowledge_graphs": knowledge_graphs(root),
        "privacy_flags": privacy_flags(root),
    }


def render_text(data):
    out = []
    out.append("repo root: %s" % data["repo_root"])
    out.append("")
    out.append("== git ==")
    git = data["git"]
    if not git["available"]:
        out.append(git["note"])
    else:
        out.append("default branch: %s" % git["default_branch"])
        out.append("local branches: %s" % (", ".join(git["local_branches"]) or "(none)"))
        out.append("recent commits (%d):" % len(git["recent_commit_subjects"]))
        for subject in git["recent_commit_subjects"]:
            out.append("  %s" % subject)
        out.append("most-changed paths (last 200 commits):")
        for item in git["top_changed_paths"]:
            out.append("  %4d  %s" % (item["changes"], item["path"]))
    out.append("")
    out.append("== intent artifacts ==")
    ia = data["intent_artifacts"]
    if not (ia["files"] or ia["dirs"] or ia["ci_workflows"]):
        out.append("(none found)")
    for f in ia["files"]:
        out.append("  %s (%d bytes) %s" % (f["path"], f["bytes"], f["first_line"]))
    for d in ia["dirs"]:
        out.append("  %s/ (%d files)" % (d["path"], d["files"]))
    if ia["ci_workflows"]:
        out.append("  ci workflows: %s" % ", ".join(ia["ci_workflows"]))
    out.append("")
    out.append("== tree ==")
    for d in data["tree"]["top_level_dirs"]:
        out.append("  %s/ (%d files)" % (d["dir"], d["files"]))
    out.append("  extensions: %s" % ", ".join(
        "%s x%d" % (e["ext"], e["files"]) for e in data["tree"]["extension_histogram"]))
    out.append("")
    out.append("== knowledge graphs ==")
    if not data["knowledge_graphs"]:
        out.append("(none found)")
    for k in data["knowledge_graphs"]:
        out.append("  %s/ (%d files)" % (k["path"], k["files"]))
    out.append("")
    out.append("== privacy flags (mechanical, no judgment) ==")
    pf = data["privacy_flags"]
    if not (pf["env_files"] or pf["key_shaped_files"] or pf["large_fixture_dirs"]):
        out.append("(none)")
    for p in pf["env_files"]:
        out.append("  env file: %s" % p)
    for p in pf["key_shaped_files"]:
        out.append("  key-shaped file: %s" % p)
    for d in pf["large_fixture_dirs"]:
        out.append("  large fixture dir: %s/ (%d files)" % (d["path"], d["files"]))
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Deterministic repository facts for the pylgrim map skill.")
    parser.add_argument("--repo-root", default=".",
                        help="repository root to inventory (default: current directory)")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="emit structured JSON instead of readable text")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.repo_root)
    if not os.path.isdir(root):
        print("error: repo root %s is not a directory" % fwd(root), file=sys.stderr)
        return 2
    data = build(root)
    if args.as_json:
        print(json.dumps(data, indent=2))
    else:
        print(render_text(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
