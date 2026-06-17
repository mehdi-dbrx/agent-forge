"""SSE (Server-Sent Events) helpers for streaming subprocess output."""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import AsyncGenerator

from brickforge import PROJECT_ROOT, PACKAGE_ROOT, LOG_FILE


def sse_event(event_type: str, data: dict) -> str:
    """Format a single SSE event string."""
    return f"event:{event_type}\ndata:{json.dumps(data)}\n\n"


def sse_line(text: str, stream: str = "out") -> str:
    return sse_event("line", {"text": text, "stream": stream})


def sse_done(ok: bool, code: int = 0) -> str:
    return sse_event("done", {"ok": ok, "code": code})


def sse_result(data: dict) -> str:
    return sse_event("result", data)


class ExecLogger:
    """Logs exec output to session log + per-action log file."""

    def __init__(self, action: str):
        self.log_file = LOG_FILE
        self._lines: list[str] = []
        header = f"\n=== EXEC {action} {time.strftime('%Y-%m-%dT%H:%M:%S')}Z ===\n"
        self._lines.append(header)
        # Per-action log file
        self._action_log_dir = PROJECT_ROOT / "logs" / "exec"
        self._action_log_dir.mkdir(parents=True, exist_ok=True)
        self._action_file = open(self._action_log_dir / f"{action}-latest.log", "w", encoding="utf-8")
        self._action_file.write(header)

    def log(self, text: str) -> None:
        line = text if text.endswith("\n") else text + "\n"
        self._lines.append(line)
        if self._action_file and not self._action_file.closed:
            self._action_file.write(line)
            self._action_file.flush()

    def finish(self, ok: bool, code: int = 0) -> None:
        footer = f"=== {'OK' if ok else 'FAILED'} (exit {code}) ===\n"
        self._lines.append(footer)
        # Session log
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write("".join(self._lines))
        # Per-action log
        if self._action_file and not self._action_file.closed:
            self._action_file.write(footer)
            self._action_file.close()

    def __del__(self):
        if hasattr(self, '_action_file') and self._action_file and not self._action_file.closed:
            self._action_file.close()


async def stream_subprocess(
    cmd: list[str],
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
    timeout: float = 300,
    logger: ExecLogger | None = None,
    detect_result: bool = False,
) -> AsyncGenerator[str, None]:
    """Stream subprocess stdout/stderr as SSE events.

    If detect_result=True, lines starting with __RESULT__: are emitted as event:result.
    """
    cwd = str(cwd or PACKAGE_ROOT)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )

    # Drain stderr concurrently to prevent pipe deadlock.
    # Without this, reading stdout sequentially before stderr causes the
    # stderr buffer to fill (64KB), blocking the child process's stderr
    # writes, which blocks stdout, deadlocking the entire pipeline.
    stderr_lines: list[str] = []

    async def drain_stderr():
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace")
            if "VIRTUAL_ENV" in text and "does not match" in text:
                continue
            stderr_lines.append(text)

    stderr_task = asyncio.create_task(drain_stderr())

    # Stream stdout lines as SSE events
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace")
        if "VIRTUAL_ENV" in text and "does not match" in text:
            continue
        if logger:
            logger.log(text)
        if detect_result and text.startswith("__RESULT__:"):
            try:
                result_data = json.loads(text[len("__RESULT__:"):])
                yield sse_result(result_data)
            except json.JSONDecodeError:
                yield sse_line(text, "out")
        else:
            yield sse_line(text, "out")

    await stderr_task

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        yield sse_line("[x] Process timed out\n", "err")

    code = proc.returncode or 0

    if code != 0 and stderr_lines:
        from brickforge.lib.env_utils import parse_subprocess_error
        raw_stderr = "".join(stderr_lines)
        clean_msg = parse_subprocess_error(raw_stderr)
        yield sse_line(f"[x] {clean_msg}\n", "err")
    elif code != 0:
        yield sse_line("[x] Process failed\n", "err")

    yield sse_done(code == 0, code)


async def _collect(gen) -> list[str]:
    """Collect all items from an async generator."""
    items = []
    async for item in gen:
        items.append(item)
    return items
