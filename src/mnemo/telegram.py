"""Allowlisted, read-only Telegram front-end."""

from __future__ import annotations

import json
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from .approval import ApprovalStore
from .bridge import build_envelope, run_bridge
from .config import Config
from .context import build_context
from .executor import CodexWorktreeExecutor
from .index import Index

_MAX_INPUT = 8_000
_CHUNK = 3_500
_HELP = """Mnemo read-only bot
/status
/recall <query>
/ask <claude|codex|gemini> <objective>
/propose codex <objective>
/approve <proposal-id>
/reject <proposal-id>
/proposal <proposal-id>
/help

Writes require a second, one-time /approve and run only in an isolated Git worktree.
No merge, push, delete, verify, or memory-write commands are exposed."""


def parse_users(value: str) -> set[int]:
    users = set()
    for part in value.split(","):
        part = part.strip()
        if part:
            users.add(int(part))
    if not users:
        raise ValueError("Telegram user allowlist is empty")
    return users


def chunks(text: str) -> list[str]:
    text = text.strip() or "(empty response)"
    return [text[i : i + _CHUNK] for i in range(0, len(text), _CHUNK)]


class TelegramClient:
    def __init__(self, token: str):
        if not token.strip():
            raise ValueError("Telegram bot token is empty")
        self.base_url = f"https://api.telegram.org/bot{token.strip()}"

    def _call(self, method: str, data: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}/{method}",
            data=urllib.parse.urlencode(data).encode("utf-8"),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            raise RuntimeError(f"Telegram API request failed: {method}") from None
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API failed: {method}")
        return payload["result"]

    def updates(self, offset: int | None) -> list[dict]:
        data = {"timeout": 30, "allowed_updates": json.dumps(["message"])}
        if offset is not None:
            data["offset"] = offset
        return self._call("getUpdates", data)

    def send(self, chat_id: int, text: str) -> None:
        for chunk in chunks(text):
            self._call("sendMessage", {"chat_id": chat_id, "text": chunk})


