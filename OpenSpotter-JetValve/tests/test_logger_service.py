import logging

from services.logger_service import LineLimitedFileHandler


def test_line_limited_file_handler_keeps_newest_1000_lines(tmp_path):
    log_file = tmp_path / "dod_system.log"
    logger = logging.getLogger("test_line_limited_file_handler")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    handler = LineLimitedFileHandler(log_file, max_lines=1000)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    try:
        for index in range(1005):
            logger.info(f"line {index}")
    finally:
        handler.close()
        logger.handlers.clear()

    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1000
    assert lines[0] == "line 5"
    assert lines[-1] == "line 1004"


def test_line_limited_file_handler_trim_failure_does_not_raise(tmp_path):
    log_file = tmp_path / "dod_system.log"
    logger = logging.getLogger("test_line_limited_file_handler_trim_failure")
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    handler = LineLimitedFileHandler(log_file, max_lines=1)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler._trim_to_line_limit = lambda: (_ for _ in ()).throw(PermissionError("locked"))
    logger.addHandler(handler)

    try:
        logger.info("line 1")
        logger.info("line 2")
    finally:
        handler.close()
        logger.handlers.clear()

    assert "line 2" in log_file.read_text(encoding="utf-8")
