"""
Dirty-safe repair pipeline with selectable repair backends.
"""

import argparse
import io
import json
import os
import re
import shutil
import tempfile
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path

import quokka_sharp as qk
from quokka_sharp.repair_computational import RepairComputationalDetails


EPS = 1e-12


def read_ancilla_tokens(filename: str) -> list[str]:
    with open(filename, "r") as f:
        content = f.read().strip()
    return [token.strip() for token in content.split(",") if token.strip()]


def simulate_for_qubit(circuit, i: int):
    cnf = qk.encoding.QASM2CNF(circuit, computational_basis=True)
    cnf.precondition({i: 0})
    cnf.postcondition({i: 0})
    return qk.Simulate(cnf)


def is_true_result(prob) -> bool:
    return not isinstance(prob, str) and abs(prob - 1) < EPS


def repair_qubit_pauli(qasmfile: str, idx: int):
    circuit = qk.encoding.QASMparser(qasmfile, translate_ccx=False)
    cnf = qk.encoding.QASM2CNF(circuit, computational_basis=False)
    return qk.Repair(cnf, int(idx))


def validate_candidate_repair(qasm_file: str, qubit: int, angles: tuple[float, float, float]) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".qasm", delete=False) as tmp:
        temp_qasm = tmp.name
    try:
        shutil.copyfile(qasm_file, temp_qasm)
        append_rzrxrz_repair(temp_qasm, qubit, angles)
        check = validate_dirty_safe(temp_qasm, [qubit])
        return bool(check["dirty safe check"])
    finally:
        try:
            os.remove(temp_qasm)
        except OSError:
            pass


def repair_qubit_comp(qasmfile: str, idx: int) -> dict:
    details = RepairComputationalDetails(qasmfile, int(idx))
    result = details.get("result")
    if isinstance(result, tuple) and len(result) == 3:
        try:
            validated = validate_candidate_repair(qasmfile, int(idx), result)
        except Exception as exc:
            details["result"] = str(exc)
            details["candidate validated"] = False
            return details
        details["candidate validated"] = validated
        if not validated:
            details["result"] = "cannot fix"
    return details


def validate_dirty_safe(qasm_file: str, ancilla_list: list[int]) -> dict:
    base_circuit = qk.encoding.QASMparser(qasm_file, translate_ccx=False)
    logic_result = {}
    phase_result = {}
    error_list = []

    for i in ancilla_list:
        logic_circuit = deepcopy(base_circuit)
        logic_prob = simulate_for_qubit(logic_circuit, i)
        logic_ok = is_true_result(logic_prob)
        logic_result[i] = logic_ok

        phase_circuit = deepcopy(base_circuit)
        phase_circuit.add_h_ancilla(i)
        phase_prob = simulate_for_qubit(phase_circuit, i)
        phase_ok = is_true_result(phase_prob)
        phase_result[i] = phase_ok

        error_types = []
        if not logic_ok:
            error_types.append("logic error")
        if not phase_ok:
            error_types.append("phase error")
        if error_types:
            error_list.append(
                {
                    "qubit": i,
                    "logic error detection": logic_ok,
                    "phase error detection": phase_ok,
                    "errors": error_types,
                }
            )

    return {
        "logic error detection": logic_result,
        "phase error detection": phase_result,
        "dirty safe check": len(error_list) == 0,
        "Errorlist": error_list,
    }


def build_index_to_qubit_ref(qasm_file: str) -> dict[int, str]:
    text = Path(qasm_file).read_text()
    statements = []
    for chunk in text.split(";"):
        stmt = chunk.split("//", 1)[0].strip()
        if stmt:
            statements.append(stmt)

    index_to_ref = {}
    global_idx = 0
    qreg_pattern = re.compile(r"^qreg\s+([A-Za-z_]\w*)\[(\d+)\]$")
    for stmt in statements:
        match = qreg_pattern.match(stmt)
        if not match:
            continue
        reg_name = match.group(1)
        reg_size = int(match.group(2))
        for local_idx in range(reg_size):
            index_to_ref[global_idx] = f"{reg_name}[{local_idx}]"
            global_idx += 1
    return index_to_ref


