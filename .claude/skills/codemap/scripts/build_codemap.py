#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone

BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".bmp",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".mov", ".wav", ".avi", ".m4a", ".flac",
    ".zip", ".tar", ".gz", ".7z", ".rar", ".iso", ".dmg", ".msi", ".bin",
    ".pdf", ".exe", ".dll", ".so", ".dylib", ".a", ".o", ".class", ".pyc",
    ".jar", ".war", ".ear", ".pyd", ".node", ".wasm",
    ".db", ".sqlite", ".sqlite3",
    ".lock",
}
IGNORE_DIRS = {
    ".git", ".claude", "node_modules", "__pycache__", ".venv", "venv",
    "env", "dist", "build", "target", ".next", ".cache", "coverage",
    ".pytest_cache", ".mypy_cache", "vendor",
}
MAX_FILE_SIZE = 2_000_000
MAX_SYMBOLS_PER_FILE = 40
SNIFF_BYTES = 8192
DEFAULT_COLLAPSE_THRESHOLD = 30


def list_files(root):
    git_dir = os.path.join(root, ".git")
    if os.path.isdir(git_dir):
        try:
            tracked = subprocess.run(
                ["git", "-C", root, "ls-files"],
                capture_output=True, text=True, check=True,
            ).stdout.splitlines()
            untracked = subprocess.run(
                ["git", "-C", root, "ls-files", "--others", "--exclude-standard"],
                capture_output=True, text=True, check=True,
            ).stdout.splitlines()
            files = sorted(set(tracked + untracked))
            if files:
                return files
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        for name in filenames:
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            files.append(rel.replace(os.sep, "/"))
    return sorted(files)


def read_and_sniff(path, size):
    if size > MAX_FILE_SIZE:
        return None, True
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return None, True
    if b"\x00" in raw[:SNIFF_BYTES]:
        return raw, True
    return raw, False


def _line_symbols(lines, pattern, decorator_prefixes=None, flags=0):
    regex = re.compile(pattern, flags)
    symbols = []
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        if regex.match(s):
            prefix = ""
            if decorator_prefixes and i > 0:
                prev = lines[i - 1].strip()
                if any(prev.startswith(p) for p in decorator_prefixes):
                    prefix = prev + " "
            cleaned = s.split("{")[0].strip().rstrip(":;,").strip()
            symbols.append((prefix + cleaned).strip())
    return symbols


def extract_python(text):
    lines = text.splitlines()
    symbols = []
    for i, line in enumerate(lines):
        m = re.match(r"^(class\s+\w+|(?:async\s+)?def\s+\w+)", line)
        if m:
            prefix = ""
            j = i - 1
            if j >= 0 and lines[j].strip().startswith("@"):
                prefix = lines[j].strip() + " "
            symbols.append((prefix + m.group(1)).strip())
    return symbols


JS_PATTERNS = [
    r"export\s+default\s+function\s+\w+",
    r"export\s+function\s+\w+",
    r"export\s+class\s+\w+",
    r"export\s+const\s+\w+\s*=",
    r"function\s+\w+",
    r"class\s+\w+",
    r"const\s+\w+\s*=\s*\([^)]*\)\s*=>",
    r"router\.(get|post|put|delete|patch)\(\s*['\"][^'\"]+['\"]",
    r"app\.(get|post|put|delete|patch)\(\s*['\"][^'\"]+['\"]",
    r"socket\.on\(\s*['\"][^'\"]+['\"]",
]
JS_COMBINED = re.compile("^(" + "|".join(JS_PATTERNS) + ")")


def extract_js(text):
    lines = text.splitlines()
    symbols = []
    for line in lines:
        s = line.strip()
        m = JS_COMBINED.match(s)
        if m:
            symbols.append(s.split("{")[0].strip().rstrip(",").strip())
    return symbols


def extract_cpp(text):
    lines = text.splitlines()
    symbols = []
    sig_re = re.compile(r"^[A-Za-z_][\w:\*&<>,\s]*\s+\w+\s*\([^;]*\)\s*\{?\s*$")
    for line in lines:
        s = line.strip()
        if not s or s.startswith("//") or s.startswith("*"):
            continue
        if re.match(r"^(class|struct|namespace)\s+\w+", s):
            symbols.append(s.rstrip("{").strip())
        elif sig_re.match(s) and not s.endswith(";") and "=" not in s.split("(")[0]:
            symbols.append(s.rstrip("{").strip())
    return symbols


