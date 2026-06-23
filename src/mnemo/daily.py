"""Daily journal — append timestamped entries to today's daily note."""

from __future__ import annotations

import datetime as _dt

import frontmatter


def append_daily(cfg, index, text: str) -> dict:
    today = _dt.date.today().isoformat()
    path = cfg.vault / "daily" / f"{today}.md"

    if path.exists():
        post = frontmatter.load(str(path))
        meta = post.metadata
        body = post.content
    else:
        meta = {"id": today, "type": "daily", "title": today, "created": today}
        body = ""

    stamp = _dt.datetime.now().strftime("%H:%M")
    body = f"{body.rstrip()}\n- {stamp} {text}".strip()
    meta["updated"] = today

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(frontmatter.dumps(frontmatter.Post(body, **meta)), encoding="utf-8")
    index.reindex(cfg.vault)
    return {"path": str(path.relative_to(cfg.vault)), "entry": text}
