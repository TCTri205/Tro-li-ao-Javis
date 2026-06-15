"""Restore PostgreSQL from leader pg_dump (COPY format). Requires psql via Docker or PATH."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DUMP = ROOT / "dump-app_db-202606041640.sql"
DEFAULT_RESET = ROOT / "db" / "reset_all.sql"


def _run(cmd: list[str], *, input_path: Path | None = None) -> None:
    print("+", " ".join(cmd))
    if input_path is not None:
        with input_path.open("r", encoding="utf-8") as fh:
            proc = subprocess.run(cmd, stdin=fh, check=False)
    else:
        proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def _sanitize_dump(dump_path: Path) -> Path:
    skip_fragments = (
        "transaction_timeout",
        "OWNER TO postgres",
        "REVOKE USAGE ON SCHEMA public FROM PUBLIC",
    )
    lines = dump_path.read_text(encoding="utf-8").splitlines()
    if not any(any(frag in line for frag in skip_fragments) for line in lines):
        return dump_path
    out = dump_path.parent / ".restore_dump_sanitized.sql"
    out.write_text(
        "\n".join(
            line for line in lines if not any(frag in line for frag in skip_fragments)
        )
        + "\n",
        encoding="utf-8",
    )
    return out


def restore(
    dump_path: Path,
    *,
    use_docker: bool,
    db_user: str,
    db_name: str,
    reset_first: bool,
) -> None:
    dump_path = _sanitize_dump(dump_path.resolve())
    if not dump_path.is_file():
        raise SystemExit(f"Dump not found: {dump_path}")

    if use_docker:
        base = ["docker", "compose", "exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1", "-U", db_user, "-d", db_name]
        compose_cwd = ROOT
    else:
        base = ["psql", "-v", "ON_ERROR_STOP=1", "-U", db_user, "-d", db_name]
        compose_cwd = None

    def psql_file(path: Path) -> None:
        cmd = list(base) + ["-f", "-"]
        if compose_cwd is not None:
            _run(cmd, input_path=path)
        else:
            _run(cmd, input_path=path)

    if reset_first:
        if use_docker:
            old = Path.cwd()
            try:
                import os

                os.chdir(compose_cwd)
                _run(list(base) + ["-f", "-"], input_path=DEFAULT_RESET)
            finally:
                os.chdir(old)
        else:
            _run(list(base) + ["-f", "-"], input_path=DEFAULT_RESET)

    if use_docker:
        import os

        old = Path.cwd()
        try:
            os.chdir(compose_cwd)
            _run(list(base) + ["-f", "-"], input_path=dump_path)
        finally:
            os.chdir(old)
    else:
        _run(list(base) + ["-f", "-"], input_path=dump_path)

    print(f"Restored {dump_path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore app_db from leader pg_dump")
    parser.add_argument("--dump", type=Path, default=DEFAULT_DUMP)
    parser.add_argument("--docker", action="store_true", default=True)
    parser.add_argument("--no-docker", dest="docker", action="store_false")
    parser.add_argument("--user", default="app_user")
    parser.add_argument("--database", default="app_db")
    parser.add_argument("--no-reset", action="store_true", help="Skip DROP SCHEMA (fail if tables exist)")
    args = parser.parse_args()
    restore(
        args.dump.resolve(),
        use_docker=args.docker,
        db_user=args.user,
        db_name=args.database,
        reset_first=not args.no_reset,
    )


if __name__ == "__main__":
    main()
