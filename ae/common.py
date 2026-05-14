import json
import math
import os
import re
import sys
from pathlib import Path

import qiskit.qasm2


EPS = 1e-12
RESULT_TRUE = "True"
RESULT_LOGIC = "LogicError"
RESULT_PHASE = "PhaseError"
RESULT_BOTH = "BothError"
RESULT_TIMEOUT = "Timeout"
RESULT_MEMOUT = "Memout"


def ensure_dir(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def read_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def write_json(path: str | Path, payload: dict) -> None:
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def parse_qreg_layout(qasm_path: str | Path) -> tuple[dict[int, str], dict[str, int]]:
    text = Path(qasm_path).read_text()
    statements = []
    for chunk in text.split(";"):
        stmt = chunk.split("//", 1)[0].strip()
        if stmt:
            statements.append(stmt)

    index_to_ref: dict[int, str] = {}
    ref_to_index: dict[str, int] = {}
    global_idx = 0
    qreg_pattern = re.compile(r"^qreg\s+([A-Za-z_]\w*)\[(\d+)\]$")
    for stmt in statements:
        match = qreg_pattern.match(stmt)
        if not match:
            continue
        reg_name = match.group(1)
        reg_size = int(match.group(2))
        for local_idx in range(reg_size):
            ref = f"{reg_name}[{local_idx}]"
            index_to_ref[global_idx] = ref
            ref_to_index[ref] = global_idx
            global_idx += 1
    return index_to_ref, ref_to_index


def list_registers(qasm_path: str | Path) -> list[str]:
    _, ref_to_index = parse_qreg_layout(qasm_path)
    names = []
    for ref in ref_to_index:
        name = ref.split("[", 1)[0]
        if name not in names:
            names.append(name)
    return names


def default_targets_for_qasm(qasm_path: str | Path, count: int = 1) -> list[str]:
    index_to_ref, ref_to_index = parse_qreg_layout(qasm_path)
    anc_refs = [ref for ref in ref_to_index if ref.startswith("anc[")]
    if anc_refs:
        return anc_refs[:count]

    registers = list_registers(qasm_path)
    if not registers:
        raise ValueError(f"No qreg declaration found in {qasm_path}")
    first_register = registers[0]
    refs = [ref for ref in index_to_ref.values() if ref.startswith(f"{first_register}[")]
    return refs[:count]


def resolve_target(qasm_path: str | Path, target: str | int) -> tuple[int, str]:
    index_to_ref, ref_to_index = parse_qreg_layout(qasm_path)
    if isinstance(target, int):
        if target not in index_to_ref:
            raise ValueError(f"Qubit index out of range: {target}")
        return target, index_to_ref[target]
    text = str(target).strip()
    if text.isdigit():
        idx = int(text)
        if idx not in index_to_ref:
            raise ValueError(f"Qubit index out of range: {idx}")
        return idx, index_to_ref[idx]
    if text not in ref_to_index:
        raise ValueError(f"Qubit reference not found in QASM: {text}")
    return ref_to_index[text], text


def normalize_targets(qasm_path: str | Path, targets: list[str | int] | None) -> list[dict]:
    selected = targets or default_targets_for_qasm(qasm_path, 1)
    seen: set[int] = set()
    result = []
    for target in selected:
        idx, ref = resolve_target(qasm_path, target)
        if idx in seen:
            continue
        seen.add(idx)
        result.append({"index": idx, "ref": ref})
    return result


def classify_from_checks(logic_ok: bool, phase_ok: bool) -> str:
    if logic_ok and phase_ok:
        return RESULT_TRUE
    if (not logic_ok) and phase_ok:
        return RESULT_LOGIC
    if logic_ok and (not phase_ok):
        return RESULT_PHASE
    return RESULT_BOTH


def status_rank(result: str) -> int:
    order = {
        RESULT_TRUE: 0,
        RESULT_LOGIC: 1,
        RESULT_PHASE: 1,
        RESULT_BOTH: 2,
        RESULT_TIMEOUT: 3,
        RESULT_MEMOUT: 4,
    }
    return order.get(result, 99)


def summarize_target_results(target_results: list[dict]) -> str:
    if not target_results:
        return RESULT_TRUE
    ranked = sorted((item["result"] for item in target_results), key=status_rank)
    return ranked[-1]


def get_qasm_info(qasm_path: str | Path) -> tuple[tuple[int, int] | None, str | None]:
    path = Path(qasm_path)
    if not path.exists():
        return None, f"Error: File {path} not found."
    try:
        circuit = qiskit.qasm2.load(str(path))
        return (int(circuit.depth() or 0), int(circuit.num_qubits)), None
    except Exception as exc:
        return None, f"Error parsing QASM: {exc}"


def qasm_metrics(qasm_path: str | Path) -> dict:
    info, error = get_qasm_info(qasm_path)
    if info is not None:
        depth, num_qubits = info
        circuit = qiskit.qasm2.load(str(qasm_path))
        ops = circuit.count_ops()
        return {
            "num_qubits": num_qubits,
            "depth": depth,
            "gates": int(sum(ops.values())),
            "registers": [reg.name for reg in circuit.qregs],
        }

    quokka_src = repo_root() / "quokka_sharp"
    if str(quokka_src) not in sys.path:
        sys.path.insert(0, str(quokka_src))
    import quokka_sharp as qk  # type: ignore

    circuit = qk.encoding.QASMparser(str(qasm_path), translate_ccx=False)
    gate_lines = 0
    for line in Path(qasm_path).read_text().splitlines():
        text = line.strip()
        if not text or text.startswith("//") or text.startswith("OPENQASM") or text.startswith("include") or text.startswith("qreg"):
            continue
        gate_lines += 1
    _, ref_to_index = parse_qreg_layout(qasm_path)
    registers = []
    for ref in ref_to_index:
        reg = ref.split("[", 1)[0]
        if reg not in registers:
            registers.append(reg)
    return {
        "num_qubits": int(circuit.n),
        "depth": int(circuit.depth()),
        "gates": gate_lines,
        "registers": registers,
    }


def quokka_default_config(tool_path: str, timeout_s: int = 3600) -> dict:
    return {
        "DEBUG": False,
        "TIMEOUT": timeout_s,
        "ToolInvocation": f"{tool_path} -mode=1",
        "GetResult": "exact.double.prec-sci.(.+?)\\\\nc s",
        "FPE": 1e-12,
        "Precision": 50,
    }


def human_repair_action(angles: list[float] | tuple[float, float, float] | None) -> str:
    if not angles:
        return "--"
    a, b, c = [float(v) for v in angles]
    pi = math.pi
    period = 2.0 * pi

    def close_mod(value: float, target: float, abs_tol: float = 1e-8) -> bool:
        return math.isclose(math.remainder(value - target, period), 0.0, abs_tol=abs_tol)

    if close_mod(a, 0.0) and close_mod(c, 0.0):
        return "Apply Rx"
    if close_mod(a, pi) and close_mod(c, -pi):
        return "Apply Rx"
    if close_mod(a, -pi) and close_mod(c, pi):
        return "Apply Rx"
    if close_mod(b, 0.0):
        return "Apply Rz"
    return "Apply Rz·Rx·Rz"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def relpath(path: str | Path) -> str:
    try:
        return os.path.relpath(Path(path), repo_root())
    except ValueError:
        return str(path)
