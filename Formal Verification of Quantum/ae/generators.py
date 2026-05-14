import importlib.util
from pathlib import Path

from qiskit import transpile
from qiskit.qasm2 import dump as qasm2_dump

from .common import ensure_dir, repo_root


def _load_module(relative_path: str, module_name: str):
    path = repo_root() / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load generator module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_qasm(output_path: Path, circuit) -> str:
    ensure_dir(output_path.parent)
    with output_path.open("w") as handle:
        qasm2_dump(circuit, handle)
    return str(output_path)


def generate_mcx(total_bits: int, output_path: str) -> str:
    module = _load_module("benchmarks/mcx/MCX_gen.py", "ae_mcx_gen")
    controls = (total_bits + 1) // 2
    return module.generate_mcx(total_bits=controls * 2 - 1 if total_bits % 2 == 1 else total_bits, dirty=True, output=output_path)


def generate_grover_full(total_bits: int, output_path: str) -> str:
    module = _load_module("benchmarks/grover/grover_full/grover_gen.py", "ae_grover_full")
    working_qubits = (total_bits + 1) // 2
    return module.generate_grover(n=working_qubits, marked_item=0, dirty=True, output=output_path)


def generate_grover_r1(total_bits: int, output_path: str) -> str:
    module = _load_module("benchmarks/grover/grover_r1/grover_r1_gen.py", "ae_grover_r1")
    working_qubits = (total_bits + 1) // 2
    return module.generate_grover(n=working_qubits, marked_item=0, dirty=True, output=output_path)


def generate_adder(total_bits: int, output_path: str) -> str:
    module = _load_module("benchmarks/adder_dirty/adder_gen.py", "ae_adder_gen")
    working_qubits = (total_bits + 1) // 2
    circuit = module.generate_adder_circuit(working_qubits)
    return _write_qasm(Path(output_path), circuit)


def generate_bridge_ghz(total_bits: int, output_path: str) -> str:
    module = _load_module("benchmarks/bridge-ghz/bridgeghz_gen.py", "ae_bridge_ghz")
    working_qubits = (total_bits + 1) // 2
    circuit = module.generate_dirty_bridge_ghz(working_qubits, True)
    return _write_qasm(Path(output_path), circuit)


def generate_reqomp_clean(total_bits: int, output_path: str) -> str:
    module = _load_module("benchmarks/mcx/MCX_gen.py", "ae_reqomp_gen")
    controls = (total_bits + 1) // 2
    return module.generate_mcx(total_bits=controls * 2 - 1 if total_bits % 2 == 1 else total_bits, dirty=False, output=output_path)


def generate_identity_random(num_qubits: int, gate_count: int, seed: int, output_path: str) -> str:
    module = _load_module("benchmarks/universal_random_circuit/id_rancir.py", "ae_identity_random")
    gates = ["h", "s", "t", "cx", "ccx", "x", "y", "z"]
    circuit = module.create_verified_identity(num_qubits=num_qubits, gate_count=gate_count, allowed_gates=gates, seed=seed)
    # Fallback for legacy generator that writes internally and returns None.
    if circuit is not None:
        return _write_qasm(Path(output_path), circuit)
    generated_name = f"identity_q{num_qubits}_g{gate_count}_s{seed}.qasm"
    generated_path = repo_root() / generated_name
    output = Path(output_path)
    ensure_dir(output.parent)
    output.write_text(generated_path.read_text())
    return str(output)


def generate_random(num_qubits: int, gate_count: int, seed: int, output_path: str) -> str:
    module = _load_module("benchmarks/pure_random/purerandom.py", "ae_pure_random")
    gates = ["h", "s", "t", "cx", "ccx", "x", "y", "z"]
    circuit = module.create_verified_identity(num_qubits=num_qubits, gate_count=gate_count, allowed_gates=gates, seed=seed)
    if circuit is not None:
        return _write_qasm(Path(output_path), circuit)
    generated_name = f"random_q{num_qubits}_g{gate_count}_s{seed}.qasm"
    generated_path = repo_root() / generated_name
    output = Path(output_path)
    ensure_dir(output.parent)
    output.write_text(generated_path.read_text())
    return str(output)


def _grover_working_qubits(total_qubits: int) -> int:
    if total_qubits < 3 or total_qubits % 2 == 0:
        raise ValueError("Grover total qubits must be an odd integer >= 3")
    return (total_qubits + 1) // 2


def generate_grover_rounds(total_qubits: int, rounds: int, output_path: str) -> str:
    module = _load_module("benchmarks/grover/grover_full/grover_gen.py", "ae_grover_rounds")
    working_qubits = _grover_working_qubits(total_qubits)
    oracle = module.makesOracle_manual(0, working_qubits, dirty=True)
    circuit = module.makesGroverCircuit_manual(working_qubits, oracle=oracle, dirty=True, iterations=rounds)
    circuit = transpile(circuit, basis_gates=["h", "x", "cx", "ccx"], optimization_level=0)
    return _write_qasm(Path(output_path), circuit)


def materialize_source(source: dict, output_dir: str) -> tuple[str, bool]:
    source_type = source["type"]
    if source_type == "existing":
        return str(repo_root() / source["path"]), False

    output_dir_path = ensure_dir(output_dir)
    if source_type == "generate":
        generator = source["generator"]
        params = dict(source.get("params", {}))
        filename = source.get("filename")
        if filename is None:
            filename = f"{generator}.qasm"
        output_path = output_dir_path / filename
        if generator == "mcx":
            return generate_mcx(params["total_bits"], str(output_path)), True
        if generator == "grover_full":
            return generate_grover_full(params["total_bits"], str(output_path)), True
        if generator == "grover_r1":
            return generate_grover_r1(params["total_bits"], str(output_path)), True
        if generator == "adder":
            return generate_adder(params["total_bits"], str(output_path)), True
        if generator == "bridge_ghz":
            return generate_bridge_ghz(params["total_bits"], str(output_path)), True
        if generator == "reqomp_clean":
            return generate_reqomp_clean(params["total_bits"], str(output_path)), True
        if generator == "identity_random":
            return generate_identity_random(params["num_qubits"], params["gate_count"], params["seed"], str(output_path)), True
        if generator == "pure_random":
            return generate_random(params["num_qubits"], params["gate_count"], params["seed"], str(output_path)), True
        if generator == "grover_rounds":
            return generate_grover_rounds(params["total_qubits"], params["rounds"], str(output_path)), True
        raise ValueError(f"Unsupported generator: {generator}")

    raise ValueError(f"Unsupported source type: {source_type}")
