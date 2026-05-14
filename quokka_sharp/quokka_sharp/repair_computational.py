# Copyright (c) 2026 Jiqi Li and Jingyi Mei
# Licensed under the MIT License. See LICENSE and NOTICE.md for provenance.

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal

import numpy as np

import quokka_sharp as qk

from .repair import solve_thetas


PROBE_ATOL = 1e-6


def _prepend_single(circuit, gate: str, qubit: int) -> None:
    circuit.circ.insert(0, [gate, qubit])


def _append_single(circuit, gate: str, qubit: int) -> None:
    circuit.add_single(gate, qubit)


def _probe_probability(base_circuit, qubit: int, prep_gate: str | None, measure_basis: str):
    circuit = deepcopy(base_circuit)

    if prep_gate is not None:
        _prepend_single(circuit, prep_gate, qubit)

    if measure_basis == "X":
        _append_single(circuit, "h", qubit)
    elif measure_basis == "Y":
        _append_single(circuit, "sdg", qubit)
        _append_single(circuit, "h", qubit)
    elif measure_basis != "Z":
        raise ValueError(f"Unsupported measurement basis: {measure_basis}")

    cnf = qk.encoding.QASM2CNF(circuit, computational_basis=True)
    cnf.precondition({qubit: 0})
    cnf.postcondition({qubit: 0})
    return qk.Simulate(cnf)


def _expectation_from_probability(prob) -> float:
    if isinstance(prob, str):
        raise RuntimeError(prob)
    return float(Decimal(2) * Decimal(prob) - Decimal(1))


def _compute_probe_vector(base_circuit, qubit: int, prep_gate: str | None) -> list[float]:
    coords = []
    for basis in ("X", "Y", "Z"):
        prob = _probe_probability(base_circuit, qubit, prep_gate, basis)
        coords.append(_expectation_from_probability(prob))
    return coords


def _is_repairable_frame(alpha, beta, atol: float) -> bool:
    alpha_arr = np.asarray(alpha, dtype=float)
    beta_arr = np.asarray(beta, dtype=float)
    alpha_norm = np.linalg.norm(alpha_arr)
    beta_norm = np.linalg.norm(beta_arr)
    dot = float(np.dot(alpha_arr, beta_arr))
    return (
        abs(alpha_norm - 1.0) <= atol
        and abs(beta_norm - 1.0) <= atol
        and abs(dot) <= atol
    )


def RepairComputationalDetails(qasmfile: str, qubit: int, atol: float = PROBE_ATOL) -> dict:
    base_circuit = qk.encoding.QASMparser(qasmfile, translate_ccx=False)

    try:
        beta = _compute_probe_vector(base_circuit, qubit, prep_gate=None)
        alpha = _compute_probe_vector(base_circuit, qubit, prep_gate="h")
    except Exception as exc:
        return {
            "result": str(exc),
            "probe alpha": None,
            "probe beta": None,
            "candidate validated": False,
        }

    details = {
        "probe alpha": [float(x) for x in alpha],
        "probe beta": [float(x) for x in beta],
        "candidate validated": False,
    }

    if not _is_repairable_frame(alpha, beta, atol=atol):
        details["result"] = "cannot fix"
        return details

    try:
        details["result"] = solve_thetas(alpha, beta, atol=atol)
    except Exception as exc:
        details["result"] = str(exc)
    return details


def RepairComputational(qasmfile: str, qubit: int, atol: float = PROBE_ATOL):
    return RepairComputationalDetails(qasmfile, qubit, atol=atol)["result"]