def resolve_ancilla_indices(ancilla_file: str, qasm_file: str) -> tuple[list[int], dict[int, str]]:
    index_to_ref = build_index_to_qubit_ref(qasm_file)
    ref_to_index = {ref: idx for idx, ref in index_to_ref.items()}
    tokens = read_ancilla_tokens(ancilla_file)

    indices = []
    for token in tokens:
        if token.isdigit():
            idx = int(token)
            if idx not in index_to_ref:
                raise ValueError(f"Ancilla index out of range: {idx}")
        else:
            if token not in ref_to_index:
                raise ValueError(f"Ancilla qubit not found in QASM: {token}")
            idx = ref_to_index[token]
        indices.append(idx)

    seen = set()
    unique_indices = []
    for idx in indices:
        if idx in seen:
            continue
        seen.add(idx)
        unique_indices.append(idx)

    selected_map = {idx: index_to_ref[idx] for idx in unique_indices}
    return unique_indices, selected_map


def append_rzrxrz_repair(qasm_file: str, qubit_index: int, angles: tuple[float, float, float]) -> None:
    index_to_ref = build_index_to_qubit_ref(qasm_file)
    if qubit_index not in index_to_ref:
        raise ValueError(f"Qubit index {qubit_index} not found in qreg declarations.")

    qref = index_to_ref[qubit_index]
    a, b, c = angles
    text = Path(qasm_file).read_text()
    if text and not text.endswith("\n"):
        text += "\n"
    text += f"rz({a}) {qref};\n"
    text += f"rx({b}) {qref};\n"
    text += f"rz({c}) {qref};\n"
    Path(qasm_file).write_text(text)


def run_pipeline(
    qasm_file: str,
    ancilla_file: str,
    output_qasm_file: str | None = None,
    repair_mode: str = "comp",
) -> dict:
    ancilla_list, index_to_ref = resolve_ancilla_indices(ancilla_file, qasm_file)
    initial_check = validate_dirty_safe(qasm_file, ancilla_list)
    for row in initial_check["Errorlist"]:
        idx = row["qubit"]
        row["qubit ref"] = index_to_ref.get(idx, f"q[{idx}]")
    error_list = [dict(item) for item in initial_check["Errorlist"]]

    if output_qasm_file is None:
        output_qasm_file = f"{Path(qasm_file).with_suffix('')}_repaired.qasm"
    shutil.copyfile(qasm_file, output_qasm_file)

    fail_list = []
    for row in error_list:
        qubit = row["qubit"]
        try:
            if repair_mode == "pauli":
                repair_result = repair_qubit_pauli(output_qasm_file, qubit)
                repair_details = None
            else:
                repair_details = repair_qubit_comp(output_qasm_file, qubit)
                repair_result = repair_details["result"]
                row["repair mode"] = "comp"
                row["probe alpha"] = repair_details.get("probe alpha")
                row["probe beta"] = repair_details.get("probe beta")
                row["candidate validated"] = bool(repair_details.get("candidate validated"))
        except Exception as exc:
            row["repair status"] = "failed"
            row["repair result"] = str(exc)
            fail_list.append({"qubit": qubit, "qubit ref": index_to_ref.get(qubit, f"q[{qubit}]"), "reason": str(exc)})
            continue

        if isinstance(repair_result, tuple) and len(repair_result) == 3:
            try:
                append_rzrxrz_repair(output_qasm_file, qubit, repair_result)
                row["repair status"] = "repaired"
                row["repair angles"] = [float(repair_result[0]), float(repair_result[1]), float(repair_result[2])]
            except Exception as exc:
                row["repair status"] = "failed"
                row["repair result"] = str(exc)
                fail_list.append({"qubit": qubit, "qubit ref": index_to_ref.get(qubit, f"q[{qubit}]"), "reason": str(exc)})
        else:
            row["repair status"] = "failed"
            row["repair result"] = str(repair_result)
            fail_list.append({"qubit": qubit, "qubit ref": index_to_ref.get(qubit, f"q[{qubit}]"), "reason": str(repair_result)})

    final_check = validate_dirty_safe(output_qasm_file, ancilla_list)
    for row in final_check["Errorlist"]:
        idx = row["qubit"]
        row["qubit ref"] = index_to_ref.get(idx, f"q[{idx}]")
    return {
        "input qasm file": qasm_file,
        "ancilla file": ancilla_file,
        "repair mode": repair_mode,
        "ancilla targets": [index_to_ref[i] for i in ancilla_list],
        "failed qubits before repair": [row["qubit ref"] for row in initial_check["Errorlist"]],
        "Errorlist": error_list,
        "repaired qasm file": output_qasm_file,
        "Faillist": fail_list,
        "verification before repair": initial_check,
        "verification after repair": final_check,
    }


