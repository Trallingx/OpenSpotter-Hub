"""
Logger Service
Centralized logging for the application.
"""

import logging
from pathlib import Path


class LineLimitedFileHandler(logging.FileHandler):
    """File handler that keeps only the newest log lines in one file."""

    def __init__(self, filename, max_lines: int = 1000, trim_check_interval: int = 1):
        super().__init__(filename, mode="a+", encoding="utf-8")
        self.max_lines = max(1, int(max_lines))
        self.trim_check_interval = max(1, int(trim_check_interval))
        self._records_since_trim_check = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            super().emit(record)
        except OSError:
            self.handleError(record)
            return

        self._records_since_trim_check += 1
        if self._records_since_trim_check < self.trim_check_interval:
            return

        self._records_since_trim_check = 0
        try:
            self._trim_to_line_limit()
        except OSError:
            # Windows/OneDrive can briefly lock the file. Logging must never crash
            # motion progress handling, so leave the file untrimmed for this pass.
            try:
                if self.stream:
                    self.stream.seek(0, 2)
            except OSError:
                pass

    def _trim_to_line_limit(self) -> None:
        if not self.stream:
            return

        self.flush()
        self.stream.seek(0)
        lines = self.stream.readlines()
        if len(lines) <= self.max_lines:
            self.stream.seek(0, 2)
            return

        self.stream.seek(0)
        self.stream.truncate()
        self.stream.writelines(lines[-self.max_lines :])
        self.flush()
        self.stream.seek(0, 2)


class LoggerService:
    """
    Centralized logging service.
    Provides logging to console and a line-limited file handler.
    """

    def __init__(self, name: str = "dod_system", level: int = logging.INFO):
        """
        Initialize logger service.

        Args:
            name: Logger name
            level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False

        # Create logs directory if it doesn't exist
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)

        # File handler trimmed in batches toward the newest 1000 physical lines.
        log_file = log_dir / "dod_system.log"
        file_handler = LineLimitedFileHandler(log_file, max_lines=1000, trim_check_interval=100)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)

        # Add handlers once
        if not self.logger.handlers:
            self.logger.addHandler(console_handler)
            self.logger.addHandler(file_handler)

    def debug(self, message: str) -> None:
        """Log debug message."""
        self.logger.debug(message)

    def info(self, message: str) -> None:
        """Log info message."""
        self.logger.info(message)

    def warning(self, message: str) -> None:
        """Log warning message."""
        self.logger.warning(message)

    def error(self, message: str) -> None:
        """Log error message."""
        self.logger.error(message)

    def critical(self, message: str) -> None:
        """Log critical message."""
        self.logger.critical(message)

    def __repr__(self):
        return f"LoggerService(logger={self.logger.name})"
