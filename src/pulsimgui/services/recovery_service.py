"""Crash recovery service for saving and restoring unsaved work."""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QMessageBox

from pulsimgui.models.project import Project


class RecoveryService(QObject):
    """Service for crash recovery and session state management."""

    recovery_available = Signal(str)  # Emits recovery file path

    # Recovery file settings
    RECOVERY_DIR = Path(tempfile.gettempdir()) / "pulsimgui_recovery"
    LOCK_FILE = RECOVERY_DIR / "session.lock"
    STATE_FILE = RECOVERY_DIR / "session_state.json"
    RECOVERY_INTERVAL = 60000  # Save recovery data every 60 seconds

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project: Optional[Project] = None
        self._recovery_timer = QTimer(self)
        self._recovery_timer.timeout.connect(self._save_recovery_data)
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Ensure recovery directory exists
        self.RECOVERY_DIR.mkdir(parents=True, exist_ok=True)

    def start_session(self) -> Optional[str]:
        """
        Start a new session and check for crash recovery files.

        Returns:
            Path to recovery file if one exists and user wants to recover, else None
        """
        recovery_path = self._check_for_recovery()
        if recovery_path:
            return recovery_path

        # Start new session
        self._create_lock_file()
        self._recovery_timer.start(self.RECOVERY_INTERVAL)
        return None

    def end_session(self, clean_exit: bool = True) -> None:
        """
        End the current session.

        Args:
            clean_exit: If True, removes recovery files (normal exit)
        """
        self._recovery_timer.stop()

        if clean_exit:
            self._cleanup_recovery_files()

        self._remove_lock_file()

    def set_project(self, project: Project) -> None:
        """Set the current project to track for recovery."""
        self._project = project

    def save_now(self) -> None:
        """Force an immediate save of recovery data."""
        self._save_recovery_data()

    def _check_for_recovery(self) -> Optional[str]:
        """
        Check if there are recovery files from a previous crash.

        Returns:
            Path to the recovery file if exists and user wants to recover
        """
        # Check if another session is running (lock file exists)
        if self.LOCK_FILE.exists():
            try:
                # Read lock file to get session info
                with open(self.LOCK_FILE, "r") as f:
                    lock_data = json.load(f)
                pid = lock_data.get("pid")

                # Check if process is still running
                if pid and self._is_process_running(pid):
                    # Another instance is running - don't recover
                    return None
            except (json.JSONDecodeError, IOError):
                pass  # Lock file corrupted, proceed with recovery check

        # Check for state file from crashed session
        if self.STATE_FILE.exists():
            try:
                with open(self.STATE_FILE, "r") as f:
                    state = json.load(f)

                recovery_file = state.get("recovery_file")
                if recovery_file and Path(recovery_file).exists():
                    # Found recovery data - return the path
                    return recovery_file

            except (json.JSONDecodeError, IOError):
                pass  # State file corrupted, can't recover

        return None

    def show_recovery_dialog(self, recovery_path: str) -> bool:
        """
        Show a dialog asking user if they want to recover.

        Args:
            recovery_path: Path to the recovery file

        Returns:
            True if user chose to recover, False otherwise
        """
        try:
            # Get some info about the recovery file
            mod_time = datetime.fromtimestamp(Path(recovery_path).stat().st_mtime)
            time_str = mod_time.strftime("%Y-%m-%d %H:%M:%S")

            result = QMessageBox.question(
                None,
                "Recover Unsaved Work",
                f"PulsimGui found unsaved work from a previous session.\n\n"
                f"Recovery file: {Path(recovery_path).name}\n"
                f"Last modified: {time_str}\n\n"
                f"Would you like to recover this work?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

            if result == QMessageBox.StandardButton.Yes:
                return True
            else:
                # User declined - clean up recovery files
                self._cleanup_recovery_files()
                return False

        except Exception:
            return False

    def recover_project(self, recovery_path: str) -> Optional[Project]:
        """
        Load a project from a recovery file.

        Args:
            recovery_path: Path to the recovery file

        Returns:
            Recovered Project object, or None if recovery failed
        """
        try:
            project = Project.load(recovery_path)
            # Mark as dirty since it's from recovery (needs to be saved)
            project.mark_dirty()
            # Clear the saved path so user must "Save As"
            project._path = None

            # Clean up recovery files after successful recovery
            self._cleanup_recovery_files()

            return project

        except Exception as e:
            QMessageBox.warning(
                None,
                "Recovery Failed",
                f"Unable to recover the project:\n{e}\n\n"
                "The recovery file may be corrupted.",
            )
            return None

    def _save_recovery_data(self) -> None:
        """Save current project state for crash recovery."""
        if self._project is None:
            return

        # Only save if there are unsaved changes
        if not self._project.is_dirty:
            return

        try:
            # Create recovery file
            recovery_file = self.RECOVERY_DIR / f"recovery_{self._session_id}.pulsim"
            self._project.save(str(recovery_file))

            # Update state file
            state = {
                "session_id": self._session_id,
                "recovery_file": str(recovery_file),
                "timestamp": datetime.now().isoformat(),
                "project_name": self._project.name,
                "original_path": str(self._project.path) if self._project.path else None,
            }
            with open(self.STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)

        except Exception:
            pass  # Silently fail - don't interrupt user work

    def _create_lock_file(self) -> None:
        """Create a lock file to indicate an active session."""
        try:
            lock_data = {
                "pid": os.getpid(),
                "session_id": self._session_id,
                "start_time": datetime.now().isoformat(),
            }
            with open(self.LOCK_FILE, "w") as f:
                json.dump(lock_data, f)
        except IOError:
            pass

    def _remove_lock_file(self) -> None:
        """Remove the lock file."""
        try:
            if self.LOCK_FILE.exists():
                self.LOCK_FILE.unlink()
        except IOError:
            pass

    def _cleanup_recovery_files(self) -> None:
        """Remove all recovery files for clean exit."""
        try:
            # Remove state file
            if self.STATE_FILE.exists():
                self.STATE_FILE.unlink()

            # Remove recovery project files
            for recovery_file in self.RECOVERY_DIR.glob("recovery_*.pulsim"):
                try:
                    recovery_file.unlink()
                except IOError:
                    pass

        except Exception:
            pass

    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with the given PID is running."""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
