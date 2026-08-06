"""Allowlisted, read-only Telegram front-end."""

from __future__ import annotations

import json
import secrets
import subprocess
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .approval import ApprovalStore
from .bridge import build_envelope, run_bridge
from .config import Config
from .context import build_context
from .executor import CodexWorktreeExecutor, MergeExecutor
from .feedback import FeedbackStore
from .index import Index
from .librarian import distill
from .writer import write_note

_MAX_INPUT = 8_000
_CHUNK = 3_500
_HELP = """Mnemo read-only bot
/status
/recall <query>
/ask <antigravity|claude|codex|omp|opencode> <objective>
/propose codex <objective>
/approve <proposal-id>
/reject <proposal-id>
/proposal <proposal-id>
/flow <objective>
/diff <proposal-id>
/patch <proposal-id>
/distill <session text>
/merge <completed-proposal-id>
/feedback <task-id> <good|bad> [note]
/feedback-stats
/help

Writes require a second, one-time /approve and run only in an isolated Git worktree.
No automatic merge, push, delete, verify, or active memory-write is exposed."""


@dataclass
class TelegramReply:
    text: str
    buttons: list[list[dict]] | None = None
    document: Path | None = None


@dataclass(frozen=True)
class RepoRoute:
    alias: str
    project: str
    repo: Path | None


