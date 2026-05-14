import os, copy
from .encoding.cnf import CNF
from subprocess import PIPE, Popen, TimeoutExpired
from .config import CONFIG
from .utils.utils import parse_wmc_result
import tempfile


tool_invocation = CONFIG["ToolInvocation"]
DEBUG           = CONFIG["DEBUG"]
TIMEOUT         = CONFIG["TIMEOUT"]
FPE             = CONFIG["FPE"]


def check_basis(i, start_basis, end_basis, cnf:'CNF', cnf_file_root):
    if DEBUG: print("index:", i)
    start_Z_or_X = start_basis == "Z"
    if end_basis == "Z":
        end_Z_or_X = True
    elif end_basis == "X":
        end_Z_or_X = False
    else:
        end_Z_or_X = 2
    cnf_temp = copy.deepcopy(cnf)
    cnf_temp.leftProjectZXi(start_Z_or_X, i)
    cnf_temp.rightProjectZXi(end_Z_or_X, i)
    if DEBUG: print(cnf_temp.cons_list)
    cnf_file = os.path.join(cnf_file_root, "quokka_entangle_check_"+ start_basis + "_" + end_basis + str(i) + ".cnf")
    cnf_temp.write_to_file(cnf_file)
    return cnf_file

def check_normalization(coeff_list):
    res = 0
    for i in coeff_list:
        res += i**2
    if DEBUG: print("normalization:", res)
    if abs(res - 1) < FPE:
        return True
    else:
        return False

def check_entanglement(i, cnf:'CNF', cnf_file_root):
    start   = ['X', 'Z']
    end     = ['X', 'Y', 'Z']
    coeff_X   = []
    coeff_Z   = []
    for start_basis in start:
        for end_basis in end:
            cnf_file = check_basis(i, start_basis, end_basis, cnf, cnf_file_root)
            tool_command = tool_invocation.split(' ')
            tool_file_command = tool_command + [cnf_file]
            if DEBUG: print(" ".join(tool_file_command))
            p = Popen(tool_file_command, stdout= PIPE, stderr=PIPE)
            try: 
                result = p.communicate(timeout = TIMEOUT)
                coeff = parse_wmc_result(result, square = cnf.square_result)
                if DEBUG: print(coeff)
                if start_basis == 'X':
                    # coeff_X.append({end_basis: coeff})
                    coeff_X.append(coeff)
                else:
                    # coeff_Z.append({end_basis: coeff})
                    coeff_Z.append(coeff)
            except TimeoutExpired:
                os.system("kill -9 " + str(p.pid))
                return "TIMEOUT"
    
    if DEBUG:         
        print("coeff_X:", coeff_X)
        print("coeff_Z:", coeff_Z)

    if check_normalization(coeff_X) and check_normalization(coeff_Z):
        return (coeff_X, coeff_Z)
    else:
        return True
    

import numpy as np


def _normalize_vector(vec, atol=1e-9):
    arr = np.asarray(vec, dtype=float)
    norm = np.linalg.norm(arr)
    if norm < atol:
        raise ValueError("Cannot normalize a near-zero vector.")
    return arr / norm


def _pauli_frame(alpha, beta, atol=1e-9):
    x_axis = _normalize_vector(alpha, atol=atol)
    z_axis = np.asarray(beta, dtype=float)
    z_axis = z_axis - np.dot(z_axis, x_axis) * x_axis
    z_axis = _normalize_vector(z_axis, atol=atol)
    y_axis = _normalize_vector(np.cross(z_axis, x_axis), atol=atol)

    frame = np.column_stack((x_axis, y_axis, z_axis))
    if np.linalg.det(frame) < 0:
        y_axis = -y_axis
        frame = np.column_stack((x_axis, y_axis, z_axis))

    if not np.allclose(frame.T @ frame, np.eye(3), atol=atol):
        raise ValueError("Pauli frame is not orthonormal.")
    return frame


def _rotation_to_rzrxrz(rotation, atol=1e-9):
    """
    Decompose a 3x3 SO(3) matrix as Rz(phi) Rx(theta) Rz(psi).
    Returns angles (phi, theta, psi).
    """

    rot = np.asarray(rotation, dtype=float)
    if rot.shape != (3, 3):
        raise ValueError("Rotation must be a 3x3 matrix.")
    if not np.allclose(rot.T @ rot, np.eye(3), atol=atol):
        raise ValueError("Rotation matrix is not orthogonal.")
    if not np.isclose(np.linalg.det(rot), 1.0, atol=atol):
        raise ValueError("Rotation matrix must have determinant +1.")

    cos_theta = float(np.clip(rot[2, 2], -1.0, 1.0))
    theta = float(np.arccos(cos_theta))
    sin_theta = float(np.sin(theta))

    if abs(sin_theta) > atol:
        phi = float(np.arctan2(rot[0, 2], -rot[1, 2]))
        psi = float(np.arctan2(rot[2, 0], rot[2, 1]))
        return phi, theta, psi

    if cos_theta > 0:
        phi = 0.0
        psi = float(np.arctan2(rot[1, 0], rot[0, 0]))
        return phi, 0.0, psi

    phi = 0.0
    psi = float(-np.arctan2(rot[1, 0], rot[0, 0]))
    return phi, float(np.pi), psi


def _rotation_from_rzrxrz(phi, theta, psi):
    c1, s1 = np.cos(phi), np.sin(phi)
    c2, s2 = np.cos(theta), np.sin(theta)
    c3, s3 = np.cos(psi), np.sin(psi)
    return np.array(
        [
            [c1 * c3 - s1 * c2 * s3, -c1 * s3 - s1 * c2 * c3, s1 * s2],
            [s1 * c3 + c1 * c2 * s3, -s1 * s3 + c1 * c2 * c3, -c1 * s2],
            [s2 * s3, s2 * c3, c2],
        ],
        dtype=float,
    )


def solve_thetas(alpha, beta, atol=1e-9):
    """
    Return textual QASM angles (a, b, c) for
        rz(a); rx(b); rz(c);
    such that the appended repair gate maps alpha -> X and beta -> Z
    under Pauli conjugation.
    """

    alpha = _normalize_vector(alpha, atol=atol)
    beta = _normalize_vector(beta, atol=atol)
    if not np.isclose(np.dot(alpha, beta), 0.0, atol=atol):
        raise ValueError("alpha and beta must be orthogonal.")

    frame = _pauli_frame(alpha, beta, atol=atol)
    repair_rotation = frame.T
    phi, theta, psi = _rotation_to_rzrxrz(repair_rotation, atol=atol)
    a, b, c = psi, theta, phi

    reconstructed = _rotation_from_rzrxrz(c, b, a)
    if not np.allclose(reconstructed, repair_rotation, atol=1e-8):
        raise ValueError("Failed to decompose repair rotation into rz-rx-rz angles.")

    ex = np.array([1.0, 0.0, 0.0])
    ez = np.array([0.0, 0.0, 1.0])
    if not np.allclose(repair_rotation @ alpha, ex, atol=1e-8):
        raise ValueError("Computed repair rotation does not map alpha to X.")
    if not np.allclose(repair_rotation @ beta, ez, atol=1e-8):
        raise ValueError("Computed repair rotation does not map beta to Z.")

    return a, b, c

def Repair(cnf: "CNF", i, cnf_file_root = tempfile.gettempdir()):
    res = check_entanglement(i, cnf, cnf_file_root)
    if res == True:
        return("cannot fix")
    else:
        alpha = res[0]; beta = res[1]
        theta_1, theta_2, theta_3 = solve_thetas(alpha, beta)
        return(theta_1, theta_2, theta_3)
        
