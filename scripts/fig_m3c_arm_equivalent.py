#!/usr/bin/env python3
"""Figure: M3C brute gate-level model vs. the arm-equivalent (what pulsim L3,
Simulink "Switching-function" and PLECS actually do).

Renders ``docs/imgs/m3c_arm_equivalent.png``: a side-by-side of the infeasible
gate-level MNA model (9 branches × 6 full-bridge submodules = 216 switches in
one matrix) against the arm Thévenin-equivalent that collapses each branch's
submodule chain into a single two-terminal element (Gnanarathna-Gole, IEEE
TPWRD 2011) — keeping the individual capacitor voltages trackable for the
sort-and-select balancer. This is the family pulsim's behavioural L3 belongs to.

Run::  python3 scripts/fig_m3c_arm_equivalent.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import (  # noqa: E402
    Circle, FancyArrowPatch, FancyBboxPatch)

OUT = Path(__file__).resolve().parent.parent / "docs" / "imgs" / "m3c_arm_equivalent.png"

RED, GREEN, BLUE = "#c0392b", "#1e8449", "#21618c"
REDF, GREENF, GREYF = "#fdedec", "#eafaf1", "#f4f6f7"

fig, ax = plt.subplots(figsize=(16.0, 10.2))
ax.set_xlim(0, 100)
ax.set_ylim(0, 100)
ax.axis("off")


def box(x, y, w, h, fc, ec, lw: float = 1.4, r: float = 0.02, z: int = 2):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=f"round,pad=0.0,rounding_size={r * 100}",
        linewidth=lw, edgecolor=ec, facecolor=fc, zorder=z))


def txt(x, y, s, size: float = 10.0, color="#1b2631", weight="normal",
        ha="center", va="center", z: int = 5, rot: float = 0.0):
    ax.text(x, y, s, fontsize=size, color=color, ha=ha, va=va, weight=weight,
            zorder=z, rotation=rot)


def arrow(x0, y0, x1, y1, color="#5d6d7e", lw: float = 2.2, z: int = 3,
          ms: float = 18.0):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>",
                 mutation_scale=ms, color=color, lw=lw, zorder=z))


def circle(x, y, rad, ec, lw: float = 1.3):
    ax.add_patch(Circle((x, y), rad, fill=False, ec=ec, lw=lw, zorder=4))


# ── Title ──────────────────────────────────────────────────────────────────
txt(50, 97.3, "M3C: modelo chaveado BRUTO  vs.  EQUIVALENTE DE BRAÇO",
    size=18, weight="bold")
txt(50, 93.7, "o atalho que pulsim L3, Simulink (Switching-function) e PLECS usam"
    " — ninguém stampa 216 chaves numa matriz só", size=11, color="#566573")

ROWS, COLS = ["A", "B", "C"], ["a", "b", "c"]
gy0, cw, ch, gap = 52.0, 11.3, 9.3, 1.1

# ════════════════════════ LEFT: brute gate-level ══════════════════════════
box(2.5, 33, 41, 56, REDF, RED, lw=2.0, r=0.015, z=1)
box(2.5, 84, 41, 5.2, RED, RED, r=0.015, z=2)
txt(23, 86.6, "✗  GATE-LEVEL BRUTO  (add_switch → MNA)", size=12.5,
    color="white", weight="bold")

gx0 = 6.0
for i, R in enumerate(ROWS):
    for j, C in enumerate(COLS):
        bx, by = gx0 + j * (cw + gap), gy0 - i * (ch + gap)
        box(bx, by, cw, ch, "white", "#cd6155", lw=1.1, r=0.012)
        for k in range(3):
            sy = by + ch - 2.6 - k * 2.0
            box(bx + 1.0, sy, cw - 2.0, 1.5, "#fad7d3", "#cd6155", lw=0.5, r=0.0)
            for s in range(4):
                ax.plot([bx + 1.8 + s * 2.1], [sy + 0.75], marker="s",
                        ms=2.0, color=RED, zorder=4)
        txt(bx + cw / 2, by + 1.3, f"M_{R}{C} · 6 SM = 24 ch", size=6.8,
            color="#922b21")
txt(gx0 - 1.9, gy0 - 5.0, "entrada A,B,C", size=8, color="#922b21",
    weight="bold", rot=90)
for i, R in enumerate(ROWS):
    txt(gx0 - 0.6, gy0 - i * (ch + gap) + ch / 2, R, size=9, color="#922b21",
        weight="bold")
for j, C in enumerate(COLS):
    txt(gx0 + j * (cw + gap) + cw / 2, gy0 + ch + 1.1, C, size=9,
        color="#922b21", weight="bold")
txt(23, gy0 + ch + 3.0, "saída a,b,c →", size=8, color="#922b21", weight="bold")

box(6.0, 35.0, 34.5, 9.5, "white", RED, lw=1.6, r=0.02)
txt(23.2, 41.6, "MATRIZ MNA GIGANTE — 216 chaves", size=10.5, color=RED,
    weight="bold")
txt(23.2, 38.6, "re-fatoriza LU a cada evento de chaveamento\n"
    "até 2²¹⁶ topologias  ·  tempo: horas–dias  ·  INVIÁVEL",
    size=8.6, color="#922b21")

# ════════════════════════ MIDDLE: collapse arrow ══════════════════════════
arrow(44.0, 61.0, 56.0, 61.0, color="#7d3c98", lw=3.2, ms=28)
txt(50, 67.2, "COLAPSO\nDE BRAÇO", size=11, color="#7d3c98", weight="bold")
txt(50, 56.0, "Gnanarathna–Gole\nIEEE TPWRD 2011", size=7.6, color="#7d3c98")

# ════════════════════════ RIGHT: arm equivalent ═══════════════════════════
box(56.5, 33, 41, 56, GREENF, GREEN, lw=2.0, r=0.015, z=1)
box(56.5, 84, 41, 5.2, GREEN, GREEN, r=0.015, z=2)
txt(77, 86.6, "✓  EQUIVALENTE  (pulsim L3 · Simulink SF · PLECS)", size=12,
    color="white", weight="bold")

gx1 = 60.0
for i, R in enumerate(ROWS):
    for j, C in enumerate(COLS):
        bx, by = gx1 + j * (cw + gap), gy0 - i * (ch + gap)
        box(bx, by, cw, ch, "white", "#52be80", lw=1.1, r=0.012)
        cyc = by + ch - 3.0
        circle(bx + cw / 2, cyc, 1.7, GREEN)
        txt(bx + cw / 2, cyc, "V_eq", size=6.0, color="#196f3d")
        ax.plot([bx + cw / 2, bx + cw / 2], [cyc - 1.7, by + 3.2], color=GREEN,
                lw=1.2, zorder=4)
        box(bx + cw / 2 - 2.2, by + 2.0, 4.4, 1.4, "white", GREEN, lw=1.0, r=0.0)
        txt(bx + cw / 2, by + 2.7, "R_eq", size=5.8, color="#196f3d")
        txt(bx + cw / 2, by + 0.7, f"M_{R}{C}", size=6.0, color="#196f3d")

box(60.0, 35.0, 34.5, 9.5, "white", GREEN, lw=1.6, r=0.02)
txt(77.2, 41.6, "matriz pequena (9 ramos) — FIXA", size=10.5, color=GREEN,
    weight="bold")
txt(77.2, 38.6, "fatoriza 1× ; só o vetor de histórico atualiza/passo\n"
    "tempo: < 1 s   ·   ≈ 278× mais rápido (sem perder acurácia)",
    size=8.6, color="#196f3d")

# ════════════════════════ BOTTOM: per-branch collapse ═════════════════════
box(2.5, 4.0, 95.0, 25.0, GREYF, "#aeb6bf", lw=1.4, r=0.01, z=1)
txt(50, 26.6, "Como UM braço (6 submódulos full-bridge) vira UM elemento:",
    size=11.5, weight="bold", color="#2c3e50")

box(5.5, 9.0, 20.0, 13.5, "white", "#cd6155", lw=1.3, r=0.02)
txt(15.5, 20.8, "6 submódulos reais", size=9, weight="bold", color="#922b21")
for k in range(6):
    sy = 18.6 - k * 1.55
    box(7.0, sy, 17.0, 1.15, "#fad7d3", "#cd6155", lw=0.5)
    for s in range(4):
        ax.plot([8.4 + s * 3.9], [sy + 0.57], marker="s", ms=2.4, color=RED)
    ax.plot([23.0], [sy + 0.57], marker="o", ms=2.4, color="#7d3c98")
txt(15.5, 7.5, "24 chaves + 6 caps", size=7.8, color="#922b21")

arrow(26.2, 15.5, 33.5, 15.5, color="#566573", lw=2.0)
txt(29.8, 18.0, "modelo\ncompanheiro\n(trapezoidal)", size=7.0, color="#566573")

box(34.5, 9.0, 21.0, 13.5, "white", BLUE, lw=1.3, r=0.02)
txt(45.0, 20.8, "cada SM → Thévenin", size=9, weight="bold", color="#1a5276")
for k in range(6):
    sy = 18.4 - k * 1.55
    circle(39.0, sy + 0.55, 0.62, BLUE, lw=1.0)
    box(42.0, sy, 4.0, 1.1, "white", BLUE, lw=0.8)
    ax.plot([40.0, 42.0], [sy + 0.55, sy + 0.55], color=BLUE, lw=0.8)
    txt(50.5, sy + 0.55, "R_sm + V_sm", size=5.6, color="#1a5276")
txt(45.0, 7.5, "R + fonte de histórico", size=7.8, color="#1a5276")

arrow(56.2, 15.5, 63.5, 15.5, color="#566573", lw=2.0)
txt(59.8, 18.6, "Σ\n(mesma corrente\nde braço)", size=7.0, color="#566573")

box(64.5, 9.0, 14.5, 13.5, "white", GREEN, lw=1.6, r=0.02)
txt(71.7, 20.8, "1 Thévenin", size=9.5, weight="bold", color="#196f3d")
circle(71.7, 16.0, 2.0, GREEN, lw=1.6)
txt(71.7, 16.0, "V_eq", size=7.5, color="#196f3d")
ax.plot([71.7, 71.7], [14.0, 11.6], color=GREEN, lw=1.4)
box(69.7, 10.6, 4.0, 1.5, "white", GREEN, lw=1.2)
txt(71.7, 11.35, "R_eq", size=7, color="#196f3d")
txt(71.7, 7.5, "ΣR_sm  ·  ΣV_sm", size=7.8, color="#196f3d")

arrow(79.2, 15.5, 84.2, 15.5, color="#566573", lw=2.0)

box(84.6, 9.0, 11.6, 13.5, "#fef9e7", "#b7950b", lw=1.3, r=0.02)
txt(90.4, 20.0, "↩ por dentro", size=8.5, weight="bold", color="#9a7d0a")
txt(90.4, 14.8, "as 6 tensões de\ncap continuam\nrastreadas\n(retro-substituição)"
    "\n→ sort-and-select", size=7.2, color="#7d6608")

OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=150, bbox_inches="tight", facecolor="white")
print(f"saved {OUT}")
