"""Minimal CLI front-end (F1). Hook/recall commands arrive in F2."""

from __future__ import annotations

import argparse
import json
import sys

from .config import Config
from .index import Index
from .search import Search


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mnemo", description="Persistent memory over a markdown vault"
    )
    p.add_argument("--vault", help="vault path (default: $MNEMO_VAULT or cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("reindex", help="refresh the derived index from the vault")
    sp.add_argument("--full", action="store_true", help="reparse every note")

    ss = sub.add_parser("search", help="search notes (returns summaries, not bodies)")
    ss.add_argument("query")
    ss.add_argument("--type")
    ss.add_argument("--project")
    ss.add_argument("-k", type=int, default=5)
    ss.add_argument("--json", action="store_true")

    sg = sub.add_parser("get", help="print a full note by id")
    sg.add_argument("id")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    cfg = Config(args.vault)
    idx = Index(cfg.index_path)
    try:
        if args.cmd == "reindex":
            stats = idx.reindex(cfg.vault, full=args.full)
            print(json.dumps(stats))
        elif args.cmd == "search":
            res = Search(idx).search(
                args.query, type=args.type, project=args.project, k=args.k
            )
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                if not res:
                    print("(no matches)")
                for r in res:
                    proj = r["project"] or "-"
                    print(f"[{r['score']}] {r['title']}  ({r['type']}/{proj})")
                    if r["summary"]:
                        print(f"    {r['summary']}")
                    print(f"    {r['path']}")
        elif args.cmd == "get":
            note = Search(idx).get(args.id)
            print(json.dumps(note, ensure_ascii=False, indent=2) if note else "not found")
    finally:
        idx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
