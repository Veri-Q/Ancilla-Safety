import numpy as np
import argparse
from qiskit import QuantumCircuit, QuantumRegister, AncillaRegister, transpile
from qiskit import qasm2


def makeMCX(n, dirty=True):
    assert n >= 1, "n must be at least 1"

    q_controls = QuantumRegister(n, name='ctrls')
    q_target = QuantumRegister(1, name='target')
    q_ancillas = AncillaRegister(n - 2, name='anc') if n > 2 else None

    circuit = QuantumCircuit(q_controls, q_target, *( [q_ancillas] if q_ancillas else [] ), name=f"MCX_{n}")

    if n == 1:
        circuit.cx(q_controls[0], q_target)
        return circuit
    if n == 2:
        circuit.ccx(q_controls[0], q_controls[1], q_target)
        return circuit

    circuit.ccx(q_controls[0], q_controls[1], q_ancillas[0])
    idx_list = []
    i = 0
    for j in range(2, n - 1):
        circuit.ccx(q_controls[j], q_ancillas[i], q_ancillas[i + 1])
        if dirty:
            idx_list.append((j, i))
        i += 1
    circuit.ccx(q_controls[-1], q_ancillas[i], q_target)

    if dirty:
        prepend_circuit = QuantumCircuit(q_controls, q_target, q_ancillas)
        prepend_circuit.ccx(q_controls[-1], q_ancillas[i], q_target)
        for j, i in reversed(idx_list):
            prepend_circuit.ccx(q_controls[j], q_ancillas[i], q_ancillas[i + 1])
        circuit = prepend_circuit.compose(circuit)

    uncompute_circuit = circuit.copy()
    if not dirty:
        uncompute_circuit.data.pop()
    else:
        del uncompute_circuit.data[0]
        del uncompute_circuit.data[-1]
    circuit = circuit.compose(uncompute_circuit.inverse())
    return circuit


def makesOracle_manual(i, n, dirty=False):
    ctrls = QuantumRegister(n)
    target = QuantumRegister(1)
    anc_qubits = AncillaRegister(n - 2, name='anc') if n > 2 else None

    fcirc = QuantumCircuit(ctrls, target, *( [anc_qubits] if anc_qubits else [] ))

    binary_i = f'{i:0{n}b}'[::-1]
    for j in range(n):
        if binary_i[j] == '0':
            fcirc.x(ctrls[j])

    fcirc.append(makeMCX(n, dirty).to_gate(), [*ctrls, target[0], *(anc_qubits[:] if anc_qubits else [])])

    for j in range(n):
        if binary_i[j] == '0':
            fcirc.x(ctrls[j])

    return fcirc


def makesGroverCircuit_manual(n, oracle=None, dirty=False, iterations=None):
    nbIter = int(np.floor(np.pi / 4.0 * np.sqrt(2 ** n))) if iterations is None else iterations

    working_qubits = QuantumRegister(n, name='r')
    phase_qubit = QuantumRegister(1, name='ph_ase')
    anc_qubits = AncillaRegister(n - 2, name='anc') if n > 2 else None

    circ = QuantumCircuit(*( [anc_qubits] if anc_qubits else [] ), working_qubits, phase_qubit, name='Grover')

    circ.x(phase_qubit[0])
    circ.h(phase_qubits := phase_qubit[0])
    circ.h(working_qubits)

    for _ in range(nbIter):
        if oracle is not None:
            circ.append(oracle.to_gate(), [*working_qubits, phase_qubit[0], *(anc_qubits[:] if anc_qubits else [])])
        else:
            circ.append(makeMCX(n, dirty).to_gate(), [*working_qubits, phase_qubit[0], *(anc_qubits[:] if anc_qubits else [])])

        circ.h(working_qubits)
        circ.x(working_qubits)
        circ.h(working_qubits[-1])

        circ.append(makeMCX(n - 1, dirty).to_gate(), [*working_qubits[:-1], working_qubits[-1], *(anc_qubits[:-1] if anc_qubits else [])])

        circ.h(working_qubits[-1])
        circ.x(working_qubits)
        circ.h(working_qubits)

    return circ


def generate_grover(n, marked_item=0, dirty=True, output=None):
    """Generate Grover circuit and export to QASM2 file."""
    oracle = makesOracle_manual(marked_item, n, dirty=dirty)
    grover_circ = makesGroverCircuit_manual(n, oracle=oracle, dirty=dirty)

    grover_circ = transpile(grover_circ, basis_gates=['h', 'x', 'cx', 'ccx'], optimization_level=0)

    qasm_str = qasm2.dumps(grover_circ)

    if output is None:
        anc_type = "dirty" if dirty else "clean"
        output = f"grover_n{n}_{anc_type}_{marked_item}.qasm"

    with open(output, "w") as f:
        f.write(qasm_str)

    if "qreg anc[" in qasm_str:
        print(f"Success: Register 'anc' found in {output}")
    else:
        print(f"Warning: Register 'anc' NOT found in {output}")

    return output


def main():
    parser = argparse.ArgumentParser(description="Generate Grover quantum search circuit")
    parser.add_argument("n", type=int, help="Number of qubits")
    parser.add_argument("--marked-item", "-m", type=int, default=0, help="Target state (default: 0)")
    parser.add_argument("--dirty", "-d", action="store_true", default=True, help="Use dirty ancilla (default: True)")
    parser.add_argument("--clean", "-c", action="store_true", help="Use clean ancilla")
    parser.add_argument("--output", "-o", type=str, default=None, help="Output file path")

    args = parser.parse_args()

    dirty = not args.clean
    generate_grover(args.n, marked_item=args.marked_item, dirty=dirty, output=args.output)


if __name__ == "__main__":
    main()
