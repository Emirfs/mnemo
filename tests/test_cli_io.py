"""CLI I/O: a UTF-8 (Turkish) body piped via stdin must round-trip intact."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from mnemo.config import Config
from mnemo.index import Index
from mnemo.search import Search


def test_stdin_utf8_roundtrip(tmp_path: Path):
    body = "Türkçe içerik: şçğıöü — em dash ve € işareti."
    proc = subprocess.run(
        [
            sys.executable, "-c", "from mnemo.cli import main; main()",
            "--vault", str(tmp_path),
            "write", "--type", "note", "--title", "utf8 test", "--body", "-",
        ],
        input=body.encode("utf-8"),
        capture_output=True,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    result = json.loads(proc.stdout.decode("utf-8"))

    idx = Index(Config(tmp_path).index_path)
    note = Search(idx).get(result["id"])
    idx.close()
    assert note is not None
    assert "şçğıöü" in note["body"]
    assert "—" in note["body"]
    assert "€" in note["body"]
