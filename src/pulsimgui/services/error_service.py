"""Error handling service for user-friendly error messages."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox, QWidget


class ErrorSeverity(Enum):
    """Error severity levels."""

    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


@dataclass
class ErrorInfo:
    """Information about an error."""

    title: str
    message: str
    details: str = ""
    severity: ErrorSeverity = ErrorSeverity.ERROR
    suggestion: str = ""


# User-friendly error message mappings
ERROR_MESSAGES = {
    # File operations
    "file_not_found": ErrorInfo(
        title="File Not Found",
        message="The specified file could not be found.",
        suggestion="Please check the file path and try again.",
    ),
    "file_permission_denied": ErrorInfo(
        title="Permission Denied",
        message="You don't have permission to access this file.",
        suggestion="Check the file permissions or try running as administrator.",
    ),
    "file_corrupted": ErrorInfo(
        title="File Corrupted",
        message="The project file appears to be corrupted or in an invalid format.",
        suggestion="Try opening a backup file or create a new project.",
    ),
    "file_save_failed": ErrorInfo(
        title="Save Failed",
        message="Unable to save the project file.",
        suggestion="Check if the disk is full or if you have write permissions.",
    ),
    # Circuit errors
    "circuit_empty": ErrorInfo(
        title="Empty Circuit",
        message="The circuit has no components.",
        suggestion="Add at least one component before running the simulation.",
        severity=ErrorSeverity.WARNING,
    ),
    "circuit_no_ground": ErrorInfo(
        title="No Ground Reference",
        message="The circuit has no ground reference.",
        suggestion="Add a ground symbol to define the reference voltage (0V).",
    ),
    "circuit_floating_node": ErrorInfo(
        title="Floating Node",
        message="One or more nodes in the circuit are not properly connected.",
        suggestion="Check all connections and ensure every node is connected to at least two components.",
    ),
    "circuit_short": ErrorInfo(
        title="Short Circuit Detected",
        message="A short circuit was detected in your design.",
        suggestion="Check for voltage sources connected in parallel or unintended direct connections.",
    ),
    # Simulation errors
    "sim_convergence": ErrorInfo(
        title="Simulation Failed",
        message="The simulation failed to converge to a solution.",
        suggestion="Try adjusting the time step, initial conditions, or check for extreme component values.",
    ),
    "sim_timeout": ErrorInfo(
        title="Simulation Timeout",
        message="The simulation took too long and was stopped.",
        suggestion="Try reducing the simulation time or simplifying the circuit.",
    ),
    "sim_invalid_params": ErrorInfo(
        title="Invalid Parameters",
        message="One or more simulation parameters are invalid.",
        suggestion="Check the simulation settings for valid time ranges and step sizes.",
    ),
    "sim_no_result": ErrorInfo(
        title="No Results",
        message="The simulation completed but produced no results.",
        suggestion="Check if any signals are being probed or if the simulation time is too short.",
        severity=ErrorSeverity.WARNING,
    ),
    # Component errors
    "component_invalid_value": ErrorInfo(
        title="Invalid Value",
        message="The component value is invalid or out of range.",
        suggestion="Enter a valid positive number with optional SI prefix (e.g., 1k, 10u, 1m).",
    ),
    "component_duplicate_name": ErrorInfo(
        title="Duplicate Name",
        message="A component with this name already exists.",
        suggestion="Choose a unique name for the component.",
    ),
    # Export errors
    "export_failed": ErrorInfo(
        title="Export Failed",
        message="Unable to export the file.",
        suggestion="Check if you have write permissions and sufficient disk space.",
    ),
    "export_no_data": ErrorInfo(
        title="No Data to Export",
        message="There is no data available to export.",
        suggestion="Run a simulation first to generate data for export.",
        severity=ErrorSeverity.WARNING,
    ),
    # Import errors
    "import_failed": ErrorInfo(
        title="Import Failed",
        message="Unable to import the file.",
        suggestion="Check if the file format is correct and the file is not corrupted.",
    ),
    "import_unsupported_format": ErrorInfo(
        title="Unsupported Format",
        message="The file format is not supported.",
        suggestion="Use a supported file format (SPICE netlist, JSON, or PulsimGui project).",
    ),
}


class ErrorService(QObject):
    """Service for handling and displaying errors."""

    error_occurred = Signal(str, str, str)  # title, message, details

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._parent_widget = parent

    def set_parent_widget(self, widget: QWidget) -> None:
        """Set the parent widget for dialogs."""
        self._parent_widget = widget

    def show_error(
        self,
        error_key: str,
        details: str = "",
        exception: Exception | None = None,
    ) -> None:
        """Show an error dialog using a predefined error key."""
        info = ERROR_MESSAGES.get(error_key)
        if info is None:
            # Fallback for unknown error keys
            info = ErrorInfo(
                title="Error",
                message=f"An error occurred: {error_key}",
                details=details or str(exception) if exception else "",
            )
        else:
            # Use provided details or extract from exception
            if details:
                info = ErrorInfo(
                    title=info.title,
                    message=info.message,
                    details=details,
                    severity=info.severity,
                    suggestion=info.suggestion,
                )
            elif exception:
                info = ErrorInfo(
                    title=info.title,
                    message=info.message,
                    details=str(exception),
                    severity=info.severity,
                    suggestion=info.suggestion,
                )

        self._display_error(info)

    def show_custom_error(
        self,
        title: str,
        message: str,
        details: str = "",
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        suggestion: str = "",
    ) -> None:
        """Show a custom error dialog."""
        info = ErrorInfo(
            title=title,
            message=message,
            details=details,
            severity=severity,
            suggestion=suggestion,
        )
        self._display_error(info)

    def show_exception(
        self,
        exception: Exception,
        context: str = "",
    ) -> None:
        """Show an error dialog for an exception with context."""
        error_type = type(exception).__name__
        error_msg = str(exception)

        # Try to map common exceptions to user-friendly messages
        if isinstance(exception, FileNotFoundError):
            self.show_error("file_not_found", details=error_msg)
        elif isinstance(exception, PermissionError):
            self.show_error("file_permission_denied", details=error_msg)
        elif isinstance(exception, ValueError):
            self.show_custom_error(
                title="Invalid Value",
                message=f"An invalid value was provided{f' for {context}' if context else ''}.",
                details=error_msg,
                suggestion="Check the input values and try again.",
            )
        elif isinstance(exception, TimeoutError):
            self.show_error("sim_timeout", details=error_msg)
        else:
            # Generic error for unknown exceptions
            self.show_custom_error(
                title="Error",
                message=f"An unexpected error occurred{f' while {context}' if context else ''}.",
                details=f"{error_type}: {error_msg}",
                suggestion="Please try again. If the problem persists, check the log files.",
            )

    def _display_error(self, info: ErrorInfo) -> None:
        """Display the error dialog."""
        # Emit signal for logging/monitoring
        self.error_occurred.emit(info.title, info.message, info.details)

        # Build full message
        full_message = info.message
        if info.suggestion:
            full_message += f"\n\n{info.suggestion}"
        if info.details:
            full_message += f"\n\nDetails: {info.details}"

        # Choose dialog type based on severity
        if info.severity == ErrorSeverity.INFO:
            QMessageBox.information(
                self._parent_widget,
                info.title,
                full_message,
            )
        elif info.severity == ErrorSeverity.WARNING:
            QMessageBox.warning(
                self._parent_widget,
                info.title,
                full_message,
            )
        elif info.severity == ErrorSeverity.CRITICAL:
            QMessageBox.critical(
                self._parent_widget,
                info.title,
                full_message,
            )
        else:  # ERROR
            QMessageBox.critical(
                self._parent_widget,
                info.title,
                full_message,
            )

    def confirm_action(
        self,
        title: str,
        message: str,
        details: str = "",
    ) -> bool:
        """Show a confirmation dialog and return True if confirmed."""
        full_message = message
        if details:
            full_message += f"\n\n{details}"

        result = QMessageBox.question(
            self._parent_widget,
            title,
            full_message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return result == QMessageBox.StandardButton.Yes
