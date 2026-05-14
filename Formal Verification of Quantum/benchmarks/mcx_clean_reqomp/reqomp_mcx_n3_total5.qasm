OPENQASM 2.0;
include "qelib1.inc";
qreg anc[1];
qreg c[3];
qreg tar[1];
ccx c[0],c[1],anc[0];
ccx c[2],anc[0],tar[0];
ccx c[0],c[1],anc[0];
