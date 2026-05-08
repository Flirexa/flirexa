#!/usr/bin/env python3
"""Fail if any FastAPI route handler is `async def` but blocks the event
loop with sync I/O (no `await`, but uses sync SQLAlchemy / requests /
subprocess). Such routes serialize the entire panel on the single uvicorn
event loop, which is what made Herbert's panel hang for seconds in
1.5.80 before the mass conversion in 1.5.82.

Run with no args from the repo root:

    python3 scripts/audit_async_routes.py

Exits 0 if clean, 1 if any offenders found. Suitable for pre-commit or CI.

Whitelisted async patterns (legitimate, not flagged):
    - `await ...` anywhere in the body
    - `async with` / `async for`
    - any parameter typed `UploadFile` (FastAPI requires async for those)
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path


def is_route_decorator(decorator: ast.AST) -> bool:
    """True for @router.<verb>(...) and @app.<verb>(...) shapes."""
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    try:
        expr = ast.unparse(target)
    except Exception:
        return False
    if not any(verb in expr for verb in ("get", "post", "put", "delete", "patch")):
        return False
    return ".router." in f".{expr}" or expr.startswith("router.") or expr.startswith("app.")


def has_async_only_construct(node: ast.AsyncFunctionDef) -> bool:
    """Routes containing await / async-with / async-for / UploadFile must
    stay `async def`. Skip those."""
    for sub in ast.walk(node):
        if isinstance(sub, (ast.Await, ast.AsyncWith, ast.AsyncFor)):
            return True
        if isinstance(sub, ast.arg) and sub.annotation is not None:
            try:
                if "UploadFile" in ast.unparse(sub.annotation):
                    return True
            except Exception:
                pass
    return False


SYNC_DB_PREFIXES = (
    "db.query", "db.execute", "db.commit", "db.add", "db.delete",
    "db.refresh", "db.flush", "db.scalar", "db.merge", "db.expunge",
    "db.rollback",
)


def has_sync_io(node: ast.AsyncFunctionDef) -> tuple[bool, str]:
    """Look for sync DB / requests / subprocess calls. Returns (found, kind)."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute):
            try:
                expr = ast.unparse(sub)
            except Exception:
                continue
            if any(expr.startswith(p) for p in SYNC_DB_PREFIXES):
                return True, "sync-db"
            if "requests." in expr and "requests.exceptions" not in expr:
                return True, "sync-http"
            if "subprocess." in expr or expr.startswith("os.system"):
                return True, "sync-subproc"
    return False, ""


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    routes_dir = repo_root / "src" / "api" / "routes"
    if not routes_dir.is_dir():
        print(f"audit_async_routes: {routes_dir} not found", file=sys.stderr)
        return 2

    offenders: list[tuple[str, int, str, str]] = []
    for py_file in sorted(routes_dir.glob("*.py")):
        try:
            tree = ast.parse(py_file.read_text(), filename=str(py_file))
        except SyntaxError as exc:
            print(f"audit_async_routes: cannot parse {py_file}: {exc}", file=sys.stderr)
            return 2
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            if not any(is_route_decorator(d) for d in node.decorator_list):
                continue
            if has_async_only_construct(node):
                continue
            found, kind = has_sync_io(node)
            if found:
                offenders.append((py_file.name, node.lineno, node.name, kind))

    if not offenders:
        print("audit_async_routes: clean (no event-loop-blocking routes)")
        return 0

    print(f"audit_async_routes: found {len(offenders)} route(s) that block the event loop:\n")
    for fname, lineno, fn, kind in offenders:
        print(f"  {fname}:{lineno}  async def {fn}(...)  [{kind}]")
    print(
        "\nFix: drop the `async` keyword. FastAPI runs `def` handlers in a "
        "thread pool so they no longer block the loop.\n"
        "If the route legitimately needs `async def` (websockets, "
        "background streaming, etc.), refactor the sync I/O out — do not "
        "ignore this check."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