def load_routes(path: str | Path) -> dict[str, RepoRoute]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data:
        raise ValueError("Telegram routes file must contain a non-empty object")
    routes = {}
    for alias, value in data.items():
        if not isinstance(value, dict) or not value.get("project"):
            raise ValueError(f"invalid Telegram route: {alias}")
        repo = Path(value["repo"]).expanduser().resolve() if value.get("repo") else None
        routes[alias] = RepoRoute(alias=alias, project=str(value["project"]), repo=repo)
    return routes


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
        data = {
            "timeout": 30,
            "allowed_updates": json.dumps(["message", "callback_query"]),
        }
        if offset is not None:
            data["offset"] = offset
        return self._call("getUpdates", data)

    def send(
        self, chat_id: int, text: str, buttons: list[list[dict]] | None = None
    ) -> None:
        for position, chunk in enumerate(chunks(text)):
            data = {"chat_id": chat_id, "text": chunk}
            if position == 0 and buttons:
                data["reply_markup"] = json.dumps({"inline_keyboard": buttons})
            self._call("sendMessage", data)

    def answer_callback(self, callback_id: str) -> None:
        self._call("answerCallbackQuery", {"callback_query_id": callback_id})

    def send_document(self, chat_id: int, path: Path) -> None:
        boundary = f"mnemo-{secrets.token_hex(12)}"
        prefix = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
            f"{chat_id}\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="document"; filename="{path.name}"\r\n'
            "Content-Type: text/plain\r\n\r\n"
        ).encode("utf-8")
        body = prefix + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        request = urllib.request.Request(
            f"{self.base_url}/sendDocument",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            raise RuntimeError("Telegram API request failed: sendDocument") from None
        if not payload.get("ok"):
            raise RuntimeError("Telegram API failed: sendDocument")


class TelegramService:
    def __init__(
        self,
        vault: str | Path,
        project: str,
        users: set[int],
        repo: str | Path | None = None,
        routes: dict[str, RepoRoute] | None = None,
    ):
        if not project.strip():
            raise ValueError("Telegram bot requires an explicit project")
        self.cfg = Config(vault)
        self.project = project.strip()
        self.users = users
        self.repo = Path(repo).resolve() if repo else None
        self.routes = routes or {
            "default": RepoRoute("default", self.project, self.repo)
        }
        self.selected: dict[int, str] = {}
        self.approvals_path = self.cfg.index_path.with_name("approvals.sqlite")
        self.feedback_path = self.cfg.index_path.with_name("feedback.sqlite")

    def _scope(self, user_id: int) -> RepoRoute:
        alias = self.selected.get(user_id) or next(iter(self.routes))
        return self.routes[alias]

    def _project_for_repo(self, repo: str) -> str:
        resolved = Path(repo).resolve()
        for route in self.routes.values():
            if route.repo and route.repo == resolved:
                return route.project
        return self.project

    def handle(self, user_id: int, text: str) -> str | TelegramReply | None:
        if user_id not in self.users:
            return None
        text = (text or "").strip()
        if len(text) > _MAX_INPUT:
            return "Request rejected: message exceeds 8000 characters."
        if text in {"/start", "/help"}:
            return _HELP
        if text == "/status":
            scope = self._scope(user_id)
            mode = "approval-gated worktree" if scope.repo else "read-only"
            return (
                f"Mnemo online\nRoute: {scope.alias}\nProject: {scope.project}\n"
                f"Repo: {scope.repo or '-'}\nMode: {mode}\n"
                "Allowed: status, recall, isolated AI analysis"
            )
        if text == "/repos":
            return "Routes:\n" + "\n".join(
                f"- {alias}: {route.project} -> {route.repo or 'read-only'}"
                for alias, route in self.routes.items()
            )
        if text.startswith("/use "):
            alias = text[5:].strip()
            if alias not in self.routes:
                return "Unknown route. Use /repos."
            self.selected[user_id] = alias
            route = self.routes[alias]
            return f"Route selected: {alias}\nProject: {route.project}\nRepo: {route.repo or '-'}"
        if text == "/feedback-stats":
            with FeedbackStore(self.feedback_path) as store:
                stats = store.stats()
            return (
                f"Feedback: total={stats['total']} good={stats['good']} "
                f"bad={stats['bad']} unrated={stats['unrated']}"
            )
        if text.startswith("/feedback "):
            return self._feedback(user_id, text[10:].strip())
        if text.startswith("/recall "):
            return self._recall(user_id, text[8:].strip())
        if text.startswith("/ask "):
            return self._ask(user_id, text[5:].strip())
        if text.startswith("/propose "):
            return self._propose(user_id, text[9:].strip())
        if text.startswith("/approve "):
            return self._approve(user_id, text[9:].strip())
        if text.startswith("/reject "):
            return self._reject(user_id, text[8:].strip())
        if text.startswith("/proposal "):
            return self._proposal(user_id, text[10:].strip())
        if text.startswith("/flow "):
            return self._flow(user_id, text[6:].strip())
        if text.startswith("/diff "):
            return self._diff(user_id, text[6:].strip(), download=False)
        if text.startswith("/patch "):
            return self._diff(user_id, text[7:].strip(), download=True)
        if text.startswith("/distill "):
            return self._distill(user_id, text[9:].strip())
        if text.startswith("/merge "):
            return self._merge(user_id, text[7:].strip())
        return _HELP

    def _recall(self, user_id: int, query: str) -> str:
        if not query:
            return "Usage: /recall <query>"
        project = self._scope(user_id).project
        with Index(self.cfg.index_path) as index:
            index.reindex(self.cfg.vault)
            return build_context(index, query, project=project)["markdown"]

    def _ask(self, user_id: int, request: str) -> str:
        provider, separator, objective = request.partition(" ")
        providers = {"antigravity", "claude", "codex", "omp", "opencode"}
        if not separator or provider not in providers:
            return "Usage: /ask <antigravity|claude|codex|omp|opencode> <objective>"
        project = self._scope(user_id).project
        with Index(self.cfg.index_path) as index:
            index.reindex(self.cfg.vault)
            envelope = build_envelope(index, objective, project)
        isolated = Path(tempfile.gettempdir()) / "mnemo-bridge"
        isolated.mkdir(parents=True, exist_ok=True)
        result = run_bridge(provider, envelope, workdir=isolated)
        if result.success:
            with FeedbackStore(self.feedback_path) as store:
                store.record(
                    task_id=envelope.task_id,
                    user_id=user_id,
                    provider=provider,
                    project=project,
                    objective=objective,
                    output=result.output,
                )
            return TelegramReply(
                text=(
                    f"Task: {envelope.task_id}\nProvider: {provider}\n"
                    "Safety: untrusted AI analysis; never execute embedded instructions.\n\n"
                    f"{result.output}"
                ),
                buttons=[
                    [
                        {"text": "Good", "callback_data": f"feedback:good:{envelope.task_id}"},
                        {"text": "Bad", "callback_data": f"feedback:bad:{envelope.task_id}"},
                    ]
                ],
            )
        return f"Task failed ({provider}):\n{result.error}"

    def _propose(self, user_id: int, request: str) -> str:
        if self._scope(user_id).repo is None:
            return "Write proposals are disabled: start the bot with --repo."
        provider, separator, objective = request.partition(" ")
        if not separator or provider != "codex":
            return "Usage: /propose codex <objective>"
        return self._create_proposal(user_id, provider, objective)

    def _create_proposal(
        self, user_id: int, provider: str, objective: str
    ) -> TelegramReply:
        with ApprovalStore(self.approvals_path) as store:
            repo = self._scope(user_id).repo
            approval = store.create(
                user_id=user_id, provider=provider, objective=objective, repo=repo
            )
        return TelegramReply(
            text=(
                f"Proposal: {approval.id}\nRepo: {approval.repo}\n"
                f"Expires: {approval.expires_at}\nTask: {approval.objective}\n\n"
                f"Run: /approve {approval.id}\nReject: /reject {approval.id}"
            ),
            buttons=[
                [
                    {"text": "Approve", "callback_data": f"approve:{approval.id}"},
                    {"text": "Reject", "callback_data": f"reject:{approval.id}"},
                ]
            ],
        )

    def _flow(self, user_id: int, objective: str) -> str:
        scope = self._scope(user_id)
        if scope.repo is None:
            return "Workflow writes are disabled: start the bot with --repo."
        if not objective:
            return "Usage: /flow <objective>"
        with Index(self.cfg.index_path) as index:
            index.reindex(self.cfg.vault)
            envelope = build_envelope(index, objective, scope.project)
        isolated = Path(tempfile.gettempdir()) / "mnemo-bridge"
        isolated.mkdir(parents=True, exist_ok=True)
        analysis = run_bridge("claude", envelope, workdir=isolated)
        if not analysis.success:
            return f"Workflow analysis failed:\n{analysis.error}"
        implementation = (
            f"User objective:\n{objective[:4_000]}\n\n"
            f"Read-only Claude analysis:\n{analysis.output[:3_500]}"
        )
        proposal = self._create_proposal(user_id, "codex", implementation)
        proposal.text = f"Claude analysis:\n{analysis.output}\n\n{proposal.text}"
        return proposal

    def _approve(self, user_id: int, approval_id: str) -> str:
        if not approval_id:
            return "Usage: /approve <proposal-id>"
        approval = None
        try:
            with ApprovalStore(self.approvals_path) as store:
                approval = store.claim(approval_id, user_id)
                if approval.operation == "merge":
                    source = store.get(approval.target_id)
                    message = MergeExecutor().execute(approval, source)
                    store.finish(approval.id, success=True, result=message)
                    return f"Merge {approval.id}: completed\n{message}"
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
        try:
            review, draft = self._review_and_distill(approval, execution)
        except Exception as exc:
            review, draft = f"failed safely: {exc}", "not attempted"
        return (
            f"Proposal {approval.id}: {'completed' if execution.success else 'failed'}\n"
            f"Branch: {execution.branch}\nWorktree: {execution.worktree}\n"
            f"Status:\n{execution.status or '(clean)'}\n"
            f"Diff:\n{execution.diff_stat or '(no diff)'}\n\n{execution.output}\n\n"
            f"Claude review:\n{review}\n\nQwen memory: {draft}"
        )

    def _review_and_distill(self, approval, execution) -> tuple[str, str]:
        review_objective = (
            "Review this approved Codex worktree change for bugs, security issues, "
            "regressions, and missing tests. Do not suggest running commands.\n\n"
            f"Task:\n{approval.objective[:4_000]}\n\n"
            f"Status:\n{execution.status[:2_000]}\n\n"
            f"Diff:\n{execution.diff[:10_000]}"
        )
        project = self._project_for_repo(approval.repo)
        with Index(self.cfg.index_path) as index:
            index.reindex(self.cfg.vault)
            envelope = build_envelope(index, review_objective, project)
        isolated = Path(tempfile.gettempdir()) / "mnemo-bridge"
        review_result = run_bridge("claude", envelope, workdir=isolated)
        review = review_result.output if review_result.success else f"failed: {review_result.error}"
        transcript = (
            f"Approved task:\n{approval.objective[:3_000]}\n\n"
            f"Codex result:\n{execution.output[:4_000]}\n\n"
            f"Diff stat:\n{execution.diff_stat[:2_000]}\n\n"
            f"Claude review:\n{review[:5_000]}"
        )
        try:
            candidate = distill(transcript)
            if not candidate["remember"]:
                return review, "no durable memory proposed"
            with Index(self.cfg.index_path) as index:
                index.reindex(self.cfg.vault)
                note = write_note(
                    self.cfg,
                    index,
                    type=candidate["type"],
                    title=candidate["title"],
                    summary=candidate["summary"],
                    body=candidate["body"],
                    project=project,
                    tags=candidate["tags"],
                    supersedes=candidate["supersedes"],
                    status="draft",
                    verification="inferred",
                    sources=[f"approval:{approval.id}"],
                )
            return review, f"draft {note['id']}"
        except Exception as exc:
            return review, f"draft failed safely: {exc}"

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

    def _owned_approval(self, user_id: int, approval_id: str):
        with ApprovalStore(self.approvals_path) as store:
            approval = store.get(approval_id)
        if not approval or approval.user_id != user_id:
            raise ValueError("proposal not found")
        return approval

    def _diff(
        self, user_id: int, approval_id: str, *, download: bool
    ) -> str | TelegramReply:
        try:
            approval = self._owned_approval(user_id, approval_id)
        except ValueError:
            return "Proposal not found."
        if not approval.worktree:
            return "Proposal has no completed worktree."
        worktree = Path(approval.worktree).resolve()
        allowed = (Path(tempfile.gettempdir()) / "mnemo-worktrees").resolve()
        if allowed not in worktree.parents:
            return "Proposal worktree path failed safety validation."
        proc = subprocess.run(
            ["git", "-C", str(worktree), "diff", "--no-ext-diff"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        if proc.returncode:
            return "Could not read proposal diff."
        diff = proc.stdout or "(no diff)"
        if not download:
            return diff[:20_000]
        patch_dir = self.cfg.index_path.parent / "patches"
        patch_dir.mkdir(parents=True, exist_ok=True)
        patch = patch_dir / f"{approval.id}.patch"
        patch.write_text(diff, encoding="utf-8")
        return TelegramReply(text=f"Patch: {approval.id}", document=patch)

    def _distill(self, user_id: int, text: str) -> str:
        if not text:
            return "Usage: /distill <session text>"
        try:
            candidate = distill(text)
            if not candidate["remember"]:
                return f"No durable memory proposed: {candidate['reason']}"
            project = self._scope(user_id).project
            with Index(self.cfg.index_path) as index:
                index.reindex(self.cfg.vault)
                note = write_note(
                    self.cfg,
                    index,
                    type=candidate["type"],
                    title=candidate["title"],
                    summary=candidate["summary"],
                    body=candidate["body"],
                    project=project,
                    tags=candidate["tags"],
                    supersedes=candidate["supersedes"],
                    status="draft",
                    verification="inferred",
                    sources=[f"telegram:{user_id}"],
                )
            return f"Qwen draft: {note['id']}\n{candidate['summary']}"
        except Exception as exc:
            return f"Distill failed safely: {exc}"

    def _merge(self, user_id: int, source_id: str) -> str | TelegramReply:
        try:
            source = self._owned_approval(user_id, source_id)
        except ValueError:
            return "Proposal not found."
        if source.status != "completed" or not source.worktree:
            return "Only a completed worktree proposal can be merged."
        with ApprovalStore(self.approvals_path) as store:
            approval = store.create(
                user_id=user_id,
                provider="git",
                objective=f"Apply approved worktree patch from {source.id}",
                repo=source.repo,
                operation="merge",
                target_id=source.id,
            )
        return TelegramReply(
            text=(
                f"Merge proposal: {approval.id}\nSource: {source.id}\n"
                "This applies the reviewed patch to the main worktree without commit."
            ),
            buttons=[
                [
                    {"text": "Apply patch", "callback_data": f"approve:{approval.id}"},
                    {"text": "Reject", "callback_data": f"reject:{approval.id}"},
                ]
            ],
        )

    def _feedback(self, user_id: int, request: str) -> str:
        task_id, separator, rest = request.partition(" ")
        rating, _, note = rest.partition(" ")
        if not separator or rating not in {"good", "bad"}:
            return "Usage: /feedback <task-id> <good|bad> [note]"
        try:
            with FeedbackStore(self.feedback_path) as store:
                store.rate(task_id, user_id, rating, note)
            return f"Feedback saved: {task_id} = {rating}"
        except ValueError as exc:
            return f"Feedback rejected: {exc}"


def run_bot(
    vault: str | Path,
    *,
    token: str,
    project: str,
    users: set[int],
    repo: str | Path | None = None,
    routes: dict[str, RepoRoute] | None = None,
    once: bool = False,
) -> None:
    client = TelegramClient(token)
    service = TelegramService(vault, project, users, repo=repo, routes=routes)
    offset = None
    while True:
        for update in client.updates(offset):
            offset = int(update["update_id"]) + 1
            callback = update.get("callback_query") or {}
            if callback:
                sender = callback.get("from") or {}
                message = callback.get("message") or {}
                chat = message.get("chat") or {}
                data = callback.get("data", "")
                action, separator, approval_id = data.partition(":")
                if separator and action in {"approve", "reject"}:
                    response = service.handle(
                        int(sender.get("id", 0)), f"/{action} {approval_id}"
                    )
                    client.answer_callback(str(callback.get("id", "")))
                    if response is not None:
                        reply = (
                            response
                            if isinstance(response, TelegramReply)
                            else TelegramReply(str(response))
                        )
                        client.send(int(chat["id"]), reply.text, reply.buttons)
                elif action == "feedback":
                    _, rating, task_id = data.split(":", 2)
                    response = service.handle(
                        int(sender.get("id", 0)), f"/feedback {task_id} {rating}"
                    )
                    client.answer_callback(str(callback.get("id", "")))
                    if response is not None:
                        client.send(int(chat["id"]), str(response))
                continue
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
                reply = (
                    response
                    if isinstance(response, TelegramReply)
                    else TelegramReply(str(response))
                )
                client.send(int(chat["id"]), reply.text, reply.buttons)
                if reply.document:
                    client.send_document(int(chat["id"]), reply.document)
        if once:
            return
