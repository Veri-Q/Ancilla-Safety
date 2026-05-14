import numpy as np
from qiskit import QuantumCircuit, QuantumRegister, AncillaRegister, transpile
from qiskit import qasm2


def makeMCX(n, dirty=True):
    assert n >= 1, "n must be at least 1"

    q_ancillas = AncillaRegister(n - 2, name='anc') if n > 2 else None
    q_controls = QuantumRegister(n, name='ctrls')
    q_target = QuantumRegister(1, name='target')

    circuit = QuantumCircuit(*( [q_ancillas] if q_ancillas else [] ), q_controls, q_target, name=f"MCX_{n}")

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
        prepend_circuit = QuantumCircuit(*( [q_ancillas] if q_ancillas else [] ), q_controls, q_target)
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


def generate_mcx(total_bits, dirty=True, output=None):
    """
    Generate MCX circuit and export to QASM2 file.

    Args:
        total_bits: Total number of qubits (2n - 1)
        dirty: Use dirty ancilla (default: True)
        output: Output file path (default: MCX_n{n}_total{total_bits}.qasm)
    """
    n = (total_bits + 1) // 2
    mcx_circ = makeMCX(n, dirty=dirty)
    qasm_str = qasm2.dumps(mcx_circ)

    if output is None:
        output = f"MCX_n{n}_total{total_bits}.qasm"

    with open(output, "w") as f:
        f.write(qasm_str)

    if "qreg anc[" in qasm_str:
        print(f"Success: Register 'anc' found in {output}")
    else:
        print(f"Warning: Register 'anc' NOT found in {output}")

    return output


def main():
    total_bits_list = [199, 399, 599, 999, 1399, 1599, 1799, 1999, 3999, 5999, 7999, 9999]

    for total in total_bits_list:
        n = (total + 1) // 2
        dirty = True
        qasm_file = f"MCX_n{n}_total{total}.qasm"

        mcx_circ = makeMCX(n, dirty=dirty)
        qasm_str = qasm2.dumps(mcx_circ)
        with open(qasm_file, "w") as f:
            f.write(qasm_str)

        print(f"MCX circuit with n={n}, total={total}, dirty={dirty} written to '{qasm_file}'")


if __name__ == "__main__":
    main()