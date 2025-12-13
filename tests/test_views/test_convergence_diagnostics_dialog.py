"""Tests for ConvergenceDiagnosticsDialog."""

from __future__ import annotations

import pytest

from pulsimgui.services.backend_types import (
    ConvergenceInfo,
    IterationRecord,
    ProblematicVariable,
)
from pulsimgui.views.dialogs.convergence_diagnostics_dialog import (
    ConvergenceDiagnosticsDialog,
)


@pytest.fixture
def converged_info():
    """Create a converged ConvergenceInfo."""
    return ConvergenceInfo(
        converged=True,
        iterations=15,
        final_residual=1e-10,
        strategy_used="newton",
        history=[
            IterationRecord(i, 1e-3 / (i + 1)) for i in range(15)
        ],
    )


@pytest.fixture
def failed_info():
    """Create a failed ConvergenceInfo."""
    return ConvergenceInfo(
        converged=False,
        iterations=50,
        final_residual=1e-3,
        strategy_used="newton",
        failure_reason="Maximum iterations exceeded",
        history=[
            IterationRecord(i, 1e-3 * (1 + 0.01 * i), damping_factor=0.5)
            for i in range(50)
        ],
        problematic_variables=[
            ProblematicVariable(
                index=0,
                name="V(out)",
                value=5.123,
                change=0.5,
                tolerance=1e-6,
                normalized_error=500000.0,
                is_voltage=True,
            ),
            ProblematicVariable(
                index=1,
                name="I(M1)",
                value=0.001,
                change=1e-4,
                tolerance=1e-9,
                normalized_error=100000.0,
                is_voltage=False,
            ),
        ],
    )


@pytest.fixture
def diverging_info():
    """Create a diverging ConvergenceInfo."""
    return ConvergenceInfo(
        converged=False,
        iterations=10,
        final_residual=1e6,
        strategy_used="newton",
        failure_reason="Residual diverging",
        history=[
            IterationRecord(i, 1e-3 * (2 ** i), step_norm=100 + i * 50)
            for i in range(10)
        ],
    )


@pytest.fixture
def stalling_info():
    """Create a stalling ConvergenceInfo."""
    return ConvergenceInfo(
        converged=False,
        iterations=30,
        final_residual=1e-5,
        strategy_used="gmin_stepping",
        failure_reason="Convergence stalled",
        history=[
            IterationRecord(i, 1e-5 * (1 + 0.001 * (i % 3)))
            for i in range(30)
        ],
    )


@pytest.fixture
def transient_failure_info():
    """Create a transient failure ConvergenceInfo."""
    return ConvergenceInfo(
        converged=False,
        iterations=20,
        final_residual=1e-2,
        strategy_used="newton",
        time_of_failure=1.5e-6,
        failure_reason="Convergence failed at t=1.5us",
        history=[
            IterationRecord(i, 1e-2 * (1 - 0.01 * i))
            for i in range(20)
        ],
    )


class TestConvergenceDiagnosticsDialog:
    """Tests for ConvergenceDiagnosticsDialog initialization."""

    def test_dialog_creates_with_converged_info(self, qtbot, converged_info):
        """Dialog should create successfully with converged info."""
        dialog = ConvergenceDiagnosticsDialog(converged_info)
        qtbot.addWidget(dialog)

        assert dialog.windowTitle() == "Convergence Diagnostics"

    def test_dialog_creates_with_failed_info(self, qtbot, failed_info):
        """Dialog should create successfully with failed info."""
        dialog = ConvergenceDiagnosticsDialog(failed_info)
        qtbot.addWidget(dialog)

        assert dialog.windowTitle() == "Convergence Diagnostics"

    def test_dialog_has_four_tabs(self, qtbot, converged_info):
        """Dialog should have Summary, History, Variables, and Suggestions tabs."""
        dialog = ConvergenceDiagnosticsDialog(converged_info)
        qtbot.addWidget(dialog)

        assert dialog._tabs.count() == 4
        assert dialog._tabs.tabText(0) == "Summary"
        assert dialog._tabs.tabText(1) == "Iteration History"
        assert dialog._tabs.tabText(2) == "Problematic Variables"
        assert dialog._tabs.tabText(3) == "Suggestions"


class TestSuggestionEngine:
    """Tests for the suggestion generation logic."""

    def test_max_iterations_suggestion(self, qtbot, failed_info):
        """Should suggest increasing iterations when max reached."""
        dialog = ConvergenceDiagnosticsDialog(failed_info)
        qtbot.addWidget(dialog)

        suggestions = dialog._generate_suggestions()
        titles = [s["title"] for s in suggestions]

        assert "Increase Maximum Iterations" in titles

    def test_voltage_limiting_suggestion_for_diverging(self, qtbot, diverging_info):
        """Should suggest voltage limiting for diverging solver."""
        dialog = ConvergenceDiagnosticsDialog(diverging_info)
        qtbot.addWidget(dialog)

        suggestions = dialog._generate_suggestions()
        titles = [s["title"] for s in suggestions]

        assert "Enable Voltage Limiting" in titles
        assert "Try GMIN Stepping" in titles

    def test_source_stepping_suggestion_for_stalling(self, qtbot, stalling_info):
        """Should suggest source stepping for stalling solver."""
        dialog = ConvergenceDiagnosticsDialog(stalling_info)
        qtbot.addWidget(dialog)

        suggestions = dialog._generate_suggestions()
        titles = [s["title"] for s in suggestions]

        assert "Try Source Stepping" in titles

    def test_floating_nodes_suggestion(self, qtbot, failed_info):
        """Should suggest checking floating nodes when voltage issues."""
        dialog = ConvergenceDiagnosticsDialog(failed_info)
        qtbot.addWidget(dialog)

        suggestions = dialog._generate_suggestions()
        titles = [s["title"] for s in suggestions]

        assert "Check Floating Nodes" in titles

    def test_large_step_suggestion(self, qtbot, diverging_info):
        """Should suggest reducing step size when large steps detected."""
        dialog = ConvergenceDiagnosticsDialog(diverging_info)
        qtbot.addWidget(dialog)

        suggestions = dialog._generate_suggestions()
        titles = [s["title"] for s in suggestions]

        assert "Reduce Maximum Voltage Step" in titles

    def test_pseudo_transient_suggestion(self, qtbot, transient_failure_info):
        """Should suggest pseudo-transient for transient failures."""
        dialog = ConvergenceDiagnosticsDialog(transient_failure_info)
        qtbot.addWidget(dialog)

        suggestions = dialog._generate_suggestions()
        titles = [s["title"] for s in suggestions]

        assert "Use Pseudo-Transient" in titles

    def test_converged_has_general_suggestion(self, qtbot, converged_info):
        """Converged simulation should have general review suggestion."""
        dialog = ConvergenceDiagnosticsDialog(converged_info)
        qtbot.addWidget(dialog)

        suggestions = dialog._generate_suggestions()

        # Should have at least one suggestion (the fallback)
        assert len(suggestions) >= 1


class TestHistoryPopulation:
    """Tests for iteration history display."""

    def test_history_table_populated(self, qtbot, failed_info):
        """History table should be populated with iteration records."""
        dialog = ConvergenceDiagnosticsDialog(failed_info)
        qtbot.addWidget(dialog)

        assert dialog._history_table.rowCount() == len(failed_info.history)

    def test_empty_history_shows_message(self, qtbot):
        """Empty history should show informative message."""
        info = ConvergenceInfo(converged=True, iterations=1)
        dialog = ConvergenceDiagnosticsDialog(info)
        qtbot.addWidget(dialog)

        # Should not crash and should show placeholder


class TestVariablesPopulation:
    """Tests for problematic variables display."""

    def test_variables_table_populated(self, qtbot, failed_info):
        """Variables table should be populated and sorted by error."""
        dialog = ConvergenceDiagnosticsDialog(failed_info)
        qtbot.addWidget(dialog)

        assert dialog._variables_table.rowCount() == len(failed_info.problematic_variables)

        # First row should have highest error (V(out) with 500000x)
        first_name = dialog._variables_table.item(0, 0).text()
        assert first_name == "V(out)"

    def test_empty_variables_shows_message(self, qtbot, converged_info):
        """Empty problematic variables should show informative message."""
        dialog = ConvergenceDiagnosticsDialog(converged_info)
        qtbot.addWidget(dialog)

        # Should not crash


class TestSuggestionsFormatting:
    """Tests for suggestions HTML formatting."""

    def test_suggestions_html_format(self, qtbot, failed_info):
        """Suggestions should format correctly as HTML."""
        dialog = ConvergenceDiagnosticsDialog(failed_info)
        qtbot.addWidget(dialog)

        suggestions = dialog._generate_suggestions()
        html = dialog._format_suggestions_html(suggestions)

        assert "<style>" in html
        assert "suggestion-title" in html
        assert "suggestion-desc" in html
        assert "suggestion-action" in html