def _fmt_bool(v: bool) -> str:
    return "PASS" if v else "FAIL"


def print_human_readable(results: dict) -> None:
    before = results["verification before repair"]
    after = results["verification after repair"]
    error_list = results["Errorlist"]
    fail_list = results["Faillist"]

    print("=== Dirty Safe Repair Report ===")
    print(f"Input QASM   : {results['input qasm file']}")
    print(f"Ancilla file : {results['ancilla file']}")
    print(f"Output QASM  : {results['repaired qasm file']}")
    print(f"Repair mode  : {results['repair mode']}")
    print(f"Targets      : {results['ancilla targets']}")
    print("")

    print("[1] Validation Before Repair")
    print(f"- Dirty safe check: {_fmt_bool(before['dirty safe check'])}")
    failed = results["failed qubits before repair"]
    print(f"- Failed qubits   : {failed if failed else 'None'}")
    print("")

    print("[2] Errorlist")
    if not error_list:
        print("- No errors detected.")
    else:
        for row in error_list:
            q = row.get("qubit ref", f"q[{row['qubit']}]")
            q_idx = row["qubit"]
            errs = ", ".join(row["errors"])
            status = row.get("repair status", "not attempted")
            angle_text = ""
            if "repair angles" in row:
                a, b, c = row["repair angles"]
                angle_text = f" | angles(rz-rx-rz)=({a:.12g}, {b:.12g}, {c:.12g})"
            if "repair result" in row:
                angle_text = f" | reason={row['repair result']}"
            print(f"- qubit {q} (index {q_idx}): errors={errs} | repair={status}{angle_text}")
    print("")

    print("[3] Faillist")
    if not fail_list:
        print("- None")
    else:
        for row in fail_list:
            q = row.get("qubit ref", f"q[{row['qubit']}]")
            print(f"- qubit {q} (index {row['qubit']}): {row['reason']}")
    print("")

    print("[4] Validation After Repair")
    print(f"- Dirty safe check: {_fmt_bool(after['dirty safe check'])}")
    print(f"- Remaining errors: {len(after['Errorlist'])}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("-q", "--qasmfile", required=True, help="Path to input QASM file")
    parser.add_argument("-a", "--ancilla", required=True, help="Path to ancilla.txt")
    parser.add_argument("-o", "--output", default=None, help="Path to repaired QASM output file")
    parser.add_argument("--repair-mode", choices=["comp", "pauli"], default="comp", help="Repair backend to use")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument("--verbose", action="store_true", help="Show raw logs from underlying solvers")
    args = parser.parse_args()

    qasm_path = Path(args.qasmfile)
    ancilla_path = Path(args.ancilla)
    if not qasm_path.is_file():
        raise SystemExit(f"QASM file not found: {qasm_path}")
    if not ancilla_path.is_file():
        raise SystemExit(f"Ancilla file not found: {ancilla_path}")

    if args.verbose:
        results = run_pipeline(str(qasm_path), str(ancilla_path), args.output, repair_mode=args.repair_mode)
    else:
        with redirect_stdout(io.StringIO()):
            results = run_pipeline(str(qasm_path), str(ancilla_path), args.output, repair_mode=args.repair_mode)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_human_readable(results)


if __name__ == "__main__":
    main()
