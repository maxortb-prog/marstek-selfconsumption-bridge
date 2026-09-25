"""Logging-Setup mit konfigurierbaren Levels und ANSI-Farben.

Die Farben werden bewusst immer ausgegeben (Anforderung), auch wenn stdout
kein TTY ist - das HA Add-on Log rendert ANSI-Sequenzen korrekt.
"""

from __future__ import annotations

import logging
import sys

# Eigenes, sehr feines Level fuer Rohdaten auf der Leitung.
TRACE_LEVEL = 5
logging.addLevelName(TRACE_LEVEL, "TRACE")


def _trace(self: logging.Logger, message: str, *args, **kwargs) -> None:
    if self.isEnabledFor(TRACE_LEVEL):
        self._log(TRACE_LEVEL, message, args, **kwargs)


logging.Logger.trace = _trace  # type: ignore[attr-defined]

LEVELS: dict[str, int] = {
    "trace": TRACE_LEVEL,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

# Farbe je Level
LEVEL_COLORS: dict[int, str] = {
    TRACE_LEVEL: "\033[38;5;245m",   # grau
    logging.DEBUG: "\033[36m",       # cyan
    logging.INFO: "\033[32m",        # gruen
    logging.WARNING: "\033[33m",     # gelb
    logging.ERROR: "\033[31m",       # rot
    logging.CRITICAL: "\033[97;41m", # weiss auf rot
}

TIME_COLOR = "\033[38;5;246m"
NAME_COLOR = "\033[38;5;110m"


class AnsiFormatter(logging.Formatter):
    """Faerbt die Logzeile nach Level.

    ``full_line=True`` faerbt die komplette Zeile inklusive Zeitstempel und
    Logger-Name in der Levelfarbe. ``full_line=False`` faerbt nur Zeitstempel,
    Level und Namen als Akzente und laesst den Text neutral.
    """

    def __init__(self, full_line: bool = True) -> None:
        super().__init__()
        self.full_line = full_line

    def format(self, record: logging.LogRecord) -> str:
        color = LEVEL_COLORS.get(record.levelno, "")
        ts = self.formatTime(record, "%Y-%m-%d %H:%M:%S")
        msg = record.getMessage()

        if self.full_line:
            # Eingebettete Farbsequenzen (z. B. fett hervorgehobene Namen)
            # beenden mit RESET - danach die Levelfarbe wieder aufnehmen,
            # damit der Rest der Zeile nicht farblos wird.
            msg = msg.replace(RESET, RESET + color)
            body = (
                f"{ts} {BOLD}{record.levelname:<8}{RESET}{color} "
                f"{record.name:<22} {msg}"
            )
            if record.exc_info:
                body += "\n" + self.formatException(record.exc_info).replace(
                    RESET, RESET + color
                )
            return f"{color}{body}{RESET}"

        level = f"{color}{BOLD}{record.levelname:<8}{RESET}"
        name = f"{NAME_COLOR}{record.name:<22}{RESET}"
        if record.levelno >= logging.WARNING:
            msg = f"{color}{msg}{RESET}"
        elif record.levelno <= TRACE_LEVEL:
            msg = f"{DIM}{msg}{RESET}"
        line = f"{TIME_COLOR}{ts}{RESET} {level} {name} {msg}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def setup_logging(level_name: str, full_line_color: bool = True) -> logging.Logger:
    """Root-Logger konfigurieren und den Bridge-Logger zurueckgeben."""
    level = LEVELS.get(str(level_name).lower(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(AnsiFormatter(full_line=full_line_color))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # paho ist auf DEBUG extrem gespraechig -> nur bei TRACE durchlassen
    logging.getLogger("paho").setLevel(
        TRACE_LEVEL if level <= TRACE_LEVEL else logging.WARNING
    )
    return logging.getLogger("marstek")


def colorize(text: str, color: str) -> str:
    return f"{color}{text}{RESET}"
