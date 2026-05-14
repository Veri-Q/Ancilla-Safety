import sys
import gc
import time
from copy import deepcopy

import quokka_sharp as qk


def parse_ancilla_tokens(filename: str) -> list[str]:
    with open(filename, 'r') as f:
        content = f.read().strip()
    return [token.strip() for token in content.split(',') if token.strip()]


def parse_reg_index(token: str) -> tuple[str, int]:
    token = token.strip()
    if '[' in token and token.endswith(']'):
        reg_name = token[:token.index('[')]
        reg_index = int(token[token.index('[') + 1:-1])
        return reg_name, reg_index
    raise ValueError(f"Invalid ancilla token format: {token}")


def verify_dirty_safe(qasm_file_path: str, ancilla_file: str):
    print(f"Loading circuit: {qasm_file_path} ...")
    base_circuit = qk.encoding.QASMparser(qasm_file_path, translate_ccx=False)
    print(f"Loaded {base_circuit.n} qubits")
    print("-" * 40)

    ancilla_tokens = parse_ancilla_tokens(ancilla_file)
    print(f"Detected {len(ancilla_tokens)} ancilla: {ancilla_tokens}")
    print("-" * 40)

    start_time = time.time()

    for token in ancilla_tokens:
        reg_name, reg_index = parse_reg_index(token)
        print(f"\nVerifying {token} ...")

        logic_pass = False
        phase_pass = False

        circuit_before = deepcopy(base_circuit)
        cnf_before = qk.encoding.QASM2CNF(circuit_before, computational_basis=True)
        cnf_before.precondition({reg_index: 0})
        cnf_before.postcondition({reg_index: 0})
        prob_before = qk.Simulate(cnf_before)

        if abs(prob_before - 1) < 1e-12:
            print(f"  [Original circuit] prob = {prob_before:.6f} PASS")
            logic_pass = True
        else:
            print(f"  [Original circuit] prob = {prob_before:.6f} FAIL (logic error)")

        circuit_after = deepcopy(base_circuit)
        circuit_after.add_h_ancilla(reg_index)
        cnf_after = qk.encoding.QASM2CNF(circuit_after, computational_basis=True)
        cnf_after.precondition({reg_index: 0})
        cnf_after.postcondition({reg_index: 0})
        prob_after = qk.Simulate(cnf_after)

        if abs(prob_after - 1) < 1e-12:
            print(f"  [With H gate] prob = {prob_after:.6f} PASS")
            phase_pass = True
        else:
            print(f"  [With H gate] prob = {prob_after:.6f} FAIL (phase error)")

        if logic_pass and phase_pass:
            print(f"  Final result: {token} is DIRTY SAFE")
        elif logic_pass and not phase_pass:
            print(f"  Final result: {token} is PHASE ERROR")
        elif not logic_pass and phase_pass:
            print(f"  Final result: {token} is LOGIC ERROR")
        else:
            print(f"  Final result: {token} is BOTH ERROR")

        del cnf_before, cnf_after, circuit_before, circuit_after
        gc.collect()

    end_time = time.time()
    print("-" * 40)
    print(f"Total time: {end_time - start_time:.3f}s")


if __name__ == "__main__":
    qasm_file = sys.argv[1] if len(sys.argv) > 1 else "test0.qasm"
    ancilla_file = sys.argv[2] if len(sys.argv) > 2 else "anc.txt"

    print(f"=== Dirty Safe Check ===")
    print(f"QASM file: {qasm_file}")
    print(f"Ancilla file: {ancilla_file}")
    print()

    try:
        verify_dirty_safe(qasm_file, ancilla_file)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()