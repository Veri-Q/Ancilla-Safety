from qiskit.qasm2 import dumps as qasm2_dumps
from qiskit import QuantumCircuit, QuantumRegister


def generate_adder_circuit(n):
    qr_a = QuantumRegister(n - 1, name='anc')
    qr_q = QuantumRegister(n, name='q')
    qc = QuantumCircuit(qr_a, qr_q)

    qc.cx(qr_a[n - 2], qr_q[n - 1])

    for i in range(n - 1, 1, -1):
        qc.cx(qr_q[i - 1], qr_a[i - 1])
        qc.x(qr_q[i - 1])
        qc.ccx(qr_a[i - 2], qr_q[i - 1], qr_a[i - 1])

    qc.cx(qr_q[0], qr_a[0])

    for i in range(2, n):
        qc.ccx(qr_a[i - 2], qr_q[i - 1], qr_a[i - 1])

    qc.cx(qr_a[n - 2], qr_q[n - 1])
    qc.x(qr_q[n - 1])

    for i in range(n - 1, 1, -1):
        qc.ccx(qr_a[i - 2], qr_q[i - 1], qr_a[i - 1])

    qc.cx(qr_q[0], qr_a[0])

    for i in range(2, n):
        qc.ccx(qr_a[i - 2], qr_q[i - 1], qr_a[i - 1])
        qc.x(qr_q[i - 1])
        qc.cx(qr_q[i - 1], qr_a[i - 1])

    return qc


for k in range(3, 10):
    n = k
    circ = generate_adder_circuit(n)
    total = 2 * n - 1
    qasm_file = f"adder_n{n}_total{total}_dirty.qasm"
    qasm_str = qasm2_dumps(circ)
    with open(qasm_file, "w") as f:
        f.write(qasm_str)

    print(f"adder_n{n}_total{total}_dirty.qasm written to '{qasm_file}'")
