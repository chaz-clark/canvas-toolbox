#!/usr/bin/env python3
"""Move the Canvas token + base URL out of a course's .env into ~/.canvas/config.

WHY: the agent should be able to run toolkit scripts without ever holding the secret.
`grade_guardian` blocks agent reads of ~/.canvas/config, but it deliberately leaves
`Read` on .env open (blocking it would also block Edit). So a token left in .env —
even commented out — stays readable. This script is the one sanctioned place that
reads that token: it runs in-process, never prints a value, and removes the keys from
.env once the global file is in place and the token is verified.

  uv run python lib/tools/cb_secure_token.py            # dry run (default)
  uv run python lib/tools/cb_secure_token.py --apply    # move it
  ... --env path/to/.env      # default: ./.env
  ... --replace               # let the .env value overwrite a DIFFERENT global one
  ... --test-dir DIR          # TEST MODE: use DIR/config instead of ~/.canvas/config
                              #   and skip the network check, so fake keys work and
                              #   your real global file is never read or written

Order of operations (a failure leaves .env untouched):
  1. read CANVAS_API_TOKEN / CANVAS_BASE_URL from .env (and the global file)
  2. verify the token with a read-only GET /api/v1/users/self
  3. write ~/.canvas/config (0600 on Mac/Linux; icacls on Windows)
  4. delete the two keys from .env, leaving every other line byte-for-byte

CANVAS_COURSE_ID never moves — it belongs to the course (see _env_loader).
Output names keys and counts only, never a value.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _env_loader  # noqa: E402
from _env_loader import GLOBAL_KEYS, force_utf8_console  # noqa: E402

HEADER = (
    "# canvas-toolbox global credentials — rotate the token HERE, once, for every\n"
    "# course repo. Only CANVAS_API_TOKEN and CANVAS_BASE_URL are read from this file;\n"
    "# a CANVAS_COURSE_ID here is IGNORED on purpose (it belongs in each course's .env).\n"
    "# `export` is deliberate so `source ~/.canvas/config` works for ad-hoc scripts.\n"
)


def _values(path: Path) -> dict[str, str]:
    """Non-empty GLOBAL_KEYS values from a dotenv-style file. Empty counts as absent."""
    from dotenv import dotenv_values
    if not path.is_file():
        return {}
    raw = dotenv_values(path)
    return {k: v for k, v in raw.items() if k in GLOBAL_KEYS and v}


def verify_token(token: str, base_url: str) -> bool:
    """Read-only check that the token authenticates. Never reports the token."""
    req = urllib.request.Request(
        base_url.rstrip("/") + "/api/v1/users/self",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def write_global(path: Path, values: dict[str, str]) -> str:
    """Atomically write the global file with owner-only access. Returns a perms note."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = HEADER + "".join(f"export {k}={values[k]}\n" for k in GLOBAL_KEYS if k in values)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".config.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body)
        if sys.platform != "win32":
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    if sys.platform != "win32":
        return "chmod 600"
    # Windows has no POSIX mode bits: drop inherited ACLs and grant only this user.
    try:
        user = os.environ.get("USERNAME", "")
        done = subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
            capture_output=True, timeout=15)
        if done.returncode == 0 and user:
            return "icacls (owner only)"
    except (OSError, subprocess.SubprocessError):
        pass
    return "WARNING: could not restrict permissions; check the file's ACL"


_KEY_LINE = re.compile(r"^\s*(?:export\s+)?(" + "|".join(GLOBAL_KEYS) + r")\s*=")


def strip_keys(env_path: Path) -> int:
    """Delete the GLOBAL_KEYS assignment lines from .env, keeping all other bytes
    (including CRLF endings) unchanged. Returns how many lines were removed."""
    text = env_path.read_bytes().decode("utf-8")
    kept, removed = [], 0
    for line in text.splitlines(keepends=True):
        if _KEY_LINE.match(line):
            removed += 1
        else:
            kept.append(line)
    env_path.write_bytes("".join(kept).encode("utf-8"))
    return removed


def run(env_path: Path, apply: bool, replace: bool, test_dir: Path | None = None) -> int:
    real = _env_loader.GLOBAL_CONFIG
    global_path = real if test_dir is None else test_dir / "config"
    if test_dir is not None:
        if global_path.resolve() == real.resolve():
            print("Refusing: --test-dir points at your real ~/.canvas folder.")
            return 1
        print(f"TEST MODE: using {global_path}; token check skipped; real global file untouched.")
    if not env_path.is_file():
        print(f"No .env at {env_path}")
        return 1
    local, existing = _values(env_path), _values(global_path)
    if not local:
        print("Nothing to move: .env has no CANVAS_API_TOKEN / CANVAS_BASE_URL.")
        return 0

    conflicts = [k for k in local if k in existing and local[k] != existing[k]]
    if conflicts and not replace:
        print(f"Refusing: {', '.join(conflicts)} differs between .env and {global_path}.")
        print("Re-run with --replace to let this .env's value win. Nothing was changed.")
        return 2

    merged = {**existing, **local}
    missing = [k for k in GLOBAL_KEYS if k not in merged]
    if missing:
        print(f"Cannot verify: {', '.join(missing)} is in neither .env nor the global file.")
        return 1

    print(f"Would move: {', '.join(sorted(local))}  ->  {global_path}")
    print(f"Would remove those keys from {env_path} (CANVAS_COURSE_ID stays).")
    if not apply:
        print("Dry run. Re-run with --apply to do it.")
        return 0

    if test_dir is None and not verify_token(merged["CANVAS_API_TOKEN"], merged["CANVAS_BASE_URL"]):
        print("Token check failed (GET /users/self). Nothing was changed.")
        return 1
    note = write_global(global_path, merged)
    removed = strip_keys(env_path)
    print(f"Done: wrote {global_path} ({note}); removed {removed} line(s) from {env_path}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    force_utf8_console()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--env", type=Path, default=Path(".env"), help="default: ./.env")
    ap.add_argument("--apply", action="store_true", help="make the change (default: dry run)")
    ap.add_argument("--replace", action="store_true",
                    help="overwrite a different value already in the global file")
    ap.add_argument("--test-dir", type=Path,
                    help="test mode: use <dir>/config as the global file, skip the network check")
    args = ap.parse_args(argv)
    return run(args.env, args.apply, args.replace, args.test_dir)


if __name__ == "__main__":
    sys.exit(main())
