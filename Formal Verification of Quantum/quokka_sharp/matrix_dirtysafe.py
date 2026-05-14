import re
import numpy as np
import time
import os
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import Operator
import qiskit.qasm2


def get_qubit_indices(circuit, reg_name):
    target_reg = None
    for reg in circuit.qregs:
        if reg.name == reg_name:
            target_reg = reg
            break

    if target_reg is None:
        return []

    indices = []
    for i, qubit in enumerate(circuit.qubits):
        if qubit in target_reg:
            indices.append(i)

    return indices


def parse_ancilla_tokens(ancilla_file):
    tokens = []
    with open(ancilla_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                parts = re.split(r'[,;]', line)
                for part in parts:
                    part = part.strip()
                    if part:
                        tokens.append(part)
    return tokens


def parse_reg_index(token):
    token = token.strip()
    if '[' in token and ']' in token:
        reg_name = token[:token.index('[')]
        idx_str = token[token.index('[')+1:token.index(']')]
        reg_index = int(idx_str)
        return reg_name, reg_index
    else:
        return token, None


def verify_dirty_safety_matrix(qasm_file, target_reg_name, target_reg_index=None):
    print(f"Loading QASM: {qasm_file} ...")

    if not os.path.exists(qasm_file):
        print(f"Error: File not found {qasm_file}")
        return

    try:
        circ = qiskit.qasm2.load(qasm_file)
    except Exception as e:
        print(f"Error: Failed to parse QASM file: {e}")
        return

    basis = ['cx', 'x', 'h', 't', 'tdg', 'ccx', 'id', 'swap', 'rz', 'ry', 'rx']
    circ_clean = transpile(circ, basis_gates=basis, optimization_level=0)

    target_indices = get_qubit_indices(circ_clean, target_reg_name)
    if not target_indices:
        print(f"Error: Register '{target_reg_name}' not found in circuit.")
        print("Available registers:", [r.name for r in circ.qregs])
        return

    if target_reg_index is not None:
        if target_reg_index >= len(target_indices):
            print(f"Error: Index {target_reg_index} out of range (register has {len(target_indices)} qubits)")
            return
        target_indices = [target_indices[target_reg_index]]

    n_qubits = circ_clean.num_qubits
    print(f"Circuit: {n_qubits} qubits")

    print("Computing unitary matrix...")
    try:
        op = Operator(circ_clean)
        U = op.data
    except Exception as e:
        print(f"Matrix computation failed: {e}")
        return

    target_qubit_idx = target_indices[0]

    # Z operator on target qubit: diagonal with -1 on states where qubit=1
    Z_a = np.eye(2**n_qubits, dtype=complex)
    for j in range(2**n_qubits):
        if (j >> target_qubit_idx) & 1:
            Z_a[j, j] = -1

    # X operator on target qubit: flip the qubit
    X_a = np.zeros((2**n_qubits, 2**n_qubits), dtype=complex)
    for j in range(2**n_qubits):
        new_j = j ^ (1 << target_qubit_idx)
        X_a[new_j, j] = 1

    # Check commutativity: [U, Z_a] = U @ Z_a - Z_a @ U
    # If commutes, ancilla value is preserved (logic safe)
    commutator_z = U @ Z_a - Z_a @ U
    logic_error = np.linalg.norm(commutator_z) > 1e-6

    # Check commutativity: [U, X_a]
    # If commutes, phase is preserved (phase safe)
    commutator_x = U @ X_a - X_a @ U
    phase_error = np.linalg.norm(commutator_x) > 1e-6

    print("-" * 40)
    print(f"Verification target: Register '{target_reg_name}' (Index: {target_qubit_idx})")
    print("-" * 40)

    if logic_error:
        print(f"[FAIL] Z commutativity: LOGIC ERROR")
    else:
        print(f"[PASS] Z commutativity: Logic preserved")

    if phase_error:
        print(f"[FAIL] X commutativity: PHASE ERROR")
    else:
        print(f"[PASS] X commutativity: Phase preserved")

    print("-" * 40)
    if not logic_error and not phase_error:
        print(f"Final result: {target_reg_name} is fully DIRTY SAFE")
    elif logic_error and not phase_error:
        print(f"Final result: {target_reg_name} is LOGIC ERROR")
    elif not logic_error and phase_error:
        print(f"Final result: {target_reg_name} is PHASE ERROR")
    else:
        print(f"Final result: {target_reg_name} is BOTH ERROR")


def verify_all_ancilla(qasm_file_path: str, ancilla_file: str):
    print(f"=== Dirty Safe Check (Matrix) ===")
    print(f"QASM file: {qasm_file_path}")
    print(f"Ancilla file: {ancilla_file}")
    print()

    ancilla_tokens = parse_ancilla_tokens(ancilla_file)
    print(f"Detected {len(ancilla_tokens)} ancilla: {ancilla_tokens}")
    print("=" * 40)

    start_time = time.time()

    for token in ancilla_tokens:
        reg_name, reg_index = parse_reg_index(token)
        print(f"\n>>> Verifying {token} ...")
        try:
            verify_dirty_safety_matrix(qasm_file_path, reg_name, reg_index)
        except Exception as e:
            print(f"Error: {e}")

    end_time = time.time()
    print()
    print("=" * 40)
    print(f"Total time: {end_time - start_time:.3f}s")


if __name__ == "__main__":
    import sys
    qasm_file = sys.argv[1] if len(sys.argv) > 1 else "test0.qasm"
    ancilla_file = sys.argv[2] if len(sys.argv) > 2 else "anc.txt"

    verify_all_ancilla(qasm_file, ancilla_file)