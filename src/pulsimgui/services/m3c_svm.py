"""Thesis-faithful Space-Vector Modulation for the M3C (L. C. Gili, UFSC 2024).

This implements the *modulation* half of the thesis control (Etapas 3-4 of the
six-stage scheme, Fig. 64) so it can drive the GUI's behavioural L3 arms:

* **Etapa 3 — Fast SVM in the non-orthogonal lgγ plane** (Celanovic's fast SVM,
  extended by the thesis to keep the common-mode γ axis). The reference is taken
  into the skewed integer ``lg`` frame where every realisable converter vector
  lands on an integer lattice point, so the three nearest vectors are found by
  plain floor/ceil — no sector search, no trig (Eqs. 25-30, 35-36).

* **Connection model** — the M3C is a 3×3 matrix of nine modules ``M_Xy``
  (X∈ABC input phase, y∈abc output phase). Erickson's continuity rules make
  exactly five modules conduct at once, forming a *spanning tree* of the
  complete bipartite graph K₃,₃ between the three input and three output phase
  nodes. K₃,₃ has exactly 3²·3² = **81** spanning trees — the thesis's 81 valid
  connections. The Etapa-3 reduction (tie the smallest input phase directly to
  the smallest output phase) fixes one edge, collapsing the set to **45**.

* **Etapa 4 — predictive cost-function balancing**. For each surviving
  connection the per-module current ``I_xy`` (from the measured terminal
  currents through that tree) predicts the cap-voltage change
  ``ΔV_xy = Sn·I_xy·Ts/C`` (Eq. 162). The connection minimising
  ``J = Σ_xy (ε_xy + ΔV_xy)²`` (Eq. 163, with ``ε_xy = V_xy − mean(V_xy)``,
  Eq. 161) is applied for the switching period.

Pure Python / standard library only, so it unit-tests in isolation (no pulsim,
no Qt). The thesis's own real-time reference code is at
github.com/lgili/Arquivos_Publicos_Tese.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import combinations

# Phase node labels. Input nodes 0..2 = A,B,C ; output nodes 0..2 = a,b,c.
IN_PHASES = ("A", "B", "C")
OUT_PHASES = ("a", "b", "c")
# The nine modules in (X, y) row-major order: M_Aa, M_Ab, ... M_Cc.
MODULES = tuple(f"M_{X}{y}" for X in IN_PHASES for y in OUT_PHASES)


# ---------------------------------------------------------------------------
# Non-orthogonal lgγ transform (Eqs. 25 / 37)
# ---------------------------------------------------------------------------
def lg_from_abc(va: float, vb: float, vc: float) -> tuple[float, float, float]:
    """Phase voltages → non-orthogonal ``(Vl, Vg, Vγ)`` (Eq. 25).

    ``Vl = va−vb`` and ``Vg = vb−vc`` are the two skewed (60°) line-voltage
    axes on which the integer lattice lives; ``Vγ = va+vb+vc`` carries the
    common mode the orthogonal αβ frame discards.
    """
    return (va - vb, vb - vc, va + vb + vc)


def abc_from_lg(vl: float, vg: float, vgamma: float) -> tuple[float, float, float]:
    """Inverse of :func:`lg_from_abc` (Eq. 37, exact normalisation).

    ``va = (Vγ + 2Vl + Vg)/3``, ``vb = (Vγ − Vl + Vg)/3``,
    ``vc = (Vγ − Vl − 2Vg)/3``.
    """
    va = (vgamma + 2.0 * vl + vg) / 3.0
    vb = (vgamma - vl + vg) / 3.0
    vc = (vgamma - vl - 2.0 * vg) / 3.0
    return (va, vb, vc)


# ---------------------------------------------------------------------------
# Fast SVM in one plane (Etapa 3 core; Eqs. 26-30, 35-36)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SvmPlane:
    """Result of the fast SVM on one (input or output) plane.

    ``vectors`` are the three nearest integer lattice vectors ``(l, g)`` and
    ``duties`` their per-period dwell fractions (≥0, summing to 1). The
    duty-weighted vector sum reconstructs the reference ``(vl_ref, vg_ref)``.
    """

    vectors: tuple[tuple[int, int], tuple[int, int], tuple[int, int]]
    duties: tuple[float, float, float]
    vl_ref: float
    vg_ref: float

    def average(self) -> tuple[float, float]:
        """Duty-weighted ``(l, g)`` — equals the reference up to float error."""
        l = sum(d * v[0] for d, v in zip(self.duties, self.vectors))
        g = sum(d * v[1] for d, v in zip(self.duties, self.vectors))
        return (l, g)


def fast_svm_plane(vl_ref: float, vg_ref: float) -> SvmPlane:
    """Fast (non-orthogonal) SVM: three nearest lattice vectors + duties.

    The four candidate integer neighbours are the floor/ceil combinations of
    the ``lg`` projections (Eq. 26). ``V_ul`` (ceil l, floor g) and ``V_lu``
    (floor l, ceil g) — the two diagonal neighbours — are always used; the
    third is the lower (``V_ll``) or upper (``V_uu``) corner depending on which
    sub-triangle the reference falls in. Duties follow Eq. 35/36; here written
    via the fractional parts so the duty-weighted sum provably reconstructs the
    reference and every duty is in [0, 1].
    """
    fl_l = math.floor(vl_ref)
    fl_g = math.floor(vg_ref)
    frac_l = vl_ref - fl_l
    frac_g = vg_ref - fl_g

    v_ul = (fl_l + 1, fl_g)      # ceil(l), floor(g) — lower-right diagonal
    v_lu = (fl_l, fl_g + 1)      # floor(l), ceil(g) — upper-left diagonal

    if frac_l + frac_g <= 1.0:
        # Lower triangle → third vector is V_ll = (floor l, floor g).
        v_third = (fl_l, fl_g)
        d_ul = frac_l
        d_lu = frac_g
        d_third = 1.0 - frac_l - frac_g
    else:
        # Upper triangle → third vector is V_uu = (ceil l, ceil g).
        v_third = (fl_l + 1, fl_g + 1)
        d_ul = 1.0 - frac_g
        d_lu = 1.0 - frac_l
        d_third = frac_l + frac_g - 1.0

    return SvmPlane(
        vectors=(v_ul, v_lu, v_third),
        duties=(d_ul, d_lu, d_third),
        vl_ref=vl_ref,
        vg_ref=vg_ref,
    )


# ---------------------------------------------------------------------------
# Connection model — the 81 spanning trees of K₃,₃ (Erickson's 5-conducting rule)
# ---------------------------------------------------------------------------
def _is_spanning_tree(edges: tuple[tuple[int, int], ...]) -> bool:
    """Do these 5 module-edges connect all six phase nodes acyclically?

    Each edge is ``(i, j)`` with input node ``i`` (0..2) and output node ``j``
    (0..2). A connected, acyclic 5-edge graph over the 6 nodes (3 input + 3
    output) is a spanning tree — exactly the M3C's valid 5-conducting set.
    """
    # Union-find over 6 nodes: inputs 0..2, outputs 3..5.
    parent = list(range(6))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, j in edges:
        ri, rj = find(i), find(3 + j)
        if ri == rj:
            return False           # cycle ⇒ not a tree
        parent[ri] = rj
    # 5 acyclic edges over 6 nodes with no cycle ⇒ all connected ⇒ spanning.
    return True


def enumerate_connections() -> list[tuple[tuple[int, int], ...]]:
    """All 81 valid 5-module connections = spanning trees of K₃,₃.

    Returns each as a sorted 5-tuple of ``(input_node, output_node)`` edges.
    """
    all_edges = [(i, j) for i in range(3) for j in range(3)]
    trees = [combo for combo in combinations(all_edges, 5)
             if _is_spanning_tree(combo)]
    return trees


def module_index(i: int, j: int) -> int:
    """Row-major flat index of module ``M_(IN[i])(OUT[j])`` in :data:`MODULES`."""
    return 3 * i + j


# ---------------------------------------------------------------------------
# Per-connection meshes: module voltages (KVL) and currents (KCL)
# ---------------------------------------------------------------------------
def module_voltages(
    v_in: tuple[float, float, float],
    v_out: tuple[float, float, float],
    short_edge: tuple[int, int],
) -> list[float]:
    """Per-module synthesised voltage ``V_Xy = pot_in[X] − pot_out[y]``.

    Each side's phase voltages fix the *relative* node potentials within that
    side; the ``short_edge`` (smallest-input tied to smallest-output, the
    Etapa-3 reduction) pins the input↔output common-mode offset by forcing that
    module to 0 V. The result is therefore **connection-independent** — every
    spanning tree consistent with the imposed line voltages yields the same
    module voltages. (Only the module *currents* depend on the tree, which is
    exactly why the Etapa-4 cost function differentiates candidates solely
    through the ΔV current term, with ε_xy constant across the period.)

    Returns a length-9 list in :data:`MODULES` (row-major) order.
    """
    si, sj = short_edge
    offset = v_in[si] - v_out[sj]
    return [v_in[i] - (v_out[j] + offset)
            for i in range(3) for j in range(3)]


def tree_module_currents(
    edges: tuple[tuple[int, int], ...],
    i_in: tuple[float, float, float],
    i_out: tuple[float, float, float],
) -> dict[tuple[int, int], float]:
    """Per-module current for a spanning-tree connection (KCL through the tree).

    Removing a tree edge splits the six nodes into two components; the current
    in that edge is the net terminal current injected on one side of the cut.
    Input phase ``i`` injects ``i_in[i]``; output phase ``j`` draws ``i_out[j]``
    (modelled as an injection of ``−i_out[j]`` at the output node). Returns the
    signed current of each conducting module (positive = input→output).
    """
    inj = [i_in[0], i_in[1], i_in[2], -i_out[0], -i_out[1], -i_out[2]]
    adj: dict[int, list[tuple[int, tuple[int, int]]]] = {n: [] for n in range(6)}
    for (i, j) in edges:
        node_out = 3 + j
        adj[i].append((node_out, (i, j)))
        adj[node_out].append((i, (i, j)))

    currents: dict[tuple[int, int], float] = {}

    def dfs(node: int, parent: int, parent_edge: tuple[int, int] | None) -> float:
        """Net injection of the subtree rooted at ``node`` (parent excluded).

        By KCL that net injection is exactly the current leaving the subtree
        through the single edge to the parent, so we can label that edge."""
        total = inj[node]
        for nb, edge in adj[node]:
            if nb == parent:
                continue
            total += dfs(nb, node, edge)
        if parent_edge is not None:
            _, j = parent_edge
            # Positive convention = input→output. The current from this node's
            # subtree toward the parent equals ``total``.
            if node == 3 + j:        # this node is the output side of the edge
                currents[parent_edge] = -total
            else:                    # this node is the input side
                currents[parent_edge] = total
        return total

    dfs(0, -1, None)
    return currents


# ---------------------------------------------------------------------------
# Etapa 4 — predictive cost function over the 45 surviving connections
# ---------------------------------------------------------------------------
@dataclass
class CostSelector:
    """Selects, each switching period, the connection minimising the thesis
    cost function ``J = Σ_xy (ε_xy + ΔV_xy)²`` (Eqs. 161-163)."""

    sn: float = 1.0           # number of active capacitors Sn (charge scaling)
    capacitance: float = 680e-6
    ts: float = 0.5e-3        # switching period (1 / f_switch)
    _connections: list[tuple[tuple[int, int], ...]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self._connections:
            self._connections = enumerate_connections()

    def reduced_set(
        self, v_in: tuple[float, float, float], v_out: tuple[float, float, float]
    ) -> tuple[tuple[int, int], list[tuple[tuple[int, int], ...]]]:
        """81→45 reduction: force the smallest input phase tied to the smallest
        output phase (Etapa 3) and keep only connections containing that edge.
        Returns ``(short_edge, candidates)``."""
        si = min(range(3), key=lambda i: v_in[i])
        sj = min(range(3), key=lambda j: v_out[j])
        short = (si, sj)
        candidates = [e for e in self._connections if short in e]
        return short, candidates

    def select(
        self,
        v_in: tuple[float, float, float],
        v_out: tuple[float, float, float],
        i_in: tuple[float, float, float],
        i_out: tuple[float, float, float],
        v_module: list[float],
    ) -> tuple[tuple[tuple[int, int], ...], tuple[int, int]]:
        """Pick the cost-minimising connection for this switching period.

        ``v_module[k]`` is module k's present total capacitor voltage. Returns
        ``(best_connection, short_edge)``.
        """
        short, candidates = self.reduced_set(v_in, v_out)
        v_mean = sum(v_module) / 9.0
        eps = [v_module[k] - v_mean for k in range(9)]      # Eq. 161
        scale = self.sn * self.ts / self.capacitance

        best = None
        best_j = math.inf
        for conn in candidates:
            currents = tree_module_currents(conn, i_in, i_out)
            j_cost = 0.0
            for k in range(9):
                i, j = divmod(k, 3)
                i_xy = currents.get((i, j), 0.0)
                dv = scale * i_xy                            # Eq. 162
                term = eps[k] + dv
                j_cost += term * term                       # Eq. 163
            if j_cost < best_j:
                best_j = j_cost
                best = conn
        return best if best is not None else candidates[0], short
