#!/usr/bin/env python
"""Run every file in sql/ in order, substituting {CONSTANTS} from app/config.py."""
import pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
import config                      # noqa: E402
from conn import connect           # noqa: E402

SUBS = config.subs()


def statements(text: str):
    """Split on ';' at end of line, ignoring comment-only chunks."""
    for raw in text.split(";\n"):
        s = raw.strip().rstrip(";").strip()
        if s and not all(l.strip().startswith("--") or not l.strip() for l in s.splitlines()):
            yield s


def main():
    files = sorted((ROOT / "sql").glob("*.sql"))
    with connect() as cn:
        for f in files:
            body = f.read_text().format(**SUBS)
            for stmt in statements(body):
                head = " ".join(stmt.split())[:70]
                t0 = time.time()
                with cn.cursor() as c:
                    c.execute(stmt)
                print(f"[{f.name}] {time.time()-t0:6.2f}s  {head}", flush=True)
    print("sql/ complete")


if __name__ == "__main__":
    main()
