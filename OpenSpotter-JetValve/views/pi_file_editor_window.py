"""
Pi File Editor Window
Moonraker-backed editor for Klipper config files and project Pi-side scripts.
"""

from __future__ import annotations

import logging
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
KLIPPER_CONFIG_DIR = PROJECT_ROOT / "docs" / "klipper_configs"
SCRIPT_DIR = PROJECT_ROOT / "scripts"
PROJECT_SCRIPT_NAMES = (
    "arduino_valve_fire.py",
    "arduino_valve_bridge.py",
)


class _WorkerSignals(QObject):
    finished = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)


def _normalize_text(text: str) -> str:
    """Normalize newline style before comparing or uploading Pi text files."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _local_pi_file_map() -> list[dict[str, Any]]:
    """Return local files that intentionally mirror files in the Pi config root."""
    files: list[dict[str, Any]] = []

    if KLIPPER_CONFIG_DIR.exists():
        for path in sorted(KLIPPER_CONFIG_DIR.iterdir()):
            if path.is_file() and path.suffix.lower() in {".cfg", ".conf", ".md"}:
                files.append(
                    {
                        "local_path": path,
                        "root": "config",
                        "remote_path": path.name,
                    }
                )

    for script_name in PROJECT_SCRIPT_NAMES:
        path = SCRIPT_DIR / script_name
        if path.exists():
            files.append(
                {
                    "local_path": path,
                    "root": "config",
                    "remote_path": f"scripts/{script_name}",
                }
            )

    return files


def _local_path_for_pi_file(root: str, remote_path: str) -> Path | None:
    """Map a Moonraker config-root file to its local project copy."""
    if root != "config":
        return None

    target = PurePosixPath(remote_path.strip("/"))
    parts = target.parts
    if len(parts) == 1 and target.suffix.lower() in {".cfg", ".conf", ".md"}:
        return KLIPPER_CONFIG_DIR / target.name

    if (
        len(parts) == 2
        and parts[0] == "scripts"
        and target.name in PROJECT_SCRIPT_NAMES
    ):
        return SCRIPT_DIR / target.name

    return None


def collect_local_pi_file_differences(
    klipper_service,
    logger: logging.Logger | None = None,
) -> list[dict[str, Any]]:
    """Compare known local Pi-target files against Moonraker config files."""
    logger = logger or logging.getLogger("dod_system")
    differences: list[dict[str, Any]] = []
    local_files = _local_pi_file_map()
    logger.info(f"Pi file sync comparing {len(local_files)} local Pi-target file(s)")

    for entry in local_files:
        local_path = entry["local_path"]
        logger.debug(f"Pi file sync reading local file {local_path}")
        try:
            local_text = _normalize_text(local_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error(f"Pi file sync local read failed for {local_path}: {exc}")
            differences.append(
                {
                    **entry,
                    "reason": f"local read failed: {exc}",
                    "uploadable": False,
                }
            )
            continue

        logger.debug(f"Pi file sync downloading remote file {entry['root']}/{entry['remote_path']}")
        remote = klipper_service.download_file(entry["root"], entry["remote_path"])
        remote_error = remote.get("error") if isinstance(remote, dict) else None
        if remote_error:
            missing = str(remote_error).startswith("HTTP 404")
            logger.warning(
                f"Pi file sync remote compare failed for {entry['root']}/{entry['remote_path']}: {remote_error}"
            )
            differences.append(
                {
                    **entry,
                    "reason": "missing on Pi" if missing else f"Pi read failed: {remote_error}",
                    "uploadable": missing,
                }
            )
            continue

        remote_text = _normalize_text(str(remote.get("content", "")))
        if local_text != remote_text:
            logger.info(f"Pi file sync found difference: {entry['remote_path']}")
            differences.append(
                {
                    **entry,
                    "reason": "content differs",
                    "uploadable": True,
                }
            )
        else:
            logger.debug(f"Pi file sync match: {entry['remote_path']}")

    logger.info(f"Pi file sync comparison complete with {len(differences)} difference(s)")
    return differences


def _format_difference_list(differences: list[dict[str, Any]], limit: int = 10) -> str:
    lines = [
        f"- {d['remote_path']} ({d['reason']})"
        for d in differences[:limit]
    ]
    if len(differences) > limit:
        lines.append(f"- ... {len(differences) - limit} more")
    return "\n".join(lines)


def upload_local_pi_file_differences(
    klipper_service,
    differences: list[dict[str, Any]],
    logger: logging.Logger | None = None,
) -> list[str]:
    """Upload uploadable local differences to the Pi and return failure messages."""
    logger = logger or logging.getLogger("dod_system")
    failures: list[str] = []
    logger.info(f"Pi file sync uploading {len(differences)} local difference(s) to Pi")

    for diff in differences:
        if not diff.get("uploadable", False):
            logger.warning(f"Pi file sync cannot upload {diff['remote_path']}: {diff['reason']}")
            failures.append(f"{diff['remote_path']}: {diff['reason']}")
            continue

        local_path = diff["local_path"]
        try:
            logger.debug(f"Pi file sync reading upload content from {local_path}")
            content = _normalize_text(local_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error(f"Pi file sync local upload read failed for {local_path}: {exc}")
            failures.append(f"{diff['remote_path']}: local read failed: {exc}")
            continue

        logger.info(f"Pi file sync uploading {diff['remote_path']}")
        result = klipper_service.upload_file_content(
            diff["root"],
            diff["remote_path"],
            content,
        )
        if isinstance(result, dict) and result.get("error"):
            logger.error(f"Pi file sync upload failed for {diff['remote_path']}: {result['error']}")
            failures.append(f"{diff['remote_path']}: {result['error']}")
        else:
            logger.info(f"Pi file sync uploaded {diff['remote_path']}")

    logger.info(f"Pi file sync upload complete with {len(failures)} failure(s)")
    return failures


def prompt_for_local_pi_upload(
    parent: QWidget,
    klipper_service,
    status_callback: Callable[[str], None] | None = None,
    logger: logging.Logger | None = None,
) -> bool:
    """
    Ask whether known local Pi-target files should be uploaded when they differ.

    The Pi remains the source of truth unless the user explicitly uploads the
    local Windows copies.
    """
    logger = logger or logging.getLogger("dod_system")
    logger.info("Pi file sync prompt started")
    differences = collect_local_pi_file_differences(klipper_service, logger)
    uploadable = [d for d in differences if d.get("uploadable", False)]
    if not differences:
        logger.info("Pi file sync prompt found no differences")
        if status_callback:
            status_callback("Pi files match local Pi-target files")
        return False

    if not uploadable:
        logger.warning("Pi file sync prompt found differences but none are uploadable")
        QMessageBox.warning(
            parent,
            "Pi File Sync",
            "Local Pi-target files could not be compared or uploaded.\n\n"
            + _format_difference_list(differences),
        )
        return False

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Pi File Sync")
    box.setText(
        "Local Windows Pi-target files differ from the files on the Pi.\n"
        "The Pi remains the source of truth unless you upload these local copies."
    )
    box.setInformativeText(_format_difference_list(uploadable))
    box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    box.button(QMessageBox.StandardButton.Yes).setText("Upload to Pi")
    box.button(QMessageBox.StandardButton.No).setText("Keep Pi Files")

    if box.exec() != QMessageBox.StandardButton.Yes:
        logger.info("Pi file sync prompt dismissed; keeping Pi files")
        if status_callback:
            status_callback("Kept Pi files as source of truth")
        return False

    logger.info(f"Pi file sync prompt accepted; uploading {len(uploadable)} file(s)")
    failures = upload_local_pi_file_differences(klipper_service, uploadable, logger)
    if failures:
        logger.error(f"Pi file sync prompt upload finished with failures: {failures}")
        QMessageBox.warning(
            parent,
            "Pi File Sync",
            "Some files could not be uploaded.\n\n" + "\n".join(failures[:10]),
        )
        return False

    QMessageBox.information(
        parent,
        "Pi File Sync",
        f"Uploaded {len(uploadable)} file(s) to the Pi.",
    )
    logger.info(f"Pi file sync prompt uploaded {len(uploadable)} file(s)")
    if status_callback:
        status_callback(f"Uploaded {len(uploadable)} local file(s) to the Pi")
    return True


class PiFileEditorWindow(QDialog):
    """Popup window for editing Moonraker-exposed Pi files."""

    def __init__(self, klipper_service, parent=None, logger: logging.Logger | None = None) -> None:
        super().__init__(parent)
        self.klipper_service = klipper_service
        self.logger = logger or logging.getLogger("dod_system")
        self.current_root = "config"
        self.current_path: str | None = None
        self.current_permissions = ""
        self._loading_editor = False
        self._dirty = False
        self._worker_signals = _WorkerSignals()
        self._worker_signals.finished.connect(self._on_worker_finished)
        self._worker_signals.failed.connect(self._on_worker_failed)
        self._worker_callbacks: dict[str, tuple[str, Callable[[Any], None] | None]] = {}

        self.setWindowTitle("Pi File Editor")
        self.setMinimumSize(1100, 700)

        self.logger.info("Pi file editor initializing dialog")
        self._build_ui()
        self.logger.info("Pi file editor dialog initialized")
        QTimer.singleShot(
            0,
            lambda: self.reload_from_pi_async(prompt_sync=False),
        )

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_files_tab(), "Files")
        self.tabs.addTab(self._build_services_tab(), "Services")
        layout.addWidget(self.tabs, 1)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)

    def _build_files_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Root"))
        self.root_combo = QComboBox()
        self.root_combo.setMinimumContentsLength(16)
        self.root_combo.setMinimumWidth(180)
        self.root_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.root_combo.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding,
            QSizePolicy.Policy.Fixed,
        )
        self.root_combo.currentIndexChanged.connect(self._on_root_changed)
        toolbar.addWidget(self.root_combo)

        self.reload_btn = QPushButton("Reload From Pi")
        self.reload_btn.clicked.connect(
            lambda: self.reload_from_pi_async(prompt_sync=True)
        )
        toolbar.addWidget(self.reload_btn)

        self.upload_local_btn = QPushButton("Upload Windows Changes")
        self.upload_local_btn.clicked.connect(
            self._on_upload_local_changes
        )
        toolbar.addWidget(self.upload_local_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.file_tree = QTreeWidget()
        self.file_tree.setHeaderLabels(["File", "Size", "Modified", "Perms"])
        self.file_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.file_tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.file_tree.itemSelectionChanged.connect(self._on_file_selected)
        self.file_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.file_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.file_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.file_tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        splitter.addWidget(self.file_tree)

        editor_panel = QWidget()
        editor_layout = QVBoxLayout(editor_panel)

        self.path_label = QLabel("No file selected")
        editor_layout.addWidget(self.path_label)

        self.editor = QPlainTextEdit()
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.textChanged.connect(self._on_editor_changed)
        editor_layout.addWidget(self.editor, 1)

        action_row = QHBoxLayout()
        self.dirty_label = QLabel("")
        action_row.addWidget(self.dirty_label)
        action_row.addStretch()

        self.copy_to_local_btn = QPushButton("Copy To Local")
        self.copy_to_local_btn.clicked.connect(self._copy_current_file_to_local_async)
        self.copy_to_local_btn.setEnabled(False)
        action_row.addWidget(self.copy_to_local_btn)

        self.save_btn = QPushButton("Save To Pi")
        self.save_btn.clicked.connect(lambda: self._save_current_file_async(restart=False))
        self.save_btn.setEnabled(False)
        action_row.addWidget(self.save_btn)

        self.save_restart_btn = QPushButton("Save && Restart Klipper")
        self.save_restart_btn.clicked.connect(lambda: self._save_current_file_async(restart=True))
        self.save_restart_btn.setEnabled(False)
        action_row.addWidget(self.save_restart_btn)
        editor_layout.addLayout(action_row)

        splitter.addWidget(editor_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        layout.addWidget(splitter, 1)
        return tab

    def _build_services_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        row = QHBoxLayout()
        self.refresh_services_btn = QPushButton("Refresh Services")
        self.refresh_services_btn.clicked.connect(
            self.refresh_services_async
        )
        row.addWidget(self.refresh_services_btn)
        row.addStretch()
        layout.addLayout(row)

        self.service_tree = QTreeWidget()
        self.service_tree.setHeaderLabels(["Service", "Active", "Sub State"])
        self.service_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.service_tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.service_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.service_tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.service_tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.service_tree, 1)

        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("Moonraker only exposes authorized services."))
        action_row.addStretch()
        for action in ("start", "restart", "stop"):
            button = QPushButton(action.title())
            button.clicked.connect(
                lambda checked=False, a=action: self._run_logged(
                    f"service {a} button",
                    lambda: self._service_action(a),
                )
            )
            action_row.addWidget(button)
        layout.addLayout(action_row)
        return tab

    def _run_logged(self, action: str, func):
        """Run a dialog action with system-log breadcrumbs and a visible error."""
        self.logger.info(f"Pi file editor action started: {action}")
        try:
            result = func()
            self.logger.info(f"Pi file editor action finished: {action}")
            return result
        except Exception as exc:
            self.logger.exception(f"Pi file editor action failed: {action}")
            self._set_status(f"{action} failed: {exc}")
            QMessageBox.critical(
                self,
                "Pi File Editor",
                f"{action} failed:\n{exc}",
            )
            return None

    def _run_background(
        self,
        action: str,
        work: Callable[[], Any],
        on_success: Callable[[Any], None] | None = None,
    ) -> None:
        """Run blocking Moonraker/file work away from the Qt GUI thread."""
        task_id = uuid.uuid4().hex
        self._worker_callbacks[task_id] = (action, on_success)
        self.logger.info(f"Pi file editor background action queued: {action}")
        self._set_status(f"{action}...")

        def worker() -> None:
            self.logger.info(f"Pi file editor background action started: {action}")
            try:
                result = work()
            except Exception:
                self._worker_signals.failed.emit(task_id, traceback.format_exc())
                return
            self._worker_signals.finished.emit(task_id, result)

        threading.Thread(target=worker, daemon=True).start()

    def _on_worker_finished(self, task_id: str, result: Any) -> None:
        action, on_success = self._worker_callbacks.pop(task_id, ("unknown", None))
        self.logger.info(f"Pi file editor background action finished: {action}")
        try:
            if on_success:
                on_success(result)
        except Exception:
            self.logger.exception(f"Pi file editor result handler failed: {action}")
            QMessageBox.critical(
                self,
                "Pi File Editor",
                f"{action} result handling failed. See logs/dod_system.log.",
            )

    def _on_worker_failed(self, task_id: str, error_text: str) -> None:
        action, _ = self._worker_callbacks.pop(task_id, ("unknown", None))
        self.logger.error(f"Pi file editor background action failed: {action}\n{error_text}")
        self._set_status(f"{action} failed")
        QMessageBox.critical(
            self,
            "Pi File Editor",
            f"{action} failed. See logs/dod_system.log.",
        )

    @staticmethod
    def _result_error(result: Any) -> str | None:
        return result.get("error") if isinstance(result, dict) and result.get("error") else None

    def reload_from_pi_async(self, prompt_sync: bool = False) -> None:
        """Reload roots, files, and services without blocking the GUI thread."""
        self.logger.info(
            f"Pi file editor async reload requested; connected={getattr(self.klipper_service, 'is_connected', False)}"
        )
        if not getattr(self.klipper_service, "is_connected", False):
            self.logger.warning("Pi file editor async reload blocked: not connected to Moonraker")
            self._set_status("Not connected to Moonraker")
            return
        if self._dirty and not self._confirm_discard_changes():
            self.logger.info("Pi file editor async reload canceled due to unsaved changes")
            return

        requested_root = self.current_root

        def work() -> dict[str, Any]:
            roots = self.klipper_service.list_file_roots()
            root_error = self._result_error(roots)
            if root_error:
                return {"error": root_error, "stage": "roots"}

            root_entries = roots if isinstance(roots, list) else []
            selected_root = self._choose_root_name(root_entries, requested_root)
            files = self.klipper_service.list_files(selected_root)
            files_error = self._result_error(files)
            if files_error:
                return {
                    "error": files_error,
                    "stage": "files",
                    "roots": root_entries,
                    "selected_root": selected_root,
                }

            services = self.klipper_service.get_machine_system_info()
            return {
                "roots": root_entries,
                "selected_root": selected_root,
                "files": files if isinstance(files, list) else [],
                "services": services,
            }

        self._run_background(
            "reload from Pi",
            work,
            lambda result: self._apply_reload_result(result, prompt_sync),
        )

    def _apply_reload_result(self, result: dict[str, Any], prompt_sync: bool) -> None:
        error = result.get("error") if isinstance(result, dict) else None
        if error:
            self.logger.error(f"Pi file editor reload failed at {result.get('stage')}: {error}")
            self._set_status(f"Failed to load {result.get('stage', 'Pi files')}: {error}")
            if result.get("roots"):
                self._populate_roots(result["roots"], result.get("selected_root", self.current_root))
            return

        selected_root = str(result.get("selected_root", "config"))
        self._populate_roots(result.get("roots", []), selected_root)
        self._populate_file_list(result.get("files", []), selected_root)
        self._populate_services(result.get("services", {}))
        self._set_status(f"Loaded {self.file_tree.topLevelItemCount()} file(s) from {selected_root}")
        if prompt_sync:
            self._prompt_local_sync_async()

    @staticmethod
    def _choose_root_name(root_entries: list[dict[str, Any]], requested_root: str) -> str:
        names = [str(root.get("name", "")) for root in root_entries if root.get("name")]
        if requested_root in names:
            return requested_root
        if "config" in names:
            return "config"
        return names[0] if names else "config"

    def _populate_roots(self, root_entries: list[dict[str, Any]], selected_root: str) -> None:
        self.logger.info(f"Pi file editor populating {len(root_entries)} root entry(ies)")
        self.root_combo.blockSignals(True)
        self.root_combo.clear()
        for root in root_entries:
            name = str(root.get("name", ""))
            if not name:
                continue
            label = f"{name} ({root.get('permissions', '')})"
            self.root_combo.addItem(label, root)

        if self.root_combo.count() == 0:
            self.root_combo.addItem("config", {"name": "config", "permissions": "rw"})

        target_index = 0
        for i in range(self.root_combo.count()):
            data = self.root_combo.itemData(i) or {}
            if data.get("name") == selected_root:
                target_index = i
                break
        self.root_combo.setCurrentIndex(target_index)
        self._fit_root_combo_to_contents()
        self.root_combo.blockSignals(False)
        self.current_root = self._selected_root_name()
        self.logger.info(f"Pi file editor selected root: {self.current_root}")

    def _fit_root_combo_to_contents(self) -> None:
        """Keep the root selector and popup wide enough for root labels."""
        if self.root_combo.count() <= 0:
            self.root_combo.setMinimumWidth(180)
            return

        metrics = self.root_combo.fontMetrics()
        content_width = max(
            metrics.horizontalAdvance(self.root_combo.itemText(i))
            for i in range(self.root_combo.count())
        )
        padded_width = content_width + 56
        closed_width = max(180, min(padded_width, 360))
        self.root_combo.setMinimumWidth(closed_width)
        self.root_combo.view().setMinimumWidth(max(closed_width, padded_width))

    def _populate_file_list(self, files: list[dict[str, Any]], root: str) -> None:
        self.current_root = root
        self.file_tree.clear()
        for info in sorted(files, key=lambda i: str(i.get("path", ""))):
            path = str(info.get("path", ""))
            if not path:
                continue
            item = QTreeWidgetItem(
                [
                    path,
                    self._format_size(info.get("size")),
                    self._format_modified(info.get("modified")),
                    str(info.get("permissions", "")),
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, info)
            self.file_tree.addTopLevelItem(item)

        self._clear_editor()
        self.logger.info(
            f"Pi file editor populated {self.file_tree.topLevelItemCount()} file row(s)"
        )

    def _populate_services(self, info: Any) -> None:
        error = self._result_error(info)
        if error:
            self.logger.error(f"Pi file editor failed to load services: {error}")
            self._set_status(f"Failed to load services: {error}")
            return

        system_info = info.get("system_info", info) if isinstance(info, dict) else {}
        services = system_info.get("available_services", [])
        states = system_info.get("service_state", {})

        self.service_tree.clear()
        for service in sorted(services):
            state = states.get(service, {}) if isinstance(states, dict) else {}
            item = QTreeWidgetItem(
                [
                    str(service),
                    str(state.get("active_state", "")),
                    str(state.get("sub_state", "")),
                ]
            )
            item.setData(0, Qt.ItemDataRole.UserRole, str(service))
            self.service_tree.addTopLevelItem(item)
        self.logger.info(f"Pi file editor populated {self.service_tree.topLevelItemCount()} service row(s)")

    def refresh_services_async(self) -> None:
        self._run_background(
            "refresh services",
            self.klipper_service.get_machine_system_info,
            self._populate_services,
        )

    def _load_file_list_async(self) -> None:
        root = self._selected_root_name()
        self.logger.info(f"Pi file editor async file list requested for root {root}")

        def work() -> dict[str, Any]:
            files = self.klipper_service.list_files(root)
            error = self._result_error(files)
            if error:
                return {"error": error, "root": root}
            return {"files": files if isinstance(files, list) else [], "root": root}

        self._run_background("load file list", work, self._apply_file_list_result)

    def _apply_file_list_result(self, result: dict[str, Any]) -> None:
        error = result.get("error")
        root = str(result.get("root", self.current_root))
        if error:
            self.logger.error(f"Pi file editor failed to load files from {root}: {error}")
            self._set_status(f"Failed to load files: {error}")
            return
        self._populate_file_list(result.get("files", []), root)
        self._set_status(f"Loaded {self.file_tree.topLevelItemCount()} file(s) from {root}")

    def _download_selected_file_async(self, root: str, path: str, permissions: str) -> None:
        self.logger.info(f"Pi file editor async download requested for {root}/{path}")

        def work() -> dict[str, Any]:
            result = self.klipper_service.download_file(root, path)
            error = self._result_error(result)
            if error:
                return {"error": error, "root": root, "path": path}
            return {
                "root": root,
                "path": path,
                "permissions": permissions,
                "content": str(result.get("content", "")),
            }

        self._run_background("download file", work, self._apply_download_result)

    def _apply_download_result(self, result: dict[str, Any]) -> None:
        root = str(result.get("root", self.current_root))
        path = str(result.get("path", ""))
        error = result.get("error")
        if error:
            self.logger.error(f"Pi file editor failed to read {root}/{path}: {error}")
            QMessageBox.warning(
                self,
                "Pi File Editor",
                f"Failed to read {root}/{path}:\n{error}",
            )
            return

        self.current_root = root
        self.current_path = path
        self.current_permissions = str(result.get("permissions", ""))
        self.path_label.setText(f"{root}/{path}")
        self._loading_editor = True
        self.editor.setPlainText(str(result.get("content", "")))
        self._loading_editor = False
        self._dirty = False
        self._refresh_save_state()
        self._set_status(f"Loaded {root}/{path} from Pi")

    def _save_current_file_async(self, restart: bool = False) -> None:
        self.logger.info(
            f"Pi file editor async save requested for {self.current_root}/{self.current_path}; restart={restart}"
        )
        if not self.current_path:
            self.logger.warning("Pi file editor save ignored: no file selected")
            return
        if not self._can_save_current_file():
            self.logger.warning(
                f"Pi file editor save blocked: {self.current_root}/{self.current_path} is not writable"
            )
            QMessageBox.warning(
                self,
                "Pi File Editor",
                "This file is not writable through Moonraker.",
            )
            return

        root = self.current_root
        path = self.current_path
        content = _normalize_text(self.editor.toPlainText())

        def work() -> dict[str, Any]:
            result = self.klipper_service.upload_file_content(root, path, content)
            error = self._result_error(result)
            if error:
                return {"error": error, "root": root, "path": path, "restart": restart}
            return {"root": root, "path": path, "restart": restart}

        self._run_background("save file", work, self._apply_save_result)

    def _apply_save_result(self, result: dict[str, Any]) -> None:
        root = str(result.get("root", self.current_root))
        path = str(result.get("path", self.current_path or ""))
        error = result.get("error")
        if error:
            self.logger.error(f"Pi file editor save failed for {root}/{path}: {error}")
            QMessageBox.warning(
                self,
                "Pi File Editor",
                f"Failed to save {root}/{path}:\n{error}",
            )
            return

        self._dirty = False
        self._refresh_save_state()
        self.logger.info(f"Pi file editor saved {root}/{path}")
        self._set_status(f"Saved {root}/{path} to Pi")

        if result.get("restart"):
            answer = QMessageBox.question(
                self,
                "Restart Klipper",
                "Restart Klipper now to apply saved config changes?",
            )
            if answer == QMessageBox.StandardButton.Yes:
                self._restart_klipper_async()
            else:
                self.logger.info("Pi file editor user skipped Klipper restart")

    def _copy_current_file_to_local_async(self) -> None:
        """Download the current Pi file and write it to the mapped local copy."""
        self.logger.info(
            f"Pi file editor copy-to-local requested for {self.current_root}/{self.current_path}"
        )
        if not self.current_path:
            self.logger.warning("Pi file editor copy-to-local ignored: no file selected")
            return

        local_path = _local_path_for_pi_file(self.current_root, self.current_path)
        if local_path is None:
            self.logger.warning(
                f"Pi file editor copy-to-local has no mapping for {self.current_root}/{self.current_path}"
            )
            QMessageBox.information(
                self,
                "Copy To Local",
                "This Pi file has no local project mapping.",
            )
            return

        if self._dirty:
            answer = QMessageBox.question(
                self,
                "Copy To Local",
                "The editor has unsaved changes. Copy the current Pi file to local and leave editor changes unsaved?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.logger.info("Pi file editor copy-to-local canceled due to unsaved editor changes")
                return

        if local_path.exists():
            answer = QMessageBox.question(
                self,
                "Copy To Local",
                f"Overwrite local file?\n{local_path}",
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.logger.info(f"Pi file editor copy-to-local canceled for {local_path}")
                return

        root = self.current_root
        remote_path = self.current_path

        def work() -> dict[str, Any]:
            result = self.klipper_service.download_file(root, remote_path)
            error = self._result_error(result)
            if error:
                return {
                    "error": error,
                    "root": root,
                    "remote_path": remote_path,
                    "local_path": local_path,
                }

            local_path.parent.mkdir(parents=True, exist_ok=True)
            content = _normalize_text(str(result.get("content", "")))
            local_path.write_text(content, encoding="utf-8")
            return {
                "root": root,
                "remote_path": remote_path,
                "local_path": local_path,
            }

        self._run_background("copy Pi file to local", work, self._apply_copy_to_local_result)

    def _apply_copy_to_local_result(self, result: dict[str, Any]) -> None:
        local_path = Path(result.get("local_path", ""))
        remote = f"{result.get('root', self.current_root)}/{result.get('remote_path', self.current_path or '')}"
        error = result.get("error")
        if error:
            self.logger.error(f"Pi file editor copy-to-local failed for {remote}: {error}")
            QMessageBox.warning(
                self,
                "Copy To Local",
                f"Failed to copy {remote}:\n{error}",
            )
            return

        self.logger.info(f"Pi file editor copied {remote} to {local_path}")
        self._set_status(f"Copied {remote} to {local_path.name}")

    def _restart_klipper_async(self) -> None:
        self._run_background(
            "restart Klipper",
            self.klipper_service.restart_klipper,
            self._apply_restart_result,
        )

    def _apply_restart_result(self, result: dict[str, Any]) -> None:
        error = self._result_error(result)
        if error:
            self.logger.error(f"Pi file editor Klipper restart failed: {error}")
            QMessageBox.warning(
                self,
                "Restart Klipper",
                f"Klipper restart failed:\n{error}",
            )
            return
        self.logger.info("Pi file editor Klipper restart requested")
        self._set_status("Klipper restart requested")

    def _prompt_local_sync_async(self) -> None:
        self.logger.info("Pi file editor async local sync comparison requested")
        self._run_background(
            "compare local Pi files",
            lambda: collect_local_pi_file_differences(self.klipper_service, self.logger),
            self._apply_local_sync_comparison,
        )

    def _apply_local_sync_comparison(self, differences: list[dict[str, Any]]) -> None:
        uploadable = [d for d in differences if d.get("uploadable", False)]
        if not differences:
            self.logger.info("Pi file sync found no differences")
            self._set_status("Pi files match local Pi-target files")
            return

        if not uploadable:
            self.logger.warning("Pi file sync found differences but none are uploadable")
            QMessageBox.warning(
                self,
                "Pi File Sync",
                "Local Pi-target files could not be compared or uploaded.\n\n"
                + _format_difference_list(differences),
            )
            return

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Pi File Sync")
        box.setText(
            "Local Windows Pi-target files differ from the files on the Pi.\n"
            "The Pi remains the source of truth unless you upload these local copies."
        )
        box.setInformativeText(_format_difference_list(uploadable))
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.button(QMessageBox.StandardButton.Yes).setText("Upload to Pi")
        box.button(QMessageBox.StandardButton.No).setText("Keep Pi Files")

        if box.exec() != QMessageBox.StandardButton.Yes:
            self.logger.info("Pi file sync dismissed; keeping Pi files")
            self._set_status("Kept Pi files as source of truth")
            return

        self._run_background(
            "upload local Pi files",
            lambda: upload_local_pi_file_differences(
                self.klipper_service,
                uploadable,
                self.logger,
            ),
            self._apply_local_sync_upload,
        )

    def _apply_local_sync_upload(self, failures: list[str]) -> None:
        if failures:
            self.logger.error(f"Pi file sync upload finished with failures: {failures}")
            QMessageBox.warning(
                self,
                "Pi File Sync",
                "Some files could not be uploaded.\n\n" + "\n".join(failures[:10]),
            )
            return
        self.logger.info("Pi file sync upload finished successfully")
        QMessageBox.information(self, "Pi File Sync", "Uploaded local file(s) to the Pi.")
        self._set_status("Uploaded local file(s) to the Pi")
        self._load_file_list_async()

    def reload_from_pi(self, prompt_sync: bool = False) -> None:
        """Reload roots and file list from Moonraker."""
        self.reload_from_pi_async(prompt_sync=prompt_sync)

    def _load_roots(self) -> None:
        self.reload_from_pi_async(prompt_sync=False)

    def _load_file_list(self) -> None:
        self._load_file_list_async()

    def refresh_services(self) -> None:
        self.refresh_services_async()

    def _on_root_changed(self) -> None:
        self._run_logged("root changed", self._on_root_changed_inner)

    def _on_root_changed_inner(self) -> None:
        self.logger.info(f"Pi file editor root changed to {self._selected_root_name()}")
        if self._dirty and not self._confirm_discard_changes():
            self.logger.info("Pi file editor root change canceled due to unsaved changes")
            return
        self._load_file_list_async()

    def _on_file_selected(self) -> None:
        self._run_logged("file selected", self._on_file_selected_inner)

    def _on_file_selected_inner(self) -> None:
        selected = self.file_tree.selectedItems()
        if not selected:
            self.logger.debug("Pi file editor file selection changed with no selected item")
            return
        if self._dirty and not self._confirm_discard_changes():
            self.logger.info("Pi file editor file selection canceled due to unsaved changes")
            return

        info = selected[0].data(0, Qt.ItemDataRole.UserRole) or {}
        path = str(info.get("path", ""))
        permissions = str(info.get("permissions", ""))
        self.logger.info(
            f"Pi file editor selected file {self.current_root}/{path} permissions={permissions}"
        )
        self._download_selected_file_async(self.current_root, path, permissions)

    def _on_editor_changed(self) -> None:
        if self._loading_editor or self.current_path is None:
            return
        self._dirty = True
        self.logger.debug(f"Pi file editor marked dirty: {self.current_root}/{self.current_path}")
        self._refresh_save_state()

    def _save_current_file(self, restart: bool = False) -> None:
        self._save_current_file_async(restart=restart)

    def _service_action(self, action: str) -> None:
        selected = self.service_tree.selectedItems()
        if not selected:
            self.logger.warning(f"Pi file editor service {action} ignored: no service selected")
            return
        service = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if not service:
            self.logger.warning(f"Pi file editor service {action} ignored: selected service missing")
            return

        self.logger.info(f"Pi file editor service action requested: {action} {service}")
        if action in {"restart", "stop"}:
            answer = QMessageBox.question(
                self,
                "Service Action",
                f"{action.title()} service '{service}'?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                self.logger.info(f"Pi file editor service {action} canceled for {service}")
                return

        self._run_background(
            f"service {action}",
            lambda: self.klipper_service.manage_service(str(service), action),
            lambda result: self._apply_service_action_result(str(service), action, result),
        )

    def _apply_service_action_result(self, service: str, action: str, result: dict[str, Any]) -> None:
        error = self._result_error(result)
        if error:
            self.logger.error(f"Pi file editor service {action} failed for {service}: {error}")
            QMessageBox.warning(
                self,
                "Service Action",
                f"Service action failed:\n{error}",
            )
            return

        self.logger.info(f"Pi file editor service {action} accepted for {service}")
        self._set_status(f"Requested {action} for {service}")
        self.refresh_services_async()

    def _on_upload_local_changes(self) -> None:
        self.logger.info("Pi file editor manual local sync requested")
        self._prompt_local_sync_async()

    def _prompt_local_sync(self) -> bool:
        self.logger.info("Pi file editor local sync prompt requested")
        self._prompt_local_sync_async()
        return False

    def _selected_root_name(self) -> str:
        data = self.root_combo.currentData() or {}
        return str(data.get("name", "config"))

    def _selected_root_permissions(self) -> str:
        data = self.root_combo.currentData() or {}
        return str(data.get("permissions", ""))

    def _can_save_current_file(self) -> bool:
        root_permissions = self._selected_root_permissions()
        return (
            bool(self.current_path)
            and "w" in self.current_permissions
            and "w" in root_permissions
        )

    def _refresh_save_state(self) -> None:
        can_save = self._can_save_current_file()
        can_copy = bool(self.current_path)
        self.copy_to_local_btn.setEnabled(can_copy)
        self.save_btn.setEnabled(can_save)
        self.save_restart_btn.setEnabled(can_save)
        self.dirty_label.setText("Unsaved changes" if self._dirty else "")

    def _clear_editor(self) -> None:
        self.current_path = None
        self.current_permissions = ""
        self._loading_editor = True
        self.editor.clear()
        self._loading_editor = False
        self._dirty = False
        self.path_label.setText("No file selected")
        self._refresh_save_state()

    def _confirm_discard_changes(self) -> bool:
        if not self._dirty:
            return True
        self.logger.info("Pi file editor asking to discard unsaved changes")
        answer = QMessageBox.question(
            self,
            "Unsaved Changes",
            "Discard unsaved editor changes?",
        )
        accepted = answer == QMessageBox.StandardButton.Yes
        self.logger.info(f"Pi file editor discard unsaved changes accepted={accepted}")
        return accepted

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    @staticmethod
    def _format_size(size: Any) -> str:
        try:
            value = int(size)
        except (TypeError, ValueError):
            return "-"
        if value < 1024:
            return f"{value} B"
        if value < 1024 * 1024:
            return f"{value / 1024:.1f} kB"
        return f"{value / (1024 * 1024):.1f} MB"

    @staticmethod
    def _format_modified(modified: Any) -> str:
        try:
            return datetime.fromtimestamp(float(modified)).strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError, OSError):
            return "-"

    def closeEvent(self, event) -> None:
        self.logger.info("Pi file editor close requested")
        if self._confirm_discard_changes():
            self.logger.info("Pi file editor closing")
            super().closeEvent(event)
        else:
            self.logger.info("Pi file editor close canceled")
            event.ignore()
