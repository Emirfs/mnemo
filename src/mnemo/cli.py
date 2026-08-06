"""mnemo CLI.

F1: reindex / search / get
F2: recall (push, for the SessionStart hook) / write (with dedup)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .config import Config
from .context import build_context
from .index import Index
from .recall import build_recall
from .search import Search
from .vault import detect_project
from .writer import verify_note, write_note


def _csv(value: str) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _dest_from_url(url: str) -> str:
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name or "vault"


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

    sr = sub.add_parser("recall", help="build the session-start recall block")
    sr.add_argument("--project", help="override project (else detected)")
    sr.add_argument("--project-dir", help="dir to detect project from (default: cwd)")
    sr.add_argument("--hook", action="store_true", help="emit SessionStart JSON")
    sr.add_argument("--reindex", action="store_true", help="refresh index first")
    sx = sub.add_parser("context", help="build a compact query context pack")
    sx.add_argument("query")
    sx.add_argument("--project", help="override project (else detected)")
    sx.add_argument("--project-dir", help="dir to detect project from (default: cwd)")
    sx.add_argument("-k", type=int, default=5)
    sx.add_argument("--budget", type=int, default=2400)
    sx.add_argument("--json", action="store_true")
    sx.add_argument("--reindex", action="store_true", help="refresh index first")

    sb = sub.add_parser("bench", help="evaluate retrieval quality against a cases file")
    sb.add_argument("cases", help="path to .json/.jsonl: {query, project?, expected:[ids], k?}")
    sb.add_argument("-k", type=int, default=5)
    sb.add_argument("--json", action="store_true")
    sb.add_argument("--reindex", action="store_true", help="refresh index first")

    sw = sub.add_parser("write", help="add or update a note (deduped)")
    sw.add_argument("--type", required=True)
    sw.add_argument("--title", required=True)
    sw.add_argument("--summary", default="")
    sw.add_argument("--body", help="body text; '-' or omitted reads stdin")
    sw.add_argument("--project")
    sw.add_argument("--tags", default="", help="comma-separated")
    sw.add_argument("--links", default="", help="comma-separated ids")
    sw.add_argument(
        "--supersedes", default="",
        help="comma-separated ids this note replaces (they're hidden from recall)",
    )
    sw.add_argument("--id")
    sw.add_argument("--draft", action="store_true", help="store outside retrieval pending verification")
    sw.add_argument(
        "--verification",
        choices=("unknown", "reported", "inferred", "verified"),
        default="unknown",
    )
    sw.add_argument("--sources", default="", help="comma-separated evidence references")

    svf = sub.add_parser("verify", help="activate a draft with evidence")
    svf.add_argument("id")
    svf.add_argument("--sources", required=True, help="comma-separated evidence references")

    sd = sub.add_parser("daily", help="append an entry to today's daily note")
    sd.add_argument("text", nargs="?", help="entry text; omitted/'-' reads stdin")

    sv = sub.add_parser("serve", help="run the MCP server over stdio (cross-AI, pull)")
    sv.add_argument(
        "--project",
        help="scope MCP search, MOC, and writes to one project",
    )

    si = sub.add_parser("init", help="scaffold the vault as a git repo")
    si.add_argument("--remote", help="git remote URL (use a PRIVATE repo)")

    sy = sub.add_parser("sync", help="commit + pull --rebase + push the vault")
    sy.add_argument("--message", "-m")

    sc = sub.add_parser("clone", help="clone a vault on a new machine, then reindex")
    sc.add_argument("url")
    sc.add_argument("dest", nargs="?", help="destination dir (default: repo name)")

    se = sub.add_parser("export", help="zip the vault markdown (for Drive/transfer)")
    se.add_argument("out", help="output .zip path")

    sm = sub.add_parser("import", help="unzip an archive into the vault, then reindex")
    sm.add_argument("archive", help="input .zip path")

    spj = sub.add_parser(
        "project",
        help="show the detected project, or write a .mnemo-project marker",
    )
    spj.add_argument("name", nargs="?", help="set this project name in the current dir")
    spj.add_argument("--dir", default=".", help="directory (default: cwd)")
    return p


def _cmd_recall(args, cfg, idx) -> None:
    if args.reindex:
        idx.reindex(cfg.vault)
    project = args.project or detect_project(args.project_dir or os.getcwd())
    block = build_recall(idx, project)
    if args.hook:
        if block:
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "SessionStart",
                            "additionalContext": block,
                        }
                    },
                    ensure_ascii=False,
                )
            )
    else:
        print(block)


def _cmd_context(args, cfg, idx) -> None:
    if args.reindex:
        idx.reindex(cfg.vault)
    project = args.project or detect_project(args.project_dir or os.getcwd())
    pack = build_context(
        idx,
        args.query,
        project=project,
        k=args.k,
        budget=args.budget,
    )
    if args.json:
        print(json.dumps(pack, ensure_ascii=False, indent=2))
    else:
        print(pack["markdown"])


def _cmd_bench(args, cfg, idx) -> None:
    from .bench import evaluate, format_report, load_cases

    if args.reindex:
        idx.reindex(cfg.vault)
    report = evaluate(idx, load_cases(args.cases), k=args.k)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_report(report))


def _cmd_write(args, cfg, idx) -> None:
    body = args.body
    if body in (None, "-"):
        body = "" if sys.stdin.isatty() else sys.stdin.read()
    result = write_note(
        cfg,
        idx,
        type=args.type,
        title=args.title,
        summary=args.summary,
        body=body,
        project=args.project,
        tags=_csv(args.tags),
        links=_csv(args.links),
        supersedes=_csv(args.supersedes),
        status="draft" if args.draft else "active",
        verification=args.verification,
        sources=_csv(args.sources),
        id=args.id,
    )
    print(json.dumps(result, ensure_ascii=False))


def _force_utf8() -> None:
    # Hooks, piped note bodies, and non-ASCII (Turkish) text must not crash or
    # mojibake on Windows cp1252. stdin matters for `write`/`daily --body -`.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8()
    args = _build_parser().parse_args(argv)

    if args.cmd == "serve":
        from .server import run as serve
        serve(args.vault, project=args.project)
        return 0

    if args.cmd == "project":
        from .vault import MARKER, detect_project
        target = Path(args.dir)
        if args.name:
            (target / MARKER).write_text(args.name + "\n", encoding="utf-8")
            print(json.dumps({"marker": str(target / MARKER), "project": args.name}))
        else:
            print(json.dumps({"project": detect_project(target)}))
        return 0

    if args.cmd in ("init", "sync", "clone", "export", "import"):
        from . import portability as port
        cfg = Config(args.vault)
        if args.cmd == "init":
            if args.remote:
                print(
                    "WARNING: use a PRIVATE repo — your notes will be pushed there.",
                    file=sys.stderr,
                )
            print(json.dumps(port.init_vault(cfg.vault, args.remote)))
        elif args.cmd == "sync":
            print(json.dumps(port.sync_vault(cfg.vault, args.message)))
        elif args.cmd == "clone":
            dest = args.dest or _dest_from_url(args.url)
            print(json.dumps(port.clone_vault(args.url, dest)))
        elif args.cmd == "export":
            print(json.dumps(port.export_vault(cfg.vault, args.out)))
        elif args.cmd == "import":
            print(json.dumps(port.import_vault(args.archive, cfg.vault)))
        return 0

    cfg = Config(args.vault)
    # Semantic (embedding) index for search/reindex/write/context; FTS-only
    # fast path for recall/daily/get so SessionStart never loads the model.
    emb = None
    if args.cmd in ("reindex", "search", "write", "context", "bench"):
        from .embed import Embedder
        if Embedder.is_available():
            emb = Embedder()
    idx = Index(cfg.index_path, embedder=emb)
    try:
        if args.cmd == "reindex":
            print(json.dumps(idx.reindex(cfg.vault, full=args.full)))
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
                    print(
                        f"[{r['score']}] {r['title']}  "
                        f"({r['type']}/{proj}, {r['verification']})"
                    )
                    if r["summary"]:
                        print(f"    {r['summary']}")
                    print(f"    {r['path']}")
        elif args.cmd == "get":
            note = Search(idx).get(args.id)
            print(json.dumps(note, ensure_ascii=False, indent=2) if note else "not found")
        elif args.cmd == "recall":
            _cmd_recall(args, cfg, idx)
        elif args.cmd == "context":
            _cmd_context(args, cfg, idx)
        elif args.cmd == "bench":
            _cmd_bench(args, cfg, idx)
        elif args.cmd == "write":
            _cmd_write(args, cfg, idx)
        elif args.cmd == "verify":
            result = verify_note(cfg, idx, args.id, _csv(args.sources))
            print(json.dumps(result, ensure_ascii=False))
        elif args.cmd == "daily":
            from .daily import append_daily
            text = args.text
            if text in (None, "-"):
                text = "" if sys.stdin.isatty() else sys.stdin.read().strip()
            print(json.dumps(append_daily(cfg, idx, text), ensure_ascii=False))
    finally:
        idx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