def extract_html(text):
    symbols = []
    title = re.search(r"<title>(.*?)</title>", text, re.S)
    if title:
        symbols.append(f"<title>{title.group(1).strip()}</title>")
    for block in re.findall(r"<script[^>]*>(.*?)</script>", text, re.S):
        for line in block.splitlines():
            m = re.match(r"^\s*function\s+\w+", line)
            if m:
                symbols.append(m.group(0).strip())
    return symbols


GO_PATTERNS = [
    r"func\s+(\(\w+\s+\*?[\w\.]+\)\s+)?\w+",
    r"type\s+\w+\s+(struct|interface)",
    r"\w+\.(HandleFunc|Get|Post|Put|Delete|Patch|GET|POST|PUT|DELETE|PATCH)\(\s*[\"'][^\"']+[\"']",
]
GO_COMBINED = "^(" + "|".join(GO_PATTERNS) + ")"


def extract_go(text):
    return _line_symbols(text.splitlines(), GO_COMBINED)


RUST_PATTERNS = [
    r"(pub(\(\w+\))?\s+)?(async\s+)?fn\s+\w+",
    r"(pub\s+)?(struct|enum|trait)\s+\w+",
    r"impl(<[^>]*>)?\s+[\w:]+",
    r"\.route\(\s*[\"'][^\"']+[\"']",
]
RUST_COMBINED = "^(" + "|".join(RUST_PATTERNS) + ")"


def extract_rust(text):
    return _line_symbols(text.splitlines(), RUST_COMBINED, decorator_prefixes=["#["])


JAVA_PATTERNS = [
    r"(public|private|protected)\s+(static\s+)?(final\s+)?(abstract\s+)?(synchronized\s+)?[\w<>\[\],\.]+\s+\w+\s*\([^;{]*\)\s*(throws\s+[\w.,\s]+)?\s*\{?\s*$",
    r"(public|private|protected)?\s*(static\s+)?(final\s+)?(abstract\s+)?(class|interface|enum|record)\s+\w+",
]
JAVA_COMBINED = "^(" + "|".join(JAVA_PATTERNS) + ")"


def extract_java(text):
    return _line_symbols(text.splitlines(), JAVA_COMBINED, decorator_prefixes=["@"])


KOTLIN_PATTERNS = [
    r"(public\s+|private\s+|internal\s+|protected\s+)?(override\s+|open\s+|abstract\s+|suspend\s+)*fun\s+\w+",
    r"(public\s+|private\s+|internal\s+)?(data\s+|sealed\s+|abstract\s+|open\s+)?(class|interface|object)\s+\w+",
    r"\w+\.(get|post|put|delete|patch)\(\s*[\"'][^\"']+[\"']",
]
KOTLIN_COMBINED = "^(" + "|".join(KOTLIN_PATTERNS) + ")"


def extract_kotlin(text):
    return _line_symbols(text.splitlines(), KOTLIN_COMBINED, decorator_prefixes=["@"])


CSHARP_PATTERNS = [
    r"(public|private|protected|internal)\s+(static\s+)?(async\s+)?(override\s+|virtual\s+|abstract\s+)?[\w<>\[\],\.\?]+\s+\w+\s*\([^;{]*\)\s*\{?\s*$",
    r"(public|private|protected|internal)?\s*(static\s+)?(sealed\s+)?(abstract\s+)?(partial\s+)?(class|interface|struct|enum|record)\s+\w+",
]
CSHARP_COMBINED = "^(" + "|".join(CSHARP_PATTERNS) + ")"


def extract_csharp(text):
    return _line_symbols(text.splitlines(), CSHARP_COMBINED, decorator_prefixes=["["])


RUBY_PATTERNS = [
    r"def\s+(self\.)?\w+[\?\!]?",
    r"(class|module)\s+\w+",
    r"(get|post|put|patch|delete)\s+[\"'][^\"']+[\"']",
]
RUBY_COMBINED = "^(" + "|".join(RUBY_PATTERNS) + ")"


def extract_ruby(text):
    return _line_symbols(text.splitlines(), RUBY_COMBINED)


PHP_PATTERNS = [
    r"(public\s+|private\s+|protected\s+)?(static\s+)?function\s+&?\w+",
    r"(class|interface|trait)\s+\w+",
    r"Route::(get|post|put|delete|patch)\(",
]
PHP_COMBINED = "^(" + "|".join(PHP_PATTERNS) + ")"


def extract_php(text):
    return _line_symbols(text.splitlines(), PHP_COMBINED, decorator_prefixes=["#["])


SWIFT_PATTERNS = [
    r"(public\s+|private\s+|internal\s+|open\s+|fileprivate\s+)?(static\s+)?(override\s+)?func\s+\w+",
    r"(public\s+|private\s+|open\s+)?(final\s+)?(class|struct|enum|protocol|extension)\s+\w+",
    r"\w+\.(get|post|put|delete)\(\s*[\"'][^\"']+[\"']",
]
SWIFT_COMBINED = "^(" + "|".join(SWIFT_PATTERNS) + ")"


def extract_swift(text):
    return _line_symbols(text.splitlines(), SWIFT_COMBINED)


SHELL_PATTERNS = [
    r"function\s+\w+",
    r"\w+\s*\(\)\s*\{?",
]
SHELL_COMBINED = "^(" + "|".join(SHELL_PATTERNS) + ")"


def extract_shell(text):
    return _line_symbols(text.splitlines(), SHELL_COMBINED)


SQL_PATTERNS = [
    r"CREATE\s+(OR\s+REPLACE\s+)?(TABLE|VIEW|FUNCTION|PROCEDURE|INDEX|TRIGGER)\s+(IF\s+NOT\s+EXISTS\s+)?[`\"\[]?\w+",
]
SQL_COMBINED = "^(" + "|".join(SQL_PATTERNS) + ")"


def extract_sql(text):
    return _line_symbols(text.splitlines(), SQL_COMBINED, flags=re.IGNORECASE)


EXTRACTORS = {
    ".py": extract_python,
    ".js": extract_js, ".jsx": extract_js, ".ts": extract_js, ".tsx": extract_js,
    ".mjs": extract_js, ".cjs": extract_js,
    ".c": extract_cpp, ".cpp": extract_cpp, ".cc": extract_cpp, ".cxx": extract_cpp,
    ".h": extract_cpp, ".hpp": extract_cpp, ".hh": extract_cpp,
    ".html": extract_html, ".htm": extract_html,
    ".go": extract_go,
    ".rs": extract_rust,
    ".java": extract_java,
    ".kt": extract_kotlin, ".kts": extract_kotlin,
    ".cs": extract_csharp,
    ".rb": extract_ruby,
    ".php": extract_php,
    ".swift": extract_swift,
    ".sh": extract_shell, ".bash": extract_shell,
    ".sql": extract_sql,
}


def extract_symbols(rel_path, text):
    ext = os.path.splitext(rel_path)[1].lower()
    extractor = EXTRACTORS.get(ext)
    if not extractor:
        return [], 0
    try:
        all_symbols = extractor(text)
    except Exception:
        all_symbols = []
    return all_symbols[:MAX_SYMBOLS_PER_FILE], len(all_symbols)


def cmd_stat(args):
    files = list_files(args.root)
    file_count = 0
    total_lines = 0
    for f in files:
        ext = os.path.splitext(f)[1].lower()
        if ext in BINARY_EXTS:
            continue
        full = os.path.join(args.root, f)
        try:
            size = os.path.getsize(full)
        except OSError:
            continue
        raw, is_binary = read_and_sniff(full, size)
        if raw is None or is_binary:
            continue
        file_count += 1
        total_lines += raw.count(b"\n") + 1
    print(json.dumps({"file_count": file_count, "total_lines": total_lines}, indent=2))


def load_state(state_path):
    if os.path.exists(state_path):
        with open(state_path) as f:
            return json.load(f)
    return {"generated": "", "root": "", "files": {}}


def save_state(state_path, state):
    os.makedirs(os.path.dirname(os.path.abspath(state_path)), exist_ok=True)
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)


def dirs_dir_for(output_path):
    return os.path.join(os.path.dirname(os.path.abspath(output_path)) or ".", "dirs")


def build_tree(files):
    tree = {}
    for path in sorted(files):
        parts = path.split("/")
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node.setdefault("__files__", []).append(parts[-1])
    return tree


def count_subtree_files(node):
    total = len(node.get("__files__", []))
    for key, child in node.items():
        if key == "__files__":
            continue
        total += count_subtree_files(child)
    return total


def sum_subtree_lines(node, files, prefix):
    total = 0
    for fname in node.get("__files__", []):
        full = f"{prefix}/{fname}" if prefix else fname
        total += files.get(full, {}).get("lines", 0)
    for key, child in node.items():
        if key == "__files__":
            continue
        child_path = f"{prefix}/{key}" if prefix else key
        total += sum_subtree_lines(child, files, child_path)
    return total


def render_file_entry(fname, info, depth):
    lines = []
    if info.get("binary"):
        lines.append("  " * depth + f"- {fname} (binary, skipped)")
        return lines
    header = fname
    purpose = info.get("purpose") or ""
    if purpose:
        header += f" — {purpose}"
    header += f" ({info.get('lines', 0)} lines)"
    lines.append("  " * depth + f"- {header}")
    symbols = info.get("symbols", [])
    total = info.get("symbol_total", len(symbols))
    for sym in symbols:
        lines.append("  " * (depth + 1) + f"· {sym}")
    if total > len(symbols):
        lines.append("  " * (depth + 1) + f"… +{total - len(symbols)} more")
    return lines


def render_node(node, files, prefix, depth, threshold, max_depth, dirs_root):
    lines = []
    subdirs = sorted(k for k in node if k != "__files__")
    for key in subdirs:
        child = node[key]
        child_path = f"{prefix}/{key}" if prefix else key
        child_file_count = count_subtree_files(child)
        depth_exceeded = max_depth is not None and (depth + 1) > max_depth
        if child_file_count > threshold or depth_exceeded:
            child_lines = render_node(child, files, child_path, 0, threshold, None, dirs_root)
            child_line_total = sum_subtree_lines(child, files, child_path)
            submap_name = child_path.replace("/", "__") + ".md"
            os.makedirs(dirs_root, exist_ok=True)
            with open(os.path.join(dirs_root, submap_name), "w") as f:
                f.write(f"# {child_path}/\n{child_file_count} files, {child_line_total} lines\n\n")
                f.write("\n".join(child_lines) + "\n")
            lines.append("  " * depth + f"- {key}/ ({child_file_count} files — see dirs/{submap_name})")
        else:
            lines.append("  " * depth + f"- {key}/")
            lines.extend(render_node(child, files, child_path, depth + 1, threshold, max_depth, dirs_root))
    for fname in sorted(node.get("__files__", [])):
        full = f"{prefix}/{fname}" if prefix else fname
        info = files.get(full, {})
        lines.extend(render_file_entry(fname, info, depth))
    return lines


def render(state, collapse_threshold, max_depth, dirs_root):
    files = state.get("files", {})
    tree = build_tree(files)
    if os.path.isdir(dirs_root):
        shutil.rmtree(dirs_root)
    body = render_node(tree, files, "", 0, collapse_threshold, max_depth, dirs_root)
    header = ["# Codemap", f"Generated: {state.get('generated', '')} | {len(files)} files", ""]
    return "\n".join(header + body) + "\n"


def cmd_build(args):
    state = load_state(args.state)
    existing_files = state.get("files", {})
    all_files = list_files(args.root)
    all_files_set = set(all_files)

    if args.paths:
        scan_targets = [p for p in args.paths if p in all_files_set]
        carry_over = {f: v for f, v in existing_files.items() if f not in scan_targets and f in all_files_set}
    else:
        scan_targets = all_files
        carry_over = {}

    new_files = dict(carry_over)
    for rel in scan_targets:
        full = os.path.join(args.root, rel)
        ext = os.path.splitext(rel)[1].lower()
        try:
            size = os.path.getsize(full)
        except OSError:
            continue
        if ext in BINARY_EXTS:
            new_files[rel] = {"binary": True, "size": size}
            continue
        try:
            mtime = os.path.getmtime(full)
        except OSError:
            continue
        old = existing_files.get(rel)
        if old and not old.get("binary") and old.get("mtime") == mtime and not args.force:
            new_files[rel] = old
            continue
        raw, is_binary = read_and_sniff(full, size)
        if raw is None:
            continue
        if is_binary:
            new_files[rel] = {"binary": True, "size": size}
            continue
        text = raw.decode("utf-8", errors="ignore")
        symbols, symbol_total = extract_symbols(rel, text)
        new_files[rel] = {
            "mtime": mtime,
            "lines": text.count("\n") + 1,
            "symbols": symbols,
            "symbol_total": symbol_total,
            "purpose": old.get("purpose", "") if old else "",
        }

    new_files = {f: v for f, v in new_files.items() if f in all_files_set}

    state = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "root": os.path.abspath(args.root),
        "files": new_files,
    }
    save_state(args.state, state)
    dirs_root = dirs_dir_for(args.output)
    with open(args.output, "w") as f:
        f.write(render(state, args.collapse_threshold, args.depth, dirs_root))
    print(f"codemap: {len(new_files)} files indexed -> {args.output}")


def load_purpose_file(path):
    with open(path, "r") as f:
        content = f.read()
    stripped = content.strip()
    if stripped.startswith("{"):
        data = json.loads(stripped)
        return {str(k): str(v) for k, v in data.items()}
    result = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        path_part, _, purpose_part = line.partition("=")
        result[path_part.strip()] = purpose_part.strip()
    return result


def cmd_set_purpose(args):
    if not args.set and not args.set_purpose_file:
        raise SystemExit("set-purpose needs --set or --set-purpose-file")
    state = load_state(args.state)
    files = state.setdefault("files", {})
    updates = {}
    for item in args.set or []:
        if "=" not in item:
            continue
        path, _, purpose = item.partition("=")
        updates[path.strip()] = purpose.strip()
    if args.set_purpose_file:
        updates.update(load_purpose_file(args.set_purpose_file))
    for path, purpose in updates.items():
        if path in files:
            files[path]["purpose"] = purpose
        else:
            files[path] = {"lines": 0, "symbols": [], "symbol_total": 0, "purpose": purpose}
    save_state(args.state, state)
    dirs_root = dirs_dir_for(args.output)
    with open(args.output, "w") as f:
        f.write(render(state, args.collapse_threshold, args.depth, dirs_root))
    print(f"updated purpose for {len(updates)} file(s) -> {args.output}")


def main():
    parser = argparse.ArgumentParser(description="Lightweight repo structure/symbol indexer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_stat = sub.add_parser("stat", help="fast file/line count, no symbol extraction")
    p_stat.add_argument("--root", default=".")
    p_stat.set_defaults(func=cmd_stat)

    p_build = sub.add_parser("build", help="build or incrementally update the codemap")
    p_build.add_argument("--root", default=".")
    p_build.add_argument("--state", default=".claude/codemap/state.json")
    p_build.add_argument("--output", default=".claude/codemap/codemap.md")
    p_build.add_argument("--paths", nargs="*", default=None, help="only rescan these relative paths")
    p_build.add_argument("--force", action="store_true", help="ignore mtime cache, rescan everything")
    p_build.add_argument("--collapse-threshold", type=int, default=DEFAULT_COLLAPSE_THRESHOLD, dest="collapse_threshold")
    p_build.add_argument("--depth", type=int, default=None, help="max directory levels expanded inline")
    p_build.set_defaults(func=cmd_build)

    p_purpose = sub.add_parser("set-purpose", help="attach a one-line purpose to indexed files")
    p_purpose.add_argument("--state", default=".claude/codemap/state.json")
    p_purpose.add_argument("--output", default=".claude/codemap/codemap.md")
    p_purpose.add_argument("--set", nargs="+", default=None, help="path=purpose text, space separated, quote each")
    p_purpose.add_argument("--set-purpose-file", dest="set_purpose_file", default=None,
                            help="file with JSON {path: purpose} or newline-delimited path=purpose")
    p_purpose.add_argument("--collapse-threshold", type=int, default=DEFAULT_COLLAPSE_THRESHOLD, dest="collapse_threshold")
    p_purpose.add_argument("--depth", type=int, default=None)
    p_purpose.set_defaults(func=cmd_set_purpose)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
