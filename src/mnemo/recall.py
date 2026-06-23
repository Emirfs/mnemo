"""Build the session-start recall block (the PUSH side of memory).

Produces a compact, token-disciplined markdown block: the project's map (MOC)
plus recent decisions and lessons — summaries only, each with an id the model
can expand via ``mnemo get <id>``.
"""

from __future__ import annotations

_MOC_BODY_LIMIT = 1500


def _recent(con, type_: str, project: str | None, limit: int):
    q = "SELECT id, title, summary FROM notes WHERE type = ?"
    params: list = [type_]
    if project:
        q += " AND (project = ? OR project IS NULL)"
        params.append(project)
    q += " ORDER BY COALESCE(updated, created, '') DESC, id DESC LIMIT ?"
    params.append(limit)
    return con.execute(q, params).fetchall()


def _moc(con, project: str | None):
    if not project:
        return None
    return con.execute(
        "SELECT id, title, summary, body FROM notes "
        "WHERE type = 'project' AND project = ? LIMIT 1",
        (project,),
    ).fetchone()


def build_recall(index, project: str | None, max_items: int = 8) -> str:
    con = index.con
    moc = _moc(con, project)
    decisions = _recent(con, "decision", project, max_items)
    lessons = _recent(con, "lesson", project, max_items)

    if not (moc or decisions or lessons):
        return ""

    out: list[str] = [
        f"## 🧠 mnemo recall — project: {project or '(unknown)'}",
        "Past context for this project. Expand any item with `mnemo get <id>`.",
    ]

    if moc:
        out.append(f"\n### Map: {moc['title']}")
        if moc["summary"]:
            out.append(moc["summary"])
        if moc["body"]:
            body = moc["body"].strip()
            if len(body) > _MOC_BODY_LIMIT:
                body = body[:_MOC_BODY_LIMIT].rstrip() + " …"
            out.append(body)

    if decisions:
        out.append("\n### Recent decisions")
        out.extend(f"- [{r['id']}] {r['title']} — {r['summary']}" for r in decisions)

    if lessons:
        out.append("\n### Lessons / past mistakes")
        out.extend(f"- [{r['id']}] {r['title']} — {r['summary']}" for r in lessons)

    out.append(
        "\n> When you make a notable decision or hit a lesson this session, "
        "record it with `memory_write` (MCP) or `mnemo write` so future "
        "sessions inherit it."
    )
    return "\n".join(out).strip()
