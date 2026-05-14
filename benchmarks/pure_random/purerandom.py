import random
import numpy as np
from qiskit import QuantumCircuit
from qiskit.circuit import library as lib
import qiskit.qasm2


def get_gate_map():
    return {
        'x': (lib.XGate, 1), 'y': (lib.YGate, 1), 'z': (lib.ZGate, 1),
        'h': (lib.HGate, 1),
        's': (lib.SGate, 1),
        't': (lib.TGate, 1),
        'cx': (lib.CXGate, 2), 'ccx': (lib.CCXGate, 3)
    }


def generate_robust_random_u(num_qubits, total_gate_count, allowed_gates, seed=None):
    if seed is not None:
        random.seed(seed)
    qc = QuantumCircuit(num_qubits)
    gate_map = get_gate_map()
    available_gates = [g for g in allowed_gates if g in gate_map]

    for _ in range(total_gate_count):
        gate_name = random.choice(available_gates)
        gate_class, n_qubits = gate_map[gate_name]
        q_indices = random.sample(range(num_qubits), n_qubits)

        if gate_name in ['rx', 'ry', 'rz']:
            angle = random.uniform(0, 2 * np.pi)
            qc.append(gate_class(angle), q_indices)
        else:
            qc.append(gate_class(), q_indices)
    return qc


def create_verified_identity(num_qubits, gate_count, allowed_gates, seed=None):
    output_name = f"random_q{num_qubits}_g{gate_count}_s{seed}.qasm"

    U = generate_robust_random_u(num_qubits, gate_count, allowed_gates, seed=seed)

    full_qc = U

    print(f"--- Verification Report ---")
    print(f"Filename: {output_name}")
    print(f"Circuit: {num_qubits} qubits, {full_qc.depth()} depth, {sum(full_qc.count_ops().values())} total gates")
    print("-" * 20)

    with open(output_name, "w") as f:
        qiskit.qasm2.dump(full_qc, f)


if __name__ == "__main__":
    gates = ['h', 's', 't', 'cx', 'ccx', 'x', 'y', 'z', 'rx']
    for k in range(5, 6):
        for n in range(50, 101, 10):
            for d in range(5, 6):
                create_verified_identity(num_qubits=n, gate_count=d * n, allowed_gates=gates, seed=k)