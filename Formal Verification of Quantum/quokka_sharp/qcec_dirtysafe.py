import qiskit
import time
import gc
from qiskit import QuantumCircuit
from mqt import qcec


def get_qubit_index(circuit: QuantumCircuit, reg_name: str, reg_index: int = 0) -> int:
    try:
        reg = next(r for r in circuit.qregs if r.name == reg_name)
        qubit = reg[reg_index]
        return circuit.find_bit(qubit).index
    except StopIteration:
        raise ValueError(f"Register '{reg_name}' not found in circuit.")
    except IndexError:
        raise ValueError(f"Register '{reg_name}' has insufficient length for index {reg_index}.")


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


def verify_pauli_invariance(qasm_file_path: str, target_reg_name: str, target_reg_index: int = 0):
    print(f"Loading circuit: {qasm_file_path} ...")
    u_circ = QuantumCircuit.from_qasm_file(qasm_file_path)

    target_qubit_idx = get_qubit_index(u_circ, target_reg_name, target_reg_index)
    print(f"Target qubit: {target_reg_name}[{target_reg_index}] (Global: {target_qubit_idx})")
    print("-" * 30)

    print("Verifying X operator commutativity...")

    rhs_x = QuantumCircuit(u_circ.num_qubits)
    rhs_x.x(target_qubit_idx)
    rhs_x.compose(u_circ, inplace=True)
    rhs_x.x(target_qubit_idx)

    start1 = time.time()
    result_x = qcec.verify(u_circ, rhs_x)
    end1 = time.time()

    if result_x.equivalence.name == "equivalent":
        print("PASS: U = X_a U X_a")
    else:
        print("FAIL: U != X_a U X_a")

    print("Cleaning up X verification memory...")
    del rhs_x
    del result_x
    gc.collect()

    print("-" * 30)

    print("Verifying Z operator commutativity...")

    rhs_z = QuantumCircuit(u_circ.num_qubits)
    rhs_z.z(target_qubit_idx)
    rhs_z.compose(u_circ, inplace=True)
    rhs_z.z(target_qubit_idx)

    start2 = time.time()
    result_z = qcec.verify(u_circ, rhs_z)
    end2 = time.time()

    if result_z.equivalence.name == "equivalent":
        print("PASS: U = Z_a U Z_a")
    else:
        print("FAIL: U != Z_a U Z_a")

    print(f"Total Verification Time: {end2 - start2 + end1 - start1:.1f}s")

    del rhs_z
    del result_z
    gc.collect()


def verify_all_ancilla(qasm_file_path: str, ancilla_file: str):
    print(f"=== Dirty Safe Check (QCEC) ===")
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
            verify_pauli_invariance(qasm_file_path, reg_name, reg_index)
        except Exception as e:
            print(f"FAIL: Error verifying {token}: {e}")
        gc.collect()

    end_time = time.time()
    print("=" * 40)
    print(f"Total time: {end_time - start_time:.1f}s")


if __name__ == "__main__":
    import sys
    qasm_file = sys.argv[1] if len(sys.argv) > 1 else "test0.qasm"
    ancilla_file = sys.argv[2] if len(sys.argv) > 2 else "anc.txt"

    verify_all_ancilla(qasm_file, ancilla_file)