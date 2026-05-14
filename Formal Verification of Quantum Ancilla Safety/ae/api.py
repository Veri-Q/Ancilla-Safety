import json
import math
import multiprocessing as mp
import os
import resource
import shutil
import sys
import tempfile
import time
import traceback
import contextlib
import gc
import io
from pathlib import Path
from random import Random

import numpy as np
import qiskit
import qiskit.qasm2
from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator

from .common import (
    EPS,
    RESULT_MEMOUT,
    RESULT_TIMEOUT,
    classify_from_checks,
    ensure_dir,
    human_repair_action,
    normalize_targets,
    parse_qreg_layout,
    quokka_default_config,
    repo_root,
    qasm_metrics,
    summarize_target_results,
    write_json,
)

QUOKKA_SRC = repo_root() / "quokka_sharp"
if str(QUOKKA_SRC) not in sys.path:
    sys.path.insert(0, str(QUOKKA_SRC))

def _apply_limits(mem_gb: int | None) -> None:
    if mem_gb:
        limit_bytes = int(mem_gb * 1024 * 1024 * 1024)
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))


def _ensure_quokka_config_env(timeout_s: int) -> None:
    if os.environ.get("QUOKKA_CONFIG"):
        return
    solver_path = os.environ.get("GPMC_PATH", "/opt/gpmc/bin/gpmc")
    if not Path(solver_path).exists():
        local_solver = Path("/home/lijiqi/simulate_ver/GPMC/bin/gpmc")
        if local_solver.exists():
            solver_path = str(local_solver)
    config_path = Path(tempfile.gettempdir()) / f"quokka_config_{os.getpid()}.json"
    write_json(config_path, quokka_default_config(solver_path, timeout_s=timeout_s))
    os.environ["QUOKKA_CONFIG"] = str(config_path)


def _load_pipeline(timeout_s: int):
    _ensure_quokka_config_env(timeout_s)
    from pipeline import run_pipeline, validate_dirty_safe  # type: ignore

    return run_pipeline, validate_dirty_safe


RESOURCE_ERROR_PATTERNS = (
    "maximum allowed dimension exceeded",
    "unable to allocate",
    "out of memory",
    "std::bad_alloc",
    "cannot allocate memory",
    "array is too big",
    "insufficient memory",
    "memoryerror",
    "memout",
)


def _map_exception_to_result(error_type: str | None, message: str | None) -> str:
    error_type = error_type or "Error"
    message = (message or "").lower()
    if error_type in {RESULT_MEMOUT, "MemoryError", "MemoutError"}:
        return RESULT_MEMOUT
    if any(pattern in message for pattern in RESOURCE_ERROR_PATTERNS):
        return RESULT_MEMOUT
    return error_type


def _decimal_to_float(value):
    if isinstance(value, str):
        return value
    return float(value)


def _quokka_verify_structured(qasm_path: str, targets: list[dict]) -> dict:
    _, validate_dirty_safe = _load_pipeline(int(os.environ.get("AE_TIMEOUT_S", "3600")))
    target_indices = [item["index"] for item in targets]
    verification = validate_dirty_safe(qasm_path, target_indices)
    per_target = []
    logic_map = verification["logic error detection"]
    phase_map = verification["phase error detection"]
    for target in targets:
        logic_ok = bool(logic_map[target["index"]])
        phase_ok = bool(phase_map[target["index"]])
        per_target.append(
            {
                "target": target["ref"],
                "index": target["index"],
                "logic_ok": logic_ok,
                "phase_ok": phase_ok,
                "result": classify_from_checks(logic_ok, phase_ok),
            }
        )
    return {
        "target_results": per_target,
        "result": summarize_target_results(per_target),
        "verification": verification,
    }


def _qcec_get_qubit_index(circuit: QuantumCircuit, reg_name: str, reg_index: int = 0) -> int:
    reg = next(r for r in circuit.qregs if r.name == reg_name)
    qubit = reg[reg_index]
    return circuit.find_bit(qubit).index


def _qcec_is_equivalent(result) -> bool:
    return str(result.equivalence.name).lower().startswith("equivalent")


def _qcec_status(result, stdout: str, stderr: str) -> bool | None:
    text = f"{stdout}\n{stderr}".lower()
    if "no conclusion can be drawn" in text or "probably equivalent" in text:
        return None
    name = str(result.equivalence.name).lower()
    if name.startswith("equivalent"):
        return True
    if name.startswith("not_equivalent"):
        return False
    return None


def _qcec_verify_quiet(qcec_module, lhs: QuantumCircuit, rhs: QuantumCircuit) -> tuple[object, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        result = qcec_module.verify(lhs, rhs)
    return result, stdout.getvalue(), stderr.getvalue()


def _qcec_verify_structured(qasm_path: str, targets: list[dict]) -> dict:
    from mqt import qcec

    circuit = QuantumCircuit.from_qasm_file(qasm_path)
    per_target = []
    for target in targets:
        reg_name = target["ref"].split("[", 1)[0]
        reg_index = int(target["ref"].split("[", 1)[1][:-1])
        global_index = _qcec_get_qubit_index(circuit, reg_name, reg_index)

        rhs_x = QuantumCircuit(circuit.num_qubits)
        rhs_x.x(global_index)
        rhs_x.compose(circuit, inplace=True)
        rhs_x.x(global_index)
        x_result, x_stdout, x_stderr = _qcec_verify_quiet(qcec, circuit, rhs_x)
        phase_ok = _qcec_status(x_result, x_stdout, x_stderr)
        x_equivalence = x_result.equivalence.name
        del rhs_x
        del x_result
        gc.collect()

        rhs_z = QuantumCircuit(circuit.num_qubits)
        rhs_z.z(global_index)
        rhs_z.compose(circuit, inplace=True)
        rhs_z.z(global_index)
        z_result, z_stdout, z_stderr = _qcec_verify_quiet(qcec, circuit, rhs_z)
        logic_ok = _qcec_status(z_result, z_stdout, z_stderr)
        z_equivalence = z_result.equivalence.name
        del rhs_z
        del z_result
        gc.collect()
        result_label = RESULT_TIMEOUT if logic_ok is None or phase_ok is None else classify_from_checks(logic_ok, phase_ok)

        per_target.append(
            {
                "target": target["ref"],
                "index": target["index"],
                "logic_ok": logic_ok,
                "phase_ok": phase_ok,
                "qcec_inconclusive": logic_ok is None or phase_ok is None,
                "qcec_z_equivalence": z_equivalence,
                "qcec_x_equivalence": x_equivalence,
                "qcec_z_stdout": z_stdout,
                "qcec_z_stderr": z_stderr,
                "qcec_x_stdout": x_stdout,
                "qcec_x_stderr": x_stderr,
                "result": result_label,
            }
        )
    return {
        "target_results": per_target,
        "result": summarize_target_results(per_target),
    }


def _matrix_verify_structured(qasm_path: str, targets: list[dict]) -> dict:
    circuit = qiskit.qasm2.load(qasm_path)
    basis = ["cx", "x", "y", "z", "h", "s", "t", "tdg", "ccx", "id", "swap", "rz", "ry", "rx"]
    circuit = qiskit.transpile(circuit, basis_gates=basis, optimization_level=0)
    operator = Operator(circuit)
    unitary = operator.data
    num_qubits = circuit.num_qubits

    per_target = []
    for target in targets:
        qubit_index = target["index"]
        z_matrix = np.eye(2**num_qubits, dtype=complex)
        for row in range(2**num_qubits):
            if (row >> qubit_index) & 1:
                z_matrix[row, row] = -1

        x_matrix = np.zeros((2**num_qubits, 2**num_qubits), dtype=complex)
        for row in range(2**num_qubits):
            x_matrix[row ^ (1 << qubit_index), row] = 1

        logic_ok = np.linalg.norm(unitary @ z_matrix - z_matrix @ unitary) <= 1e-6
        phase_ok = np.linalg.norm(unitary @ x_matrix - x_matrix @ unitary) <= 1e-6
        per_target.append(
            {
                "target": target["ref"],
                "index": target["index"],
                "logic_ok": bool(logic_ok),
                "phase_ok": bool(phase_ok),
                "result": classify_from_checks(bool(logic_ok), bool(phase_ok)),
            }
        )
    return {
        "target_results": per_target,
        "result": summarize_target_results(per_target),
    }


def _verify_impl(backend: str, qasm_path: str, targets: list[dict], timeout_s: int, mem_gb: int | None, metadata: dict | None) -> dict:
    _apply_limits(mem_gb)
    os.environ["AE_TIMEOUT_S"] = str(timeout_s)
    started = time.time()
    if backend == "quokka":
        payload = _quokka_verify_structured(qasm_path, targets)
    elif backend == "qcec":
        payload = _qcec_verify_structured(qasm_path, targets)
    elif backend == "matrix":
        payload = _matrix_verify_structured(qasm_path, targets)
    else:
        raise ValueError(f"Unsupported backend: {backend}")
    elapsed = time.time() - started
    payload.update(
        {
            "backend": backend,
            "qasm": qasm_path,
            "targets": targets,
            "timeout_s": timeout_s,
            "mem_gb": mem_gb,
            "runtime_seconds": elapsed,
            "metadata": metadata or {},
        }
    )
    return payload


def _repair_impl(
    qasm_path: str,
    targets: list[dict],
    output_qasm: str,
    timeout_s: int,
    mem_gb: int | None,
    metadata: dict | None,
    repair_mode: str,
) -> dict:
    _apply_limits(mem_gb)
    os.environ["AE_TIMEOUT_S"] = str(timeout_s)
    started = time.time()
    target_refs = [item["ref"] for item in targets]
    ancilla_file = Path(output_qasm).with_suffix(".anc.txt")
    ancilla_file.write_text(",".join(target_refs))
    run_pipeline, _ = _load_pipeline(timeout_s)
    pipeline_result = run_pipeline(qasm_path, str(ancilla_file), output_qasm, repair_mode=repair_mode)
    elapsed = time.time() - started
    error_rows = pipeline_result.get("Errorlist", [])
    fail_list = pipeline_result.get("Faillist", [])
    rows = []
    for target in targets:
        matching = next((row for row in error_rows if row.get("qubit ref") == target["ref"]), None)
        fail_row = next((row for row in fail_list if row.get("qubit ref") == target["ref"]), None)
        repair_angles = matching.get("repair angles") if matching else None
        rows.append(
            {
                "target": target["ref"],
                "index": target["index"],
                "verify_result": next(
                    (
                        item["result"]
                        for item in _quokka_verify_structured(qasm_path, [target])["target_results"]
                    ),
                    "True",
                ),
                "entangle_check": "Insep" if fail_row and "cannot fix" in str(fail_row.get("reason", "")).lower() else ("Sep" if matching else "--"),
                "repair_action": human_repair_action(repair_angles),
                "repair_status": matching.get("repair status", "not-needed") if matching else ("failed" if fail_row else "not-needed"),
                "repair_angles": repair_angles,
                "reverify_result": next(
                    (
                        item["result"]
                        for item in _quokka_verify_structured(output_qasm, [target])["target_results"]
                    ),
                    "True",
                ),
                "failure_reason": fail_row.get("reason") if fail_row else matching.get("repair result") if matching else None,
            }
        )
    return {
        "backend": "quokka",
        "qasm": qasm_path,
        "targets": targets,
        "timeout_s": timeout_s,
        "mem_gb": mem_gb,
        "runtime_seconds": elapsed,
        "metadata": metadata or {},
        "repair_mode": repair_mode,
        "output_qasm": output_qasm,
        "pipeline": pipeline_result,
        "rows": rows,
    }


def _child_entry(queue, mode: str, kwargs: dict) -> None:
    try:
        if mode == "verify":
            payload = _verify_impl(**kwargs)
        elif mode == "repair":
            payload = _repair_impl(**kwargs)
        else:
            raise ValueError(f"Unsupported child mode: {mode}")
        queue.put({"ok": True, "payload": payload})
    except MemoryError:
        queue.put({"ok": False, "error_type": RESULT_MEMOUT, "message": "MemoryError"})
    except Exception as exc:  # pragma: no cover - surfaced in logs
        queue.put(
            {
                "ok": False,
                "error_type": exc.__class__.__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )


def _run_in_child(mode: str, timeout_s: int, kwargs: dict) -> dict:
    main_module = sys.modules.get("__main__")
    main_file = getattr(main_module, "__file__", None)
    if main_file and main_file != "<stdin>":
        start_method = "spawn"
    else:
        start_method = "fork" if "fork" in mp.get_all_start_methods() else "spawn"
    ctx = mp.get_context(start_method)
    queue = ctx.Queue()
    process = ctx.Process(target=_child_entry, args=(queue, mode, kwargs))
    started = time.time()
    process.start()
    process.join(timeout_s)
    elapsed = time.time() - started
    if process.is_alive():
        process.terminate()
        process.join()
        return {
            "result": RESULT_TIMEOUT,
            "runtime_seconds": elapsed,
            "error": "Timed out",
            "targets": kwargs.get("targets", []),
            "backend": kwargs.get("backend", "quokka"),
            "qasm": kwargs.get("qasm_path"),
            "metadata": kwargs.get("metadata", {}),
        }
    if queue.empty():
        return {
            "result": RESULT_MEMOUT if process.exitcode and process.exitcode != 0 else RESULT_TIMEOUT,
            "runtime_seconds": elapsed,
            "error": f"Child exited without payload (code={process.exitcode})",
            "targets": kwargs.get("targets", []),
            "backend": kwargs.get("backend", "quokka"),
            "qasm": kwargs.get("qasm_path"),
            "metadata": kwargs.get("metadata", {}),
        }
    outcome = queue.get()
    if outcome["ok"]:
        return outcome["payload"]
    result = _map_exception_to_result(outcome.get("error_type"), outcome.get("message"))
    return {
        "result": result,
        "runtime_seconds": elapsed,
        "error": outcome.get("message"),
        "traceback": outcome.get("traceback"),
        "raw_error_type": outcome.get("error_type"),
        "targets": kwargs.get("targets", []),
        "backend": kwargs.get("backend", "quokka"),
        "qasm": kwargs.get("qasm_path"),
        "metadata": kwargs.get("metadata", {}),
    }


def verify_dirty_safety(
    backend: str,
    qasm: str,
    targets: list[str | int] | None = None,
    timeout_s: int = 3600,
    mem_gb: int | None = 32,
    metadata: dict | None = None,
) -> dict:
    resolved_targets = normalize_targets(qasm, targets)
    return _run_in_child(
        mode="verify",
        timeout_s=timeout_s,
        kwargs={
            "backend": backend,
            "qasm_path": qasm,
            "targets": resolved_targets,
            "timeout_s": timeout_s,
            "mem_gb": mem_gb,
            "metadata": metadata,
        },
    )


def run_repair_pipeline(
    qasm: str,
    targets: list[str | int] | None = None,
    injection_spec: dict | None = None,
    output_qasm: str | None = None,
    repair_mode: str = "comp",
    timeout_s: int = 3600,
    mem_gb: int | None = 32,
    metadata: dict | None = None,
) -> dict:
    resolved_targets = normalize_targets(qasm, targets)
    source_qasm = qasm
    injection_result = None
    if injection_spec:
        injected_qasm = output_qasm or str(Path(qasm).with_name(f"{Path(qasm).stem}_injected.qasm"))
        injection_result = inject_errors(qasm, [item["ref"] for item in resolved_targets], output_qasm=injected_qasm, **injection_spec)
        source_qasm = injection_result["output_qasm"]
    final_output_qasm = output_qasm or str(Path(source_qasm).with_name(f"{Path(source_qasm).stem}_repaired.qasm"))
    result = _run_in_child(
        mode="repair",
        timeout_s=timeout_s,
        kwargs={
            "qasm_path": source_qasm,
            "targets": resolved_targets,
            "output_qasm": final_output_qasm,
            "repair_mode": repair_mode,
            "timeout_s": timeout_s,
            "mem_gb": mem_gb,
            "metadata": metadata,
        },
    )
    if injection_result:
        result["injection"] = injection_result
    return result


def inject_errors(
    qasm: str,
    targets: list[str | int],
    mode: str,
    seed: int,
    output_qasm: str,
    gate_count_range: tuple[int, int] = (1, 3),
    angle_range: tuple[float, float] = (0.0, math.pi),
) -> dict:
    rng = Random(seed)
    circuit = qiskit.qasm2.load(qasm)
    resolved_targets = normalize_targets(qasm, targets)
    output = Path(output_qasm)
    ensure_dir(output.parent)

    gate_sets = {
        "logic_only": ["x", "rx"],
        "phase_only": ["z", "rz", "s", "t"],
        "hybrid_logic": ["x", "rx"],
        "hybrid_phase": ["z", "rz", "s", "t"],
        "entangling_only": ["cx"],
        "arbitrary": ["x", "y", "z", "h", "s", "t", "rx", "rz", "cx"],
    }
    injections = []
    index_to_ref, _ = parse_qreg_layout(qasm)
    for target in resolved_targets:
        gate_count = rng.randint(gate_count_range[0], gate_count_range[1])
        operations = []
        if mode == "hybrid":
            operation_choices = [rng.choice(gate_sets["hybrid_logic"]), rng.choice(gate_sets["hybrid_phase"])]
            while len(operation_choices) < gate_count:
                operation_choices.append(rng.choice(gate_sets["arbitrary"]))
            rng.shuffle(operation_choices)
        else:
            choices = gate_sets[mode]
            operation_choices = [rng.choice(choices) for _ in range(gate_count)]

        for gate_name in operation_choices:
            qubit = circuit.qubits[target["index"]]
            angle = None
            if gate_name == "x":
                circuit.x(qubit)
            elif gate_name == "y":
                circuit.y(qubit)
            elif gate_name == "z":
                circuit.z(qubit)
            elif gate_name == "h":
                circuit.h(qubit)
            elif gate_name == "s":
                circuit.s(qubit)
            elif gate_name == "t":
                circuit.t(qubit)
            elif gate_name == "rx":
                angle = rng.uniform(angle_range[0], angle_range[1])
                circuit.rx(angle, qubit)
            elif gate_name == "rz":
                angle = rng.uniform(angle_range[0], angle_range[1])
                circuit.rz(angle, qubit)
            elif gate_name == "cx":
                partners = [idx for idx in range(circuit.num_qubits) if idx != target["index"]]
                if not partners:
                    raise ValueError("CX injection requires at least two qubits")
                partner_index = rng.choice(partners)
                partner_qubit = circuit.qubits[partner_index]
                circuit.cx(qubit, partner_qubit)
                operations.append(
                    {
                        "gate": gate_name,
                        "angle": None,
                        "partner_index": partner_index,
                        "partner_ref": index_to_ref.get(partner_index, f"q[{partner_index}]"),
                    }
                )
                continue
            else:
                raise ValueError(f"Unsupported injection gate: {gate_name}")
            operations.append({"gate": gate_name, "angle": angle})
        injections.append({"target": target["ref"], "index": target["index"], "operations": operations})

    with output.open("w") as handle:
        qiskit.qasm2.dump(circuit, handle)
    return {
        "input_qasm": qasm,
        "output_qasm": str(output),
        "seed": seed,
        "mode": mode,
        "targets": injections,
    }