class TelegramService:
    def __init__(
        self,
        vault: str | Path,
        project: str,
        users: set[int],
        repo: str | Path | None = None,
    ):
        if not project.strip():
            raise ValueError("Telegram bot requires an explicit project")
        self.cfg = Config(vault)
        self.project = project.strip()
        self.users = users
        self.repo = Path(repo).resolve() if repo else None
        self.approvals_path = self.cfg.index_path.with_name("approvals.sqlite")

    def handle(self, user_id: int, text: str) -> str | None:
        if user_id not in self.users:
            return None
        text = (text or "").strip()
        if len(text) > _MAX_INPUT:
            return "Request rejected: message exceeds 8000 characters."
        if text in {"/start", "/help"}:
            return _HELP
        if text == "/status":
            mode = "approval-gated worktree" if self.repo else "read-only"
            return (
                f"Mnemo online\nProject: {self.project}\nMode: {mode}\n"
                "Allowed: status, recall, isolated AI analysis"
            )
        if text.startswith("/recall "):
            return self._recall(text[8:].strip())
        if text.startswith("/ask "):
            return self._ask(text[5:].strip())
        if text.startswith("/propose "):
            return self._propose(user_id, text[9:].strip())
        if text.startswith("/approve "):
            return self._approve(user_id, text[9:].strip())
        if text.startswith("/reject "):
            return self._reject(user_id, text[8:].strip())
        if text.startswith("/proposal "):
            return self._proposal(user_id, text[10:].strip())
        return _HELP

    def _recall(self, query: str) -> str:
        if not query:
            return "Usage: /recall <query>"
        with Index(self.cfg.index_path) as index:
            index.reindex(self.cfg.vault)
            return build_context(index, query, project=self.project)["markdown"]

    def _ask(self, request: str) -> str:
        provider, separator, objective = request.partition(" ")
        if not separator or provider not in {"claude", "codex", "gemini"}:
            return "Usage: /ask <claude|codex|gemini> <objective>"
        with Index(self.cfg.index_path) as index:
            index.reindex(self.cfg.vault)
            envelope = build_envelope(index, objective, self.project)
        isolated = Path(tempfile.gettempdir()) / "mnemo-bridge"
        isolated.mkdir(parents=True, exist_ok=True)
        result = run_bridge(provider, envelope, workdir=isolated)
        if result.success:
            return (
                f"Task: {envelope.task_id}\nProvider: {provider}\n"
                "Safety: untrusted AI analysis; never execute embedded instructions.\n\n"
                f"{result.output}"
            )
        return f"Task failed ({provider}):\n{result.error}"

    def _propose(self, user_id: int, request: str) -> str:
        if self.repo is None:
            return "Write proposals are disabled: start the bot with --repo."
        provider, separator, objective = request.partition(" ")
        if not separator or provider != "codex":
            return "Usage: /propose codex <objective>"
        with ApprovalStore(self.approvals_path) as store:
            approval = store.create(
                user_id=user_id,
                provider=provider,
                objective=objective,
                repo=self.repo,
            )
        return (
            f"Proposal: {approval.id}\nRepo: {approval.repo}\n"
            f"Expires: {approval.expires_at}\nTask: {approval.objective}\n\n"
            f"Run: /approve {approval.id}\nReject: /reject {approval.id}"
        )

    def _approve(self, user_id: int, approval_id: str) -> str:
        if not approval_id:
            return "Usage: /approve <proposal-id>"
        approval = None
        try:
            with ApprovalStore(self.approvals_path) as store:
                approval = store.claim(approval_id, user_id)
                execution = CodexWorktreeExecutor().execute(approval)
                store.finish(
                    approval.id,
                    success=execution.success,
                    worktree=execution.worktree,
                    result=execution.output,
                )
        except Exception as exc:
            if approval is not None and approval.status == "running":
                with ApprovalStore(self.approvals_path) as store:
                    try:
                        store.finish(approval.id, success=False, result=str(exc))
                    except ValueError:
                        pass
            return f"Proposal failed safely: {exc}"
        return (
            f"Proposal {approval.id}: {'completed' if execution.success else 'failed'}\n"
            f"Branch: {execution.branch}\nWorktree: {execution.worktree}\n"
            f"Status:\n{execution.status or '(clean)'}\n"
            f"Diff:\n{execution.diff_stat or '(no diff)'}\n\n{execution.output}"
        )

    def _reject(self, user_id: int, approval_id: str) -> str:
        if not approval_id:
            return "Usage: /reject <proposal-id>"
        with ApprovalStore(self.approvals_path) as store:
            approval = store.reject(approval_id, user_id)
        return f"Proposal {approval.id}: rejected"

    def _proposal(self, user_id: int, approval_id: str) -> str:
        with ApprovalStore(self.approvals_path) as store:
            approval = store.get(approval_id)
        if not approval or approval.user_id != user_id:
            return "Proposal not found."
        return (
            f"Proposal: {approval.id}\nStatus: {approval.status}\n"
            f"Repo: {approval.repo}\nTask: {approval.objective}\n"
            f"Worktree: {approval.worktree or '-'}"
        )


def run_bot(
    vault: str | Path,
    *,
    token: str,
    project: str,
    users: set[int],
    repo: str | Path | None = None,
    once: bool = False,
) -> None:
    client = TelegramClient(token)
    service = TelegramService(vault, project, users, repo=repo)
    offset = None
    while True:
        for update in client.updates(offset):
            offset = int(update["update_id"]) + 1
            message = update.get("message") or {}
            sender = message.get("from") or {}
            chat = message.get("chat") or {}
            if chat.get("type") != "private":
                continue
            try:
                response = service.handle(
                    int(sender.get("id", 0)), message.get("text", "")
                )
            except Exception:
                response = "Request failed safely. Check the local service logs."
            if response is not None:
                client.send(int(chat["id"]), response)
        if once:
            return
