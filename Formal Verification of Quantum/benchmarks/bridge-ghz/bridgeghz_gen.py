import qiskit
from qiskit import QuantumCircuit, QuantumRegister, AncillaRegister, qasm2
import os


def generate_dirty_bridge_ghz(n: int, dirty=True):
    """
    Generate an n-qubit GHZ state circuit where CNOT operations between adjacent
    working qubits are implemented via a Dirty Ancilla using 4-CNOT components.

    Args:
        n (int): Number of working qubits (n >= 2)
    """
    if n < 2:
        raise ValueError("GHZ state requires at least 2 qubits.")

    a = AncillaRegister(n - 1, name='anc')
    q = QuantumRegister(n, name='q')

    qc = QuantumCircuit(a, q)
    qc.h(q[0])

    for i in range(n - 1):
        ctrl_qubit = q[i]
        target_qubit = q[i + 1]
        bridge_ancilla = a[i]

        qc.cx(ctrl_qubit, bridge_ancilla)
        qc.cx(bridge_ancilla, target_qubit)
        qc.cx(ctrl_qubit, bridge_ancilla)

        if dirty:
            qc.cx(bridge_ancilla, target_qubit)

    return qc


def save_to_qasm(qc, n):
    total = 2 * n - 1
    filename = f"ghz_dirty_bridge_n{n}_total{total}.qasm"
    qasm_str = qasm2.dumps(qc)

    with open(filename, "w") as f:
        f.write(qasm_str)

    print(f"[Success] Circuit generated and saved to: {os.path.abspath(filename)}")
    print(f"Stats: {n} Working Qubits, {n - 1} Dirty Ancillas, Total Depth: {qc.depth()}")


if __name__ == "__main__":
    for k in range(2600, 3000, 50):
        N = k
        circuit = generate_dirty_bridge_ghz(N, True)
        save_to_qasm(circuit, N)

    # Generate n=2000 (total = 3999)
    N = 2000
    circuit = generate_dirty_bridge_ghz(N, True)
    save_to_qasm(circuit, N)