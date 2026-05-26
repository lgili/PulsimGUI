"""Math signal evaluation + MathSignalDialog.

Split out of ``scope_window.py`` so the (large) scope-window module no
longer carries the math-expression parser, unit inference, and dialog
implementation. The dialog lets the user combine two signals (and the
time vector) with a small whitelisted formula language; the evaluator
runs the formula and emits a derived trace.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.services.theme_service import Theme


_MATH_BINARY_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: lambda left, right: left + right,  # type: ignore[operator]
    ast.Sub: lambda left, right: left - right,  # type: ignore[operator]
    ast.Mult: lambda left, right: left * right,  # type: ignore[operator]
    ast.Div: lambda left, right: left / right,  # type: ignore[operator]
    ast.Pow: lambda left, right: left ** right,  # type: ignore[operator]
}
_MATH_UNARY_OPS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.UAdd: lambda value: value,
    ast.USub: lambda value: -value,  # type: ignore[operator]
}
_MATH_ALLOWED_NAMES = frozenset({"A", "B", "t"})
_MATH_ALLOWED_CALLS = frozenset({"abs", "sqrt", "square", "derivative", "integral", "moving_avg", "avg"})


def _math_moving_average(values: Any, window: Any) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    kernel_size = int(round(float(window)))
    if kernel_size < 2:
        raise ValueError("moving_avg window must be at least 2 samples")
    kernel_size = min(kernel_size, len(array))
    kernel = np.ones(kernel_size, dtype=float) / float(kernel_size)
    return np.convolve(array, kernel, mode="same")


def _math_validate_ast(node: ast.AST) -> None:
    if isinstance(node, ast.Expression):
        _math_validate_ast(node.body)
        return
    if isinstance(node, ast.BinOp):
        if type(node.op) not in _MATH_BINARY_OPS:
            raise ValueError("Unsupported binary operator")
        _math_validate_ast(node.left)
        _math_validate_ast(node.right)
        return
    if isinstance(node, ast.UnaryOp):
        if type(node.op) not in _MATH_UNARY_OPS:
            raise ValueError("Unsupported unary operator")
        _math_validate_ast(node.operand)
        return
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _MATH_ALLOWED_CALLS:
            raise ValueError("Unsupported function call")
        for arg in node.args:
            _math_validate_ast(arg)
        return
    if isinstance(node, ast.Name):
        if node.id not in _MATH_ALLOWED_NAMES:
            raise ValueError(f"Unknown symbol '{node.id}'")
        return
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise ValueError("Only numeric constants are supported")
        return
    raise ValueError("Unsupported expression syntax")


def _math_eval_ast(node: ast.AST, env: Mapping[str, Any], time: np.ndarray) -> Any:
    if isinstance(node, ast.Expression):
        return _math_eval_ast(node.body, env, time)
    if isinstance(node, ast.BinOp):
        left = _math_eval_ast(node.left, env, time)
        right = _math_eval_ast(node.right, env, time)
        return _MATH_BINARY_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp):
        operand = _math_eval_ast(node.operand, env, time)
        return _MATH_UNARY_OPS[type(node.op)](operand)
    if isinstance(node, ast.Name):
        return env[node.id]
    if isinstance(node, ast.Constant):
        val = node.value
        if not isinstance(val, (int, float)):
            raise ValueError("Only numeric constants are supported")
        return float(val)
    if isinstance(node, ast.Call):
        func_name = node.func.id if isinstance(node.func, ast.Name) else ""
        args: list[Any] = [_math_eval_ast(arg, env, time) for arg in node.args]
        if func_name == "abs":
            return np.abs(args[0])
        if func_name == "sqrt":
            return np.sqrt(np.maximum(np.asarray(args[0], dtype=float), 0.0))
        if func_name == "square":
            return np.square(args[0])
        if func_name == "derivative":
            return np.gradient(np.asarray(args[0], dtype=float), time)
        if func_name == "integral":
            dt = np.diff(time, prepend=time[0])
            return np.cumsum(np.asarray(args[0], dtype=float) * dt)
        if func_name in {"moving_avg", "avg"}:
            return _math_moving_average(args[0], args[1])
    raise ValueError("Unsupported expression syntax")


def evaluate_math_expression(formula: str, env: Mapping[str, Any], time: np.ndarray) -> np.ndarray:
    """Evaluate a whitelisted scope-math expression against ``env`` + ``time``."""
    expression = str(formula or "").strip()
    if not expression:
        raise ValueError("Expression cannot be empty")
    parsed = ast.parse(expression, mode="eval")
    _math_validate_ast(parsed)
    result = _math_eval_ast(parsed, env, time)
    array = np.asarray(result, dtype=float)
    if array.ndim == 0:
        return np.full_like(time, float(array), dtype=float)
    if len(array) != len(time):
        raise ValueError("Expression must return one value per sample")
    return array


def _combine_math_units(left: str, right: str, operator_name: str) -> str:
    left_unit = str(left or "").strip()
    right_unit = str(right or "").strip()
    if operator_name in {"add", "sub"}:
        if left_unit == right_unit:
            return left_unit
        if not left_unit:
            return right_unit
        if not right_unit:
            return left_unit
        return "mixed"
    if operator_name == "mul":
        if not left_unit:
            return right_unit
        if not right_unit:
            return left_unit
        return f"{left_unit}*{right_unit}"
    if operator_name == "div":
        if left_unit == right_unit:
            return ""
        if not right_unit:
            return left_unit
        if not left_unit:
            return f"1/{right_unit}"
        return f"{left_unit}/{right_unit}"
    if operator_name == "pow":
        if not left_unit:
            return ""
        return f"{left_unit}^{right_unit or 'n'}"
    return left_unit


def _infer_math_unit(node: ast.AST, env_units: dict[str, str]) -> str:
    if isinstance(node, ast.Expression):
        return _infer_math_unit(node.body, env_units)
    if isinstance(node, ast.Name):
        return str(env_units.get(node.id, "") or "")
    if isinstance(node, ast.Constant):
        return ""
    if isinstance(node, ast.UnaryOp):
        return _infer_math_unit(node.operand, env_units)
    if isinstance(node, ast.BinOp):
        left_unit = _infer_math_unit(node.left, env_units)
        right_unit = _infer_math_unit(node.right, env_units)
        if isinstance(node.op, ast.Add):
            return _combine_math_units(left_unit, right_unit, "add")
        if isinstance(node.op, ast.Sub):
            return _combine_math_units(left_unit, right_unit, "sub")
        if isinstance(node.op, ast.Mult):
            return _combine_math_units(left_unit, right_unit, "mul")
        if isinstance(node.op, ast.Div):
            return _combine_math_units(left_unit, right_unit, "div")
        if isinstance(node.op, ast.Pow):
            return _combine_math_units(left_unit, right_unit, "pow")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        func_name = node.func.id
        base_unit = _infer_math_unit(node.args[0], env_units) if node.args else ""
        if func_name in {"abs", "moving_avg", "avg"}:
            return base_unit
        if func_name == "square":
            return f"{base_unit}^2" if base_unit else ""
        if func_name == "sqrt":
            return f"sqrt({base_unit})" if base_unit else ""
        if func_name == "derivative":
            return f"{base_unit}/s" if base_unit else "1/s"
        if func_name == "integral":
            return f"{base_unit}*s" if base_unit else "s"
    return ""


def infer_math_expression_unit(formula: str, env_units: dict[str, str]) -> str:
    """Best-effort unit inference for a scope-math expression."""
    expression = str(formula or "").strip()
    if not expression:
        return ""
    parsed = ast.parse(expression, mode="eval")
    _math_validate_ast(parsed)
    return _infer_math_unit(parsed, env_units)


class MathSignalDialog(QDialog):
    """Dialog that encapsulates math signal interactions."""
    def __init__(
        self,
        parent: QWidget,
        signal_data: dict[str, np.ndarray],
        signal_units: dict[str, str],
        time_values: np.ndarray,
        default_signal: str,
        theme: Theme | None,
        scope_theme: dict[str, str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Math Signal")
        self.setModal(True)
        self.setMinimumWidth(560)
        self._signal_names = list(signal_data.keys())
        self._signal_data = {name: np.asarray(values, dtype=float) for name, values in signal_data.items()}
        self._signal_units = {str(name): str(unit or "") for name, unit in signal_units.items()}
        self._time_values = np.asarray(time_values, dtype=float)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Math Signal")
        title.setObjectName("mathSignalDialogTitle")
        subtitle = QLabel("Create derived traces with an explicit formula and live validation.")
        subtitle.setObjectName("mathSignalDialogSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        inputs_section = QLabel("Inputs")
        inputs_section.setObjectName("mathSignalSection")
        layout.addWidget(inputs_section)
        inputs_form = QFormLayout()
        inputs_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        inputs_form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        inputs_form.setHorizontalSpacing(10)
        inputs_form.setVerticalSpacing(8)
        self._source_a_combo = QComboBox()
        self._source_a_combo.addItems(self._signal_names)
        idx = self._source_a_combo.findText(default_signal)
        if idx >= 0:
            self._source_a_combo.setCurrentIndex(idx)
        inputs_form.addRow("Signal A", self._source_a_combo)

        self._source_b_combo = QComboBox()
        self._source_b_combo.addItems(self._signal_names)
        if idx >= 0:
            self._source_b_combo.setCurrentIndex(idx)
        inputs_form.addRow("Signal B", self._source_b_combo)

        self._swap_sources_btn = QPushButton("Swap A ↔ B")
        self._swap_sources_btn.setObjectName("mathSignalSwapBtn")
        self._swap_sources_btn.clicked.connect(self._on_swap_sources_clicked)
        inputs_form.addRow("", self._swap_sources_btn)
        layout.addLayout(inputs_form)

        formula_section = QLabel("Formula")
        formula_section.setObjectName("mathSignalSection")
        layout.addWidget(formula_section)
        self._formula_edit = QLineEdit("A")
        self._formula_edit.setPlaceholderText("Examples: A + B, abs(A), moving_avg(A, 16), derivative(A)")
        layout.addWidget(self._formula_edit)
        self._formula_help = QLabel(
            "Use variables A, B and t. Supported functions: abs(), sqrt(), square(), derivative(), integral(), moving_avg()."
        )
        self._formula_help.setObjectName("mathSignalDialogSubtitle")
        self._formula_help.setWordWrap(True)
        layout.addWidget(self._formula_help)

        output_section = QLabel("Output")
        output_section.setObjectName("mathSignalSection")
        layout.addWidget(output_section)
        output_form = QFormLayout()
        output_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        output_form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        output_form.setHorizontalSpacing(10)
        output_form.setVerticalSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Auto")
        output_form.addRow("Result Name", self._name_edit)
        self._unit_preview_label = QLabel("Result Unit: —")
        self._unit_preview_label.setObjectName("mathSignalDialogSubtitle")
        output_form.addRow("Unit Preview", self._unit_preview_label)
        self._auto_plot_check = QCheckBox("Add to plot immediately")
        self._auto_plot_check.setChecked(True)
        output_form.addRow("Behavior", self._auto_plot_check)

        self._preview_label = QLabel("Preview: --")
        self._preview_label.setObjectName("mathSignalPreview")

        layout.addLayout(output_form)
        layout.addWidget(self._preview_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self._create_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if self._create_button is not None:
            self._create_button.setText("Create")
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._source_a_combo.currentIndexChanged.connect(self._update_state)
        self._source_b_combo.currentIndexChanged.connect(self._update_state)
        self._formula_edit.textChanged.connect(self._update_state)
        self._name_edit.textChanged.connect(self._update_state)

        if theme is not None:
            c = theme.colors
            shell = scope_theme or {
                "panel_bg": c.panel_background,
                "border": c.panel_border,
                "text": c.foreground,
                "muted": c.foreground_muted,
                "field_bg": c.input_background,
                "field_border": c.input_border,
                "focus": c.input_focus_border,
                "button_bg": c.secondary,
                "button_hover_bg": c.secondary_hover,
                "button_text": c.secondary_foreground,
                "accent": c.primary,
                "accent_fg": c.primary_foreground,
                "menu_bg": c.menu_background,
                "menu_text": c.foreground,
                "menu_border": c.panel_border,
                "menu_hover_bg": c.menu_hover,
            }
            self.setStyleSheet(f"""
                QDialog {{
                    background-color: {shell["panel_bg"]};
                    border: 1px solid {shell["border"]};
                    border-radius: 12px;
                }}
                QLabel#mathSignalDialogTitle {{
                    font-size: 18px;
                    font-weight: 700;
                    color: {shell["text"]};
                }}
                QLabel#mathSignalDialogSubtitle {{
                    font-size: 12px;
                    color: {shell["muted"]};
                }}
                QLabel#mathSignalSection {{
                    font-size: 11px;
                    font-weight: 700;
                    color: {shell["text"]};
                    margin-top: 4px;
                }}
                QLabel#mathSignalPreview {{
                    font-size: 11px;
                    font-weight: 600;
                    color: {shell["text"]};
                    background-color: {shell["field_bg"]};
                    border: 1px solid {shell["border"]};
                    border-radius: 10px;
                    padding: 7px 10px;
                }}
                QComboBox, QLineEdit {{
                    background-color: {shell["field_bg"]};
                    color: {shell["text"]};
                    border: 1px solid {shell["field_border"]};
                    border-radius: 10px;
                    padding: 5px 9px;
                    min-height: 28px;
                }}
                QComboBox:hover, QLineEdit:hover {{
                    border-color: {shell["focus"]};
                }}
                QComboBox QAbstractItemView {{
                    background-color: {shell["menu_bg"]};
                    color: {shell["menu_text"]};
                    border: 1px solid {shell["menu_border"]};
                    selection-background-color: {shell["menu_hover_bg"]};
                    selection-color: {shell["menu_text"]};
                    outline: none;
                }}
                QCheckBox {{
                    color: {shell["text"]};
                    font-weight: 600;
                }}
                QPushButton {{
                    background-color: {shell["button_bg"]};
                    color: {shell["button_text"]};
                    border: 1px solid {shell["border"]};
                    border-radius: 10px;
                    padding: 6px 12px;
                    min-height: 28px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: {shell["button_hover_bg"]};
                    border-color: {shell["accent"]};
                }}
                QPushButton#mathSignalSwapBtn {{
                    min-width: 108px;
                }}
                QDialogButtonBox QPushButton {{
                    min-width: 94px;
                }}
            """)

        self._update_state()

    def _on_swap_sources_clicked(self) -> None:
        idx_a = self._source_a_combo.currentIndex()
        idx_b = self._source_b_combo.currentIndex()
        self._source_a_combo.setCurrentIndex(idx_b)
        self._source_b_combo.setCurrentIndex(idx_a)
        self._update_state()

    def _update_state(self) -> None:
        source_a = self._source_a_combo.currentText().strip()
        source_b = self._source_b_combo.currentText().strip()
        formula = self._formula_edit.text().strip()
        env = {
            "A": self._signal_data.get(source_a, np.array([], dtype=float)),
            "B": self._signal_data.get(source_b, np.array([], dtype=float)),
            "t": self._time_values,
        }
        env_units = {
            "A": self._signal_units.get(source_a, ""),
            "B": self._signal_units.get(source_b, ""),
            "t": "s",
        }

        valid = False
        preview_text = "Preview: Enter an expression."
        unit_text = "Result Unit: —"
        try:
            result = evaluate_math_expression(formula, env, self._time_values)
            unit = infer_math_expression_unit(formula, env_units)
            valid = True
            min_val = float(np.min(result)) if len(result) else 0.0
            max_val = float(np.max(result)) if len(result) else 0.0
            preview_text = (
                f"Preview: valid expression • {len(result)} samples • "
                f"min {min_val:.4g} • max {max_val:.4g}"
            )
            unit_text = f"Result Unit: {unit or 'unitless'}"
        except Exception as exc:
            preview_text = f"Preview: invalid expression • {exc}"

        self._preview_label.setText(preview_text)
        self._unit_preview_label.setText(unit_text)
        if self._create_button is not None:
            self._create_button.setEnabled(valid)

    def selected_config(self) -> dict[str, object]:
        """Return the currently selected math-signal configuration."""
        source_a = self._source_a_combo.currentText().strip()
        source_b = self._source_b_combo.currentText().strip()
        formula = self._formula_edit.text().strip()
        custom_name = self._name_edit.text().strip()
        env_units = {
            "A": self._signal_units.get(source_a, ""),
            "B": self._signal_units.get(source_b, ""),
            "t": "s",
        }
        return {
            "source_a": source_a,
            "source_b": source_b,
            "formula": formula,
            "custom_name": custom_name,
            "auto_plot": bool(self._auto_plot_check.isChecked()),
            "result_unit": infer_math_expression_unit(formula, env_units),
        }


__all__ = [
    "MathSignalDialog",
    "evaluate_math_expression",
    "infer_math_expression_unit",
]
