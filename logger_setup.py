"""Structured logging for the S8 assignment runner.

Writes simultaneously to:
  - stdout (colourised, compact)
  - logs/run_<timestamp>.log (full structured output)

Every log record at WARNING+ includes the elapsed time since the process
started so performance sections can be verified from the log alone.
"""
from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

_START_TIME = time.time()
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)


class _ElapsedFormatter(logging.Formatter):
    """Adds +{elapsed:.1f}s to every record at WARNING and above."""

    COLOURS = {
        logging.DEBUG: "\033[90m",      # dark grey
        logging.INFO: "\033[0m",         # default
        logging.WARNING: "\033[33m",     # yellow
        logging.ERROR: "\033[31m",       # red
        logging.CRITICAL: "\033[41m",    # red bg
    }
    RESET = "\033[0m"

    def __init__(self, colour: bool = True):
        super().__init__()
        self._colour = colour

    def format(self, record: logging.LogRecord) -> str:
        elapsed = f"+{time.time() - _START_TIME:6.1f}s"
        level = record.levelname[:4]
        msg = record.getMessage()
        line = f"[{elapsed}] [{level}] {record.name}: {msg}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        if self._colour and sys.stderr.isatty():
            c = self.COLOURS.get(record.levelno, "")
            return f"{c}{line}{self.RESET}"
        return line


def setup(name: str = "s8", level: int = logging.DEBUG) -> logging.Logger:
    """Return a configured root logger.  Call once at startup."""
    import datetime

    log = logging.getLogger(name)
    if log.handlers:
        return log   # already set up (idempotent)
    log.setLevel(level)

    # Console handler (INFO+)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(_ElapsedFormatter(colour=True))
    log.addHandler(ch)

    # File handler (DEBUG+)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    fh = logging.FileHandler(LOGS_DIR / f"run_{ts}.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_ElapsedFormatter(colour=False))
    log.addHandler(fh)

    log.info("Logging started - output: logs/run_%s.log", ts)
    return log
