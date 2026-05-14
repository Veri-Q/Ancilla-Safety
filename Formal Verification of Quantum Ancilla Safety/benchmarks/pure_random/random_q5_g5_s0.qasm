OPENQASM 2.0;
include "qelib1.inc";
qreg q[5];
y q[3];
h q[2];
z q[3];
ccx q[3],q[2],q[4];
cx q[4],q[1];
