#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "build_codemap.py")

results = []


def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((name, status, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail and status == "FAIL" else ""))


def run_codemap(*args):
    return subprocess.run([sys.executable, SCRIPT] + list(args), capture_output=True, text=True)


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


LANG_SAMPLES = {
    "app.py": (
        "class UserService:\n"
        "    pass\n\n"
        "def create_user(name):\n"
        "    pass\n\n"
        "@app.route(\"/users\")\n"
        "def list_users():\n"
        "    pass\n",
        ["class UserService", "def create_user", '@app.route("/users") def list_users'],
    ),
    "app.js": (
        "class Store {}\n\n"
        "function fetchData() {}\n\n"
        "router.get('/items', getItems);\n",
        ["class Store", "function fetchData()", "router.get('/items', getItems);"],
    ),
    "app.ts": (
        "export class Widget {}\n\n"
        "export function build() {}\n",
        ["export class Widget", "export function build()"],
    ),
    "main.go": (
        "package main\n\n"
        "func (s *Server) Handle(w http.ResponseWriter, r *http.Request) {}\n\n"
        "type Server struct {\n"
        "\taddr string\n"
        "}\n",
        ["func (s *Server) Handle(w http.ResponseWriter, r *http.Request)", "type Server struct"],
    ),
    "lib.rs": (
        "pub struct Config {\n"
        "    name: String,\n"
        "}\n\n"
        "pub fn load_config() -> Config {\n"
        "}\n",
        ["pub struct Config", "pub fn load_config() -> Config"],
    ),
    "App.java": (
        "public class UserController {\n"
        "}\n\n"
        "@GetMapping(\"/users\")\n"
        "public List<User> listUsers() {\n"
        "}\n",
        ["public class UserController", '@GetMapping("/users") public List<User> listUsers()'],
    ),
    "index.html": (
        "<html><head><title>Fixture App</title></head>\n"
        "<body>\n"
        "<script>\n"
        "function initApp() {\n"
        "}\n"
        "</script>\n"
        "</body></html>\n",
        ["<title>Fixture App</title>", "function initApp"],
    ),
}


def build_fixture(root, filler_count):
    for fname, (content, _expected) in LANG_SAMPLES.items():
        write(os.path.join(root, "src", fname), content)
    for i in range(filler_count):
        subdir = f"pkg{i % 12}/mod{i % 5}"
        ext = [".py", ".txt", ".md", ".js", ".json"][i % 5]
        content = f"value_{i} = {i}\n" if ext in (".py", ".js") else f"filler {i}\n"
        write(os.path.join(root, "filler", subdir, f"file_{i}{ext}"), content)
    return root


def test_language_extraction(tmp_root):
    build_fixture(tmp_root, filler_count=110)
    state_path = os.path.join(tmp_root, ".claude", "codemap", "state.json")
    output_path = os.path.join(tmp_root, ".claude", "codemap", "codemap.md")
    result = run_codemap("build", "--root", tmp_root, "--state", state_path, "--output", output_path)
    check("build exits cleanly on mixed-language fixture", result.returncode == 0, result.stderr)
    with open(state_path) as f:
        files = json.load(f)["files"]
    for fname, (_content, expected_symbols) in LANG_SAMPLES.items():
        key = f"src/{fname}"
        info = files.get(key)
        ok = info is not None
        if ok:
            for exp in expected_symbols:
                ok = ok and exp in info.get("symbols", [])
        check(f"symbols extracted correctly for {fname}", ok, info.get("symbols") if info else "missing from state")
    return state_path, output_path


def test_deletion_pruning(tmp_root, state_path, output_path):
    target = os.path.join(tmp_root, "filler", "pkg0", "mod0", "file_0.py")
    check("filler file_0.py exists before deletion", os.path.exists(target))
    os.remove(target)
    unrelated = os.path.relpath(os.path.join(tmp_root, "src", "app.py"), tmp_root).replace(os.sep, "/")
    result = run_codemap("build", "--root", tmp_root, "--state", state_path, "--output", output_path, "--paths", unrelated)
    check("targeted --paths rescan exits cleanly", result.returncode == 0, result.stderr)
    with open(state_path) as f:
        files = json.load(f)["files"]
    check(
        "deleted file pruned from state during --paths rescan (bug fix)",
        "filler/pkg0/mod0/file_0.py" not in files,
    )


def test_truncation_marker(tmp_root):
    lines = []
    for i in range(50):
        lines.append(f"def handler_{i}():")
        lines.append("    pass")
    write(os.path.join(tmp_root, "big.py"), "\n".join(lines) + "\n")
    state_path = os.path.join(tmp_root, ".claude", "codemap", "state.json")
    output_path = os.path.join(tmp_root, ".claude", "codemap", "codemap.md")
    result = run_codemap("build", "--root", tmp_root, "--state", state_path, "--output", output_path, "--paths", "big.py")
    check("targeted rescan of oversized file exits cleanly", result.returncode == 0, result.stderr)
    with open(state_path) as f:
        info = json.load(f)["files"]["big.py"]
    check("symbol_total tracked beyond the 40 cap", info["symbol_total"] == 50, info["symbol_total"])
    check("stored/shown symbols capped at 40", len(info["symbols"]) == 40, len(info["symbols"]))
    with open(output_path) as f:
        rendered = f.read()
    check('truncation marker "… +10 more" present in rendered codemap.md', "+10 more" in rendered)


def test_collapsing(filler_count=110):
    tmp_root = tempfile.mkdtemp(prefix="codemap_collapse_")
    try:
        build_fixture(tmp_root, filler_count=filler_count)
        state_path = os.path.join(tmp_root, ".claude", "codemap", "state.json")
        output_path = os.path.join(tmp_root, ".claude", "codemap", "codemap.md")
        run_codemap("build", "--root", tmp_root, "--state", state_path, "--output", output_path)
        dirs_dir = os.path.join(tmp_root, ".claude", "codemap", "dirs")
        check("large subtree produces at least one dirs/ submap", os.path.isdir(dirs_dir) and len(os.listdir(dirs_dir)) > 0)
        with open(output_path) as f:
            top = f.read()
        check("collapsed pointer appears in top-level codemap.md", "see dirs/" in top)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def test_performance(filler_count=520, bound_seconds=10):
    tmp_root = tempfile.mkdtemp(prefix="codemap_perf_")
    try:
        build_fixture(tmp_root, filler_count=filler_count)
        state_path = os.path.join(tmp_root, ".claude", "codemap", "state.json")
        output_path = os.path.join(tmp_root, ".claude", "codemap", "codemap.md")

        t0 = time.time()
        result = run_codemap("stat", "--root", tmp_root)
        stat_elapsed = time.time() - t0
        check("stat exits cleanly at 500+ files", result.returncode == 0, result.stderr)
        check(f"stat completes within {bound_seconds}s ({stat_elapsed:.2f}s actual)", stat_elapsed < bound_seconds)

        t0 = time.time()
        result = run_codemap("build", "--root", tmp_root, "--state", state_path, "--output", output_path)
        build_elapsed = time.time() - t0
        check("build exits cleanly at 500+ files", result.returncode == 0, result.stderr)
        check(f"build completes within {bound_seconds}s ({build_elapsed:.2f}s actual)", build_elapsed < bound_seconds)

        with open(state_path) as f:
            file_count = len(json.load(f)["files"])
        check("fixture actually exceeds 500 files", file_count > 500, file_count)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


def main():
    tmp_root = tempfile.mkdtemp(prefix="codemap_func_")
    try:
        state_path, output_path = test_language_extraction(tmp_root)
        test_deletion_pruning(tmp_root, state_path, output_path)
        test_truncation_marker(tmp_root)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    test_collapsing()
    test_performance()

    failed = [r for r in results if r[1] == "FAIL"]
    print()
    print(f"{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("FAILURES:")
        for name, status, detail in failed:
            print(f"  - {name}: {detail}")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
