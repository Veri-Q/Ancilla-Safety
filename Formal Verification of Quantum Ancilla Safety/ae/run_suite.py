import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

from .api import inject_errors, run_repair_pipeline, verify_dirty_safety
from .common import (
    RESULT_MEMOUT,
    RESULT_TIMEOUT,
    ensure_dir,
    qasm_metrics,
    quokka_default_config,
    read_json,
    relpath,
    repo_root,
    summarize_target_results,
    write_json,
)
from .generators import materialize_source


MANIFEST_PATH = repo_root() / "ae" / "manifest.json"
DEFAULT_AE_TIMEOUT_S = 3600
DEFAULT_AE_MEM_GB = 24
PAPER_TIMEOUT_S = 3600
PAPER_MEM_GB = 32
PERFORMANCE_FIELDNAMES = [
    "Benchmark",
    "N",
    "Depth",
    "Matrix Time",
    "Matrix Output",
    "Quokka-Sharp Time",
    "Quokka-Sharp Output",
    "QCEC Time",
    "QCEC Output",
]
REPAIR_FIELDNAMES = [
    "Case",
    "N",
    "Depth",
    "Gates",
    "Injected",
    "Target",
    "Diagnosis",
    "Entangle Check",
    "Repair Action",
    "ReVerify",
    "Output",
    "Repair Mode",
]
FIGURE_FIELDNAMES = [
    "figure",
    "kind",
    "series",
    "x",
    "runtime_seconds",
    "result",
    "source_qasm",
    "generated",
    "representative_run",
    "raw_log",
]
BACKEND_DISAGREEMENT_FIELDNAMES = [
    "row_id",
    "benchmark",
    "N",
    "Depth",
    "target",
    "Matrix Output",
    "Quokka-Sharp Output",
    "QCEC Output",
    "Matrix Raw Log",
    "Quokka-Sharp Raw Log",
    "QCEC Raw Log",
    "kind",
]
QCEC_INCONCLUSIVE_FIELDNAMES = [
    "row_id",
    "benchmark",
    "N",
    "Depth",
    "target",
    "qcec_z_equivalence",
    "qcec_x_equivalence",
    "diagnostic_excerpt",
    "raw_log",
]
RESOURCE_OR_INFRA_OUTPUTS = {
    RESULT_TIMEOUT,
    RESULT_MEMOUT,
    "ModuleNotFoundError",
    "QASM2ParseError",
    "FileNotFoundError",
    "Error",
}


def _log(message: str) -> None:
    print(message, flush=True)


def _results_root(output_dir: str | None) -> Path:
    return ensure_dir(output_dir or repo_root() / "results")


def _prepare_dirs(output_dir: str | None) -> dict[str, Path]:
    root = _results_root(output_dir)
    return {
        "root": root,
        "raw": ensure_dir(root / "raw"),
        "processed": ensure_dir(root / "processed"),
        "figures": ensure_dir(root / "figures"),
        "generated": ensure_dir(repo_root() / "generated"),
        "generated_injected": ensure_dir(repo_root() / "generated" / "injected"),
        "generated_repaired": ensure_dir(repo_root() / "generated" / "repaired"),
    }


def ensure_quokka_config(output_dir: str | None, timeout_s: int = 3600) -> str:
    dirs = _prepare_dirs(output_dir)
    solver_path = os.environ.get("GPMC_PATH", "/opt/gpmc/bin/gpmc")
    if not Path(solver_path).exists():
        local_solver = Path("/home/lijiqi/simulate_ver/GPMC/bin/gpmc")
        if local_solver.exists():
            solver_path = str(local_solver)
    config_path = dirs["processed"] / "quokka_config.json"
    write_json(config_path, quokka_default_config(solver_path, timeout_s=timeout_s))
    os.environ["QUOKKA_CONFIG"] = str(config_path)
    return str(config_path)


def _materialize_case_qasm(case: dict, generated_dir: Path) -> tuple[str, bool, bool]:
    representative = bool(case.get("representative_run", False))
    source = case["source"]
    if case.get("artifact_source"):
        source = case["artifact_source"]
        representative = True
    qasm_path, generated = materialize_source(source, generated_dir / case["id"])
    return qasm_path, generated, representative


def _write_raw_log(raw_dir: Path, payload: dict, stem: str) -> str:
    path = raw_dir / f"{stem}.json"
    write_json(path, payload)
    return str(path)


def _backend_result_row(case: dict, qasm_path: str, metrics: dict, backend_result: dict, generated: bool, representative: bool, raw_log_path: str) -> dict:
    target_results = backend_result.get("target_results", backend_result.get("targets", []))
    target_refs = [item["target"] for item in target_results if isinstance(item, dict) and "target" in item]
    if not target_refs:
        target_refs = [str(target) for target in case.get("targets", ["--"])]
    return {
        "row_id": case["id"],
        "benchmark": case["benchmark"],
        "N": metrics["num_qubits"],
        "Depth": metrics["depth"],
        "Gates": metrics["gates"],
        "backend": backend_result.get("backend"),
        "time_seconds": round(float(backend_result.get("runtime_seconds", 0.0)), 4),
        "output": backend_result.get("result"),
        "target": ",".join(target_refs),
        "source_qasm": relpath(qasm_path),
        "generated": generated,
        "representative_run": representative,
        "raw_log": relpath(raw_log_path),
    }


def _process_verification_case(
    case: dict,
    dirs: dict[str, Path],
    stage: str = "verify",
    case_index: int | None = None,
    case_total: int | None = None,
) -> list[dict]:
    qasm_path, generated, representative = _materialize_case_qasm(case, dirs["generated"])
    metrics = qasm_metrics(qasm_path)
    rows = []
    active_qasm = qasm_path
    case_progress = f"{case_index}/{case_total} " if case_index is not None and case_total is not None else ""
    _log(
        f"[{stage}] case {case_progress}{case['id']} "
        f"benchmark={case['benchmark']} N={metrics['num_qubits']} depth={metrics['depth']} "
        f"targets={','.join(str(target) for target in case['targets'])} "
        f"backends={','.join(case['backends'])}"
    )
    if case.get("injection"):
        injected_path = dirs["generated_injected"] / f"{case['id']}.qasm"
        _log(f"[{stage}]   injecting errors seed={case['injection'].get('seed')} mode={case['injection'].get('mode')}")
        injection_result = inject_errors(qasm_path, case["targets"], output_qasm=str(injected_path), **case["injection"])
        injection_log = _write_raw_log(dirs["raw"], injection_result, f"{case['id']}_injection")
        active_qasm = injection_result["output_qasm"]
        metrics = qasm_metrics(active_qasm)
        rows.append(
            {
                "row_id": case["id"],
                "benchmark": case["benchmark"],
                "N": metrics["num_qubits"],
                "Depth": metrics["depth"],
                "Gates": metrics["gates"],
                "backend": "injection",
                "time_seconds": 0.0,
                "output": case["injection"]["mode"],
                "target": case["targets"][0],
                "source_qasm": relpath(active_qasm),
                "generated": True,
                "representative_run": representative,
                "raw_log": relpath(injection_log),
            }
        )
    for backend_index, backend in enumerate(case["backends"], start=1):
        _log(
            f"[{stage}]   backend {backend_index}/{len(case['backends'])} {backend} "
            f"targets={','.join(str(target) for target in case['targets'])} "
            f"timeout={case.get('timeout_s', 3600)}s mem={case.get('mem_gb', 32)}GB"
        )
        result = verify_dirty_safety(
            backend=backend,
            qasm=active_qasm,
            targets=case["targets"],
            timeout_s=case.get("timeout_s", 3600),
            mem_gb=case.get("mem_gb", 32),
            metadata={"case_id": case["id"], "row_group": case.get("row_group")},
        )
        raw_path = _write_raw_log(dirs["raw"], result, f"{case['id']}_{backend}")
        rows.append(_backend_result_row(case, active_qasm, metrics, result, generated, representative, raw_path))
        _log(
            f"[{stage}]   done {backend}: output={result.get('result')} "
            f"time={float(result.get('runtime_seconds', 0.0)):.3f}s raw={relpath(raw_path)}"
        )
    return rows


def _process_repair_case(
    case: dict,
    dirs: dict[str, Path],
    stage: str = "table2",
    case_index: int | None = None,
    case_total: int | None = None,
) -> list[dict]:
    qasm_path, generated, representative = _materialize_case_qasm(case, dirs["generated"])
    base_metrics = qasm_metrics(qasm_path)
    rows = []
    case_progress = f"{case_index}/{case_total} " if case_index is not None and case_total is not None else ""
    _log(
        f"[{stage}] case {case_progress}{case['id']} "
        f"benchmark={case['benchmark']} N={base_metrics['num_qubits']} depth={base_metrics['depth']} "
        f"repair_mode={case.get('repair_mode', 'comp')} rows={len(case['rows'])}"
    )

    target_to_label = {row["target"]: row["case_label"] for row in case["rows"]}

    def _collect_fail_labels_from_result(result: dict) -> list[str]:
        fail_labels: list[str] = []
        pipeline = result.get("pipeline", {})
        for item in pipeline.get("Faillist", []) or []:
            qref = item.get("qubit ref")
            if qref in target_to_label:
                fail_labels.append(target_to_label[qref])
        for entry in result.get("rows", []) or []:
            if str(entry.get("failure_reason", "")).lower() == "cannot fix":
                label = target_to_label.get(entry.get("target"))
                if label:
                    fail_labels.append(label)
        ordered = []
        seen = set()
        for row in case["rows"]:
            label = row["case_label"]
            if label in fail_labels and label not in seen:
                seen.add(label)
                ordered.append(label)
        return ordered

    def _format_output_cell(base_output: str, fail_labels: list[str]) -> str:
        if fail_labels:
            return "FailList: {" + ", ".join(fail_labels) + "}"
        return base_output
    if not any(row.get("injection") for row in case["rows"]):
        targets = [row["target"] for row in case["rows"]]
        case_labels = [row["case_label"] for row in case["rows"]]
        _log(
            f"[{stage}]   batch repair targets={','.join(targets)} "
            f"timeout={case.get('timeout_s', 3600)}s mem={case.get('mem_gb', 32)}GB"
        )
        result = run_repair_pipeline(
            qasm=qasm_path,
            targets=targets,
            injection_spec=None,
            output_qasm=str(dirs["generated_repaired"] / f"{case['id']}_repaired.qasm"),
            repair_mode=case.get("repair_mode", "comp"),
            timeout_s=case.get("timeout_s", 3600),
            mem_gb=case.get("mem_gb", 32),
            metadata={"case_id": case["id"], "case_labels": case_labels, "benchmark": case["benchmark"]},
        )
        raw_path = _write_raw_log(dirs["raw"], result, f"{case['id']}_repair")
        fail_labels = _collect_fail_labels_from_result(result)
        entries_by_target = {entry.get("target"): entry for entry in result.get("rows", [])}
        for row in case["rows"]:
            entry = entries_by_target.get(row["target"])
            if result.get("result") in {RESULT_TIMEOUT, RESULT_MEMOUT} or entry is None:
                rows.append(
                    {
                        "Case": case["benchmark"],
                        "N": base_metrics["num_qubits"],
                        "Depth": base_metrics["depth"],
                        "Gates": base_metrics["gates"],
                        "Injected": "Yes" if row.get("injected", False) else "No",
                        "Target": row["case_label"],
                        "Diagnosis": result.get("result", "Error"),
                        "EntangleCheck": "--",
                        "RepairAction": "--",
                        "ReVerify": result.get("result", "Error"),
                        "Output": _format_output_cell(result.get("error") or result.get("result", "Error"), fail_labels),
                        "RepairMode": case.get("repair_mode", "comp"),
                        "raw_log": relpath(raw_path),
                        "representative_run": representative,
                        "generated": generated,
                    }
                )
                continue
            rows.append(
                {
                    "Case": case["benchmark"],
                    "N": base_metrics["num_qubits"],
                    "Depth": base_metrics["depth"],
                    "Gates": base_metrics["gates"],
                    "Injected": "Yes" if row.get("injected", False) else "No",
                    "Target": row["case_label"],
                    "Diagnosis": entry["verify_result"],
                    "EntangleCheck": entry["entangle_check"],
                    "RepairAction": entry["repair_action"],
                    "ReVerify": entry["reverify_result"],
                    "Output": _format_output_cell(entry["failure_reason"] or entry["reverify_result"], fail_labels),
                    "RepairMode": result.get("repair_mode", case.get("repair_mode", "comp")),
                    "raw_log": relpath(raw_path),
                    "representative_run": representative,
                    "generated": generated,
                }
            )
        _log(
            f"[{stage}]   done batch repair: rows={len(rows)} "
            f"time={float(result.get('runtime_seconds', 0.0)):.3f}s raw={relpath(raw_path)}"
        )
        return rows

    for row_index, row in enumerate(case["rows"], start=1):
        _log(
            f"[{stage}]   repair row {row_index}/{len(case['rows'])} "
            f"target={row['case_label']} timeout={case.get('timeout_s', 3600)}s mem={case.get('mem_gb', 32)}GB"
        )
        result = run_repair_pipeline(
            qasm=qasm_path,
            targets=[row["target"]],
            injection_spec=row.get("injection"),
            output_qasm=str(dirs["generated_repaired"] / f"{case['id']}_{row['case_label']}_repaired.qasm"),
            repair_mode=case.get("repair_mode", "comp"),
            timeout_s=case.get("timeout_s", 3600),
            mem_gb=case.get("mem_gb", 32),
            metadata={"case_id": case["id"], "case_label": row["case_label"], "benchmark": case["benchmark"]},
        )
        raw_path = _write_raw_log(dirs["raw"], result, f"{case['id']}_{row['case_label']}_repair")
        fail_labels = _collect_fail_labels_from_result(result)
        if result.get("result") in {RESULT_TIMEOUT, RESULT_MEMOUT} or "rows" not in result:
            rows.append(
                {
                    "Case": case["benchmark"],
                    "N": base_metrics["num_qubits"],
                    "Depth": base_metrics["depth"],
                    "Gates": base_metrics["gates"],
                    "Injected": "Yes" if row.get("injected", bool(row.get("injection"))) else "No",
                    "Target": row["case_label"],
                    "Diagnosis": result.get("result", "Error"),
                    "EntangleCheck": "--",
                    "RepairAction": "--",
                    "ReVerify": result.get("result", "Error"),
                    "Output": _format_output_cell(result.get("error") or result.get("result", "Error"), fail_labels),
                    "RepairMode": case.get("repair_mode", "comp"),
                    "raw_log": relpath(raw_path),
                    "representative_run": representative,
                    "generated": generated
                }
            )
            _log(
                f"[{stage}]   done repair {row['case_label']}: output={result.get('result', 'Error')} "
                f"time={float(result.get('runtime_seconds', 0.0)):.3f}s raw={relpath(raw_path)}"
            )
            continue
        entry = result["rows"][0]
        rows.append(
            {
                "Case": case["benchmark"],
                "N": base_metrics["num_qubits"],
                "Depth": base_metrics["depth"],
                "Gates": base_metrics["gates"],
                "Injected": "Yes" if row.get("injected", bool(row.get("injection"))) else "No",
                "Target": row["case_label"],
                "Diagnosis": entry["verify_result"],
                "EntangleCheck": entry["entangle_check"],
                "RepairAction": entry["repair_action"],
                "ReVerify": entry["reverify_result"],
                "Output": _format_output_cell(entry["failure_reason"] or entry["reverify_result"], fail_labels),
                "RepairMode": result.get("repair_mode", case.get("repair_mode", "comp")),
                "raw_log": relpath(raw_path),
                "representative_run": representative,
                "generated": generated
            }
        )
        _log(
            f"[{stage}]   done repair {row['case_label']}: diagnosis={entry['verify_result']} "
            f"reverify={entry['reverify_result']} time={float(result.get('runtime_seconds', 0.0)):.3f}s "
            f"raw={relpath(raw_path)}"
        )
    return rows


def _figure_task_count(figure_cases: list[dict]) -> int:
    total = 0
    for figure in figure_cases:
        if figure["kind"] == "mcx":
            total += sum(len(point.get("backends", figure["backends"])) for point in figure["points"])
        elif figure["kind"] == "grover":
            total += sum(len(series["rounds"]) * len(series.get("backends", figure["backends"])) for series in figure["series"])
    return total


def _grover_working_qubits(total_qubits: int) -> int:
    if total_qubits < 3 or total_qubits % 2 == 0:
        raise ValueError("Grover total qubits must be an odd integer >= 3")
    return (total_qubits + 1) // 2


def _process_figure_cases(figure_cases: list[dict], dirs: dict[str, Path], stage: str = "figure3") -> list[dict]:
    rows = []
    task_total = _figure_task_count(figure_cases)
    task_index = 0
    for figure in figure_cases:
        if figure["kind"] == "mcx":
            for point in figure["points"]:
                qasm_path, generated = materialize_source(point["source"], dirs["generated"] / "figure_mcx")
                metrics = qasm_metrics(qasm_path)
                for backend in point.get("backends", figure["backends"]):
                    task_index += 1
                    _log(
                        f"[{stage}] task {task_index}/{task_total} {figure['id']} kind=mcx "
                        f"x={point['label']} backend={backend} N={metrics['num_qubits']} depth={metrics['depth']}"
                    )
                    result = verify_dirty_safety(
                        backend=backend,
                        qasm=qasm_path,
                        targets=point["targets"],
                        timeout_s=figure.get("timeout_s", 3600),
                        mem_gb=figure.get("mem_gb", 32),
                        metadata={"figure_id": figure["id"], "label": point["label"]},
                    )
                    raw_path = _write_raw_log(dirs["raw"], result, f"{figure['id']}_{point['label']}_{backend}")
                    _log(
                        f"[{stage}]   done {figure['id']} x={point['label']} {backend}: "
                        f"output={result.get('result')} time={float(result.get('runtime_seconds', 0.0)):.3f}s "
                        f"raw={relpath(raw_path)}"
                    )
                    rows.append(
                        {
                            "figure": figure["id"],
                            "kind": figure["kind"],
                            "series": backend,
                            "x": int(point["label"]),
                            "runtime_seconds": float(result.get("runtime_seconds", 0.0)),
                            "result": result.get("result"),
                            "source_qasm": relpath(qasm_path),
                            "generated": generated,
                            "representative_run": False,
                            "raw_log": relpath(raw_path),
                        }
                    )
        elif figure["kind"] == "grover":
            for series in figure["series"]:
                total_qubits = series["total_qubits"]
                working_qubits = _grover_working_qubits(total_qubits)
                for rounds in series["rounds"]:
                    if series.get("source_dir"):
                        source = {
                            "type": "existing",
                            "path": f"{series['source_dir']}/grover_n{total_qubits}_r{rounds}.qasm",
                        }
                    else:
                        source = {
                            "type": "generate",
                            "generator": "grover_rounds",
                            "params": {"total_qubits": total_qubits, "rounds": rounds},
                            "filename": f"grover_n{total_qubits}_r{rounds}.qasm",
                        }
                    qasm_path, generated = materialize_source(source, dirs["generated"] / "figure_grover")
                    targets = ["anc[0]"] if working_qubits > 2 else ["r[0]"]
                    for backend in series.get("backends", figure["backends"]):
                        metrics = qasm_metrics(qasm_path)
                        task_index += 1
                        _log(
                            f"[{stage}] task {task_index}/{task_total} {figure['id']} kind=grover "
                            f"series={series['label']} rounds={rounds} backend={backend} "
                            f"N={metrics['num_qubits']} depth={metrics['depth']}"
                        )
                        result = verify_dirty_safety(
                            backend=backend,
                            qasm=qasm_path,
                            targets=targets,
                            timeout_s=figure.get("timeout_s", 3600),
                            mem_gb=figure.get("mem_gb", 32),
                            metadata={"figure_id": figure["id"], "label": series["label"], "rounds": rounds},
                        )
                        raw_path = _write_raw_log(dirs["raw"], result, f"{figure['id']}_{total_qubits}_{rounds}_{backend}")
                        _log(
                            f"[{stage}]   done {figure['id']} rounds={rounds} {backend}: "
                            f"output={result.get('result')} time={float(result.get('runtime_seconds', 0.0)):.3f}s "
                            f"raw={relpath(raw_path)}"
                        )
                        rows.append(
                            {
                                "figure": figure["id"],
                                "kind": figure["kind"],
                                "series": f"{series['label']} ({backend})",
                                "x": rounds,
                                "runtime_seconds": float(result.get("runtime_seconds", 0.0)),
                                "result": result.get("result"),
                                "source_qasm": relpath(qasm_path),
                                "generated": generated,
                                "representative_run": False,
                                "raw_log": relpath(raw_path),
                            }
                        )
        else:
            raise ValueError(f"Unsupported figure kind: {figure['kind']}")
    return rows


def run_smoke(output_dir: str | None = None, mem_gb: int = DEFAULT_AE_MEM_GB) -> dict:
    manifest = read_json(MANIFEST_PATH)
    dirs = _prepare_dirs(output_dir)
    ensure_quokka_config(output_dir, timeout_s=300)
    smoke_cases = [manifest["table1_main_cases"][0], manifest["table1_main_cases"][13]]
    smoke_results = []
    for index, case in enumerate(smoke_cases, start=1):
        case = dict(case)
        case["timeout_s"] = min(case.get("timeout_s", 300), 300)
        case["mem_gb"] = min(case.get("mem_gb", mem_gb), mem_gb)
        smoke_results.extend(_process_verification_case(case, dirs, stage="smoke", case_index=index, case_total=len(smoke_cases)))

    repair_case = dict(manifest["table2_repair_cases"][0])
    repair_case["rows"] = repair_case["rows"][:1]
    repair_case["timeout_s"] = 300
    repair_case["mem_gb"] = mem_gb
    repair_results = _process_repair_case(repair_case, dirs, stage="smoke-repair", case_index=1, case_total=1)

    payload = {
        "timestamp": time.time(),
        "verification_rows": smoke_results,
        "repair_rows": repair_results,
    }
    summary_path = dirs["processed"] / "smoke_summary.json"
    write_json(summary_path, payload)
    print(f"[smoke] wrote {summary_path}")
    return payload


def _write_stage_results(dirs: dict[str, Path], stage_name: str, payload: dict) -> Path:
    payload = {"timestamp": time.time(), **payload}
    path = dirs["processed"] / f"{stage_name}_results.json"
    write_json(path, payload)
    _log(f"[{stage_name}] wrote {relpath(path)}")
    return path


def _case_with_limits(case: dict, timeout_s: int | None, mem_gb: int | None) -> dict:
    if timeout_s is None and mem_gb is None:
        return case
    updated = dict(case)
    if timeout_s is not None:
        updated["timeout_s"] = timeout_s
    if mem_gb is not None:
        updated["mem_gb"] = mem_gb
    return updated


def run_table1(
    output_dir: str | None = None,
    write_tables: bool = True,
    timeout_s: int = DEFAULT_AE_TIMEOUT_S,
    mem_gb: int = DEFAULT_AE_MEM_GB,
) -> dict:
    manifest = read_json(MANIFEST_PATH)
    dirs = _prepare_dirs(output_dir)
    ensure_quokka_config(output_dir, timeout_s=timeout_s)
    performance_rows = []
    cases = manifest["table1_main_cases"]
    _log(f"[table1] starting {len(cases)} cases with timeout={timeout_s}s mem={mem_gb}GB")
    for index, case in enumerate(cases, start=1):
        case = _case_with_limits(case, timeout_s, mem_gb)
        performance_rows.extend(_process_verification_case(case, dirs, stage="table1", case_index=index, case_total=len(cases)))
        _write_stage_results(dirs, "table1", {"timeout_s": timeout_s, "mem_gb": mem_gb, "performance_rows": performance_rows, "repair_rows": [], "figure_rows": []})
    payload = {"timeout_s": timeout_s, "mem_gb": mem_gb, "performance_rows": performance_rows, "repair_rows": [], "figure_rows": []}
    _write_stage_results(dirs, "table1", payload)
    if write_tables:
        generate_tables(output_dir)
    return payload


def run_table3(
    output_dir: str | None = None,
    write_tables: bool = True,
    timeout_s: int = DEFAULT_AE_TIMEOUT_S,
    mem_gb: int = DEFAULT_AE_MEM_GB,
) -> dict:
    manifest = read_json(MANIFEST_PATH)
    dirs = _prepare_dirs(output_dir)
    ensure_quokka_config(output_dir, timeout_s=timeout_s)
    performance_rows = []
    cases = manifest["table3_appendix_cases"]
    _log(f"[table3] starting {len(cases)} cases with timeout={timeout_s}s mem={mem_gb}GB")
    for index, case in enumerate(cases, start=1):
        case = _case_with_limits(case, timeout_s, mem_gb)
        performance_rows.extend(_process_verification_case(case, dirs, stage="table3", case_index=index, case_total=len(cases)))
        _write_stage_results(dirs, "table3", {"timeout_s": timeout_s, "mem_gb": mem_gb, "performance_rows": performance_rows, "repair_rows": [], "figure_rows": []})
    payload = {"timeout_s": timeout_s, "mem_gb": mem_gb, "performance_rows": performance_rows, "repair_rows": [], "figure_rows": []}
    _write_stage_results(dirs, "table3", payload)
    if write_tables:
        generate_tables(output_dir)
    return payload


def run_table2(
    output_dir: str | None = None,
    write_tables: bool = True,
    timeout_s: int = DEFAULT_AE_TIMEOUT_S,
    mem_gb: int = DEFAULT_AE_MEM_GB,
) -> dict:
    manifest = read_json(MANIFEST_PATH)
    dirs = _prepare_dirs(output_dir)
    ensure_quokka_config(output_dir, timeout_s=timeout_s)
    repair_rows = []
    cases = manifest["table2_repair_cases"]
    _log(f"[table2] starting {len(cases)} repair cases with timeout={timeout_s}s mem={mem_gb}GB")
    for index, case in enumerate(cases, start=1):
        case = _case_with_limits(case, timeout_s, mem_gb)
        repair_rows.extend(_process_repair_case(case, dirs, stage="table2", case_index=index, case_total=len(cases)))
        _write_stage_results(dirs, "table2", {"timeout_s": timeout_s, "mem_gb": mem_gb, "performance_rows": [], "repair_rows": repair_rows, "figure_rows": []})
    payload = {"timeout_s": timeout_s, "mem_gb": mem_gb, "performance_rows": [], "repair_rows": repair_rows, "figure_rows": []}
    _write_stage_results(dirs, "table2", payload)
    if write_tables:
        generate_tables(output_dir)
    return payload


def run_figure3(
    output_dir: str | None = None,
    write_tables: bool = True,
    timeout_s: int = DEFAULT_AE_TIMEOUT_S,
    mem_gb: int = DEFAULT_AE_MEM_GB,
) -> dict:
    manifest = read_json(MANIFEST_PATH)
    dirs = _prepare_dirs(output_dir)
    ensure_quokka_config(output_dir, timeout_s=timeout_s)
    _log(f"[figure3] starting {len(manifest['figure3_cases'])} figure groups with timeout={timeout_s}s mem={mem_gb}GB")
    figure_rows = []
    for figure in manifest["figure3_cases"]:
        figure = _case_with_limits(figure, timeout_s, mem_gb)
        figure_rows.extend(_process_figure_cases([figure], dirs, stage="figure3"))
        _write_stage_results(dirs, "figure3", {"timeout_s": timeout_s, "mem_gb": mem_gb, "performance_rows": [], "repair_rows": [], "figure_rows": figure_rows})
    payload = {"timeout_s": timeout_s, "mem_gb": mem_gb, "performance_rows": [], "repair_rows": [], "figure_rows": figure_rows}
    _write_stage_results(dirs, "figure3", payload)
    if write_tables:
        generate_tables(output_dir)
    return payload


def run_all(output_dir: str | None = None, timeout_s: int = DEFAULT_AE_TIMEOUT_S, mem_gb: int = DEFAULT_AE_MEM_GB) -> dict:
    dirs = _prepare_dirs(output_dir)
    _log(f"[all] starting staged full artifact run with timeout={timeout_s}s mem={mem_gb}GB: table1 -> table2 -> figure3 -> table3")
    table1_payload = run_table1(output_dir, write_tables=False, timeout_s=timeout_s, mem_gb=mem_gb)
    table2_payload = run_table2(output_dir, write_tables=False, timeout_s=timeout_s, mem_gb=mem_gb)
    figure_payload = run_figure3(output_dir, write_tables=False, timeout_s=timeout_s, mem_gb=mem_gb)
    table3_payload = run_table3(output_dir, write_tables=False, timeout_s=timeout_s, mem_gb=mem_gb)
    payload = {
        "timestamp": time.time(),
        "timeout_s": timeout_s,
        "mem_gb": mem_gb,
        "performance_rows": table1_payload["performance_rows"] + table3_payload["performance_rows"],
        "repair_rows": table2_payload["repair_rows"],
        "figure_rows": figure_payload["figure_rows"],
    }
    full_path = dirs["processed"] / "all_results.json"
    write_json(full_path, payload)
    _log(f"[all] wrote {relpath(full_path)}")
    generate_tables(output_dir)
    return payload


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _performance_table_rows(case_defs: list[dict], perf_rows: list[dict]) -> list[dict]:
    by_row_backend: dict[tuple[str, str], dict] = {}
    for row in perf_rows:
        by_row_backend[(row["row_id"], row["backend"])] = row

    backend_specs = [
        ("matrix", "Matrix"),
        ("quokka", "Quokka-Sharp"),
        ("qcec", "QCEC"),
    ]
    table_rows = []
    for case in case_defs:
        row = {
            "Benchmark": case["benchmark"],
            "N": "",
            "Depth": "",
        }
        any_backend_row = None
        for backend_key, backend_label in backend_specs:
            backend_row = by_row_backend.get((case["id"], backend_key))
            if backend_row is not None and any_backend_row is None:
                any_backend_row = backend_row
            row[f"{backend_label} Time"] = backend_row["time_seconds"] if backend_row is not None else "--"
            row[f"{backend_label} Output"] = backend_row["output"] if backend_row is not None else "--"
        if any_backend_row is not None:
            row["N"] = any_backend_row["N"]
            row["Depth"] = any_backend_row["Depth"]
        elif case.get("source", {}).get("type") == "existing":
            metrics = qasm_metrics(case["source"]["path"])
            row["N"] = metrics["num_qubits"]
            row["Depth"] = metrics["depth"]
        table_rows.append(row)
    return table_rows


def _repair_table_rows(repair_rows: list[dict]) -> list[dict]:
    case_rows: dict[str, list[dict]] = {}
    for row in repair_rows:
        case_rows.setdefault(str(row["Case"]), []).append(row)

    raw_fail_lists: dict[tuple[str, str], list[str]] = {}
    for case_name, rows in case_rows.items():
        target_to_label = {row["Target"]: row["Target"] for row in rows}
        for row in rows:
            raw_log = row.get("raw_log")
            if not raw_log:
                continue
            data = _safe_read_raw_log(raw_log)
            fail_labels: list[str] = []
            pipeline = data.get("pipeline", {})
            for item in pipeline.get("Faillist", []) or []:
                qref = item.get("qubit ref")
                if not qref:
                    continue
                for raw_row in rows:
                    if raw_row.get("Target") and raw_row.get("raw_log") == raw_log:
                        pass
                if qref.startswith("anc["):
                    label = "a_" + qref.split("[", 1)[1][:-1]
                    fail_labels.append(label)
                elif qref.startswith("q["):
                    label = "a_" + qref.split("[", 1)[1][:-1]
                    fail_labels.append(label)
            ordered = []
            seen = set()
            for candidate in [r["Target"] for r in rows]:
                if candidate in fail_labels and candidate not in seen:
                    seen.add(candidate)
                    ordered.append(candidate)
            if ordered:
                raw_fail_lists[(case_name, row["Target"])] = ordered

    return [
        {
            "Case": row["Case"],
            "N": row["N"],
            "Depth": row["Depth"],
            "Gates": row["Gates"],
            "Injected": row["Injected"],
            "Target": row["Target"],
            "Diagnosis": row["Diagnosis"],
            "Entangle Check": row["EntangleCheck"],
            "Repair Action": row["RepairAction"],
            "ReVerify": row["ReVerify"],
            "Output": (
                "FailList: {" + ", ".join(raw_fail_lists[(str(row["Case"]), row["Target"])]) + "}"
                if (str(row["Case"]), row["Target"]) in raw_fail_lists
                else row["Output"]
            ),
            "Repair Mode": row.get("RepairMode", "comp"),
        }
        for row in repair_rows
    ]


def _load_results_payload(dirs: dict[str, Path]) -> dict:
    stage_names = ["table1", "table2", "figure3", "table3"]
    stage_paths = [dirs["processed"] / f"{name}_results.json" for name in stage_names]
    payload = {"performance_rows": [], "repair_rows": [], "figure_rows": [], "source_files": []}
    if any(path.exists() for path in stage_paths):
        for path in stage_paths:
            if not path.exists():
                continue
            stage_payload = read_json(path)
            payload["performance_rows"].extend(stage_payload.get("performance_rows", []))
            payload["repair_rows"].extend(stage_payload.get("repair_rows", []))
            payload["figure_rows"].extend(stage_payload.get("figure_rows", []))
            payload["source_files"].append(relpath(path))
        return payload

    results_path = dirs["processed"] / "all_results.json"
    if not results_path.exists():
        raise FileNotFoundError(
            f"No experiment results found under {dirs['processed']}. "
            "Run ./run_all_experiments.sh table1/table2/figure3/table3 first."
        )
    full_payload = read_json(results_path)
    return {
        "performance_rows": full_payload.get("performance_rows", []),
        "repair_rows": full_payload.get("repair_rows", []),
        "figure_rows": full_payload.get("figure_rows", []),
        "source_files": [relpath(results_path)],
    }


def _raw_log_path(raw_log: str) -> Path:
    path = Path(raw_log)
    if path.is_absolute():
        return path
    return (repo_root() / path).resolve()


def _safe_read_raw_log(raw_log: str) -> dict:
    try:
        return read_json(_raw_log_path(raw_log))
    except Exception:
        return {}


def _case_ids(manifest: dict) -> set[str]:
    return {
        case["id"]
        for group in ("table1_main_cases", "table3_appendix_cases")
        for case in manifest.get(group, [])
    }


def _raw_log_fallback_row(case: dict, backend: str) -> dict | None:
    raw_path = repo_root() / "results" / "raw" / f"{case['id']}_{backend}.json"
    if not raw_path.exists():
        return None
    payload = _safe_read_raw_log(str(raw_path))
    if not payload:
        return None
    qasm_path = payload.get("qasm")
    metrics = qasm_metrics(qasm_path) if qasm_path else {"num_qubits": "", "depth": "", "gates": ""}
    target = ""
    target_results = payload.get("target_results") or []
    if target_results:
        target = target_results[0].get("target", "")
    elif payload.get("targets"):
        first_target = payload["targets"][0]
        if isinstance(first_target, dict):
            target = first_target.get("ref", "")
        else:
            target = str(first_target)
    return {
        "row_id": case["id"],
        "benchmark": case["benchmark"],
        "N": metrics["num_qubits"],
        "Depth": metrics["depth"],
        "Gates": metrics["gates"],
        "backend": backend,
        "time_seconds": round(float(payload.get("runtime_seconds", 0.0)), 4),
        "output": payload.get("result", "--"),
        "target": target or (case.get("targets") or [""])[0],
        "source_qasm": relpath(qasm_path) if qasm_path else "",
        "generated": False,
        "representative_run": False,
        "raw_log": relpath(raw_path),
    }


def _active_performance_rows(manifest: dict, perf_rows: list[dict]) -> list[dict]:
    active_case_map = {
        case["id"]: case
        for group in ("table1_main_cases", "table3_appendix_cases")
        for case in manifest.get(group, [])
    }
    filtered = [row for row in perf_rows if row["row_id"] in active_case_map]
    by_key = {(row["row_id"], row["backend"]): row for row in filtered}
    for case_id, case in active_case_map.items():
        for backend in case.get("backends", []):
            key = (case_id, backend)
            fallback = _raw_log_fallback_row(case, backend)
            if fallback is not None:
                if key in by_key:
                    filtered = [row for row in filtered if (row["row_id"], row["backend"]) != key]
                filtered.append(fallback)
                by_key[key] = fallback
            elif key in by_key:
                continue
    return filtered


def _backend_diagnostic_rows(perf_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    by_row: dict[str, dict[str, dict]] = {}
    for row in perf_rows:
        by_row.setdefault(row["row_id"], {})[row["backend"]] = row

    backend_specs = [
        ("matrix", "Matrix"),
        ("quokka", "Quokka-Sharp"),
        ("qcec", "QCEC"),
    ]
    disagreements = []
    qcec_inconclusive = []
    for row_id, backend_rows in sorted(by_row.items()):
        outputs = {backend: row.get("output") for backend, row in backend_rows.items()}
        conclusive_outputs = {
            backend: output
            for backend, output in outputs.items()
            if output not in RESOURCE_OR_INFRA_OUTPUTS and output is not None
        }
        if len(set(conclusive_outputs.values())) > 1:
            exemplar = next(iter(backend_rows.values()))
            disagreements.append(
                {
                    "row_id": row_id,
                    "benchmark": exemplar.get("benchmark", ""),
                    "N": exemplar.get("N", ""),
                    "Depth": exemplar.get("Depth", ""),
                    "target": exemplar.get("target", ""),
                    "Matrix Output": outputs.get("matrix", "--"),
                    "Quokka-Sharp Output": outputs.get("quokka", "--"),
                    "QCEC Output": outputs.get("qcec", "--"),
                    "Matrix Raw Log": backend_rows.get("matrix", {}).get("raw_log", "--"),
                    "Quokka-Sharp Raw Log": backend_rows.get("quokka", {}).get("raw_log", "--"),
                    "QCEC Raw Log": backend_rows.get("qcec", {}).get("raw_log", "--"),
                    "kind": "non_resource_backend_disagreement",
                }
            )

        qcec_row = backend_rows.get("qcec")
        if not qcec_row:
            continue
        raw_payload = _safe_read_raw_log(qcec_row.get("raw_log", ""))
        for target_result in raw_payload.get("target_results", []):
            diagnostic_text = "\n".join(
                str(target_result.get(field, ""))
                for field in ["qcec_z_stdout", "qcec_z_stderr", "qcec_x_stdout", "qcec_x_stderr"]
                if target_result.get(field)
            )
            is_inconclusive = bool(target_result.get("qcec_inconclusive")) or "no conclusion can be drawn" in diagnostic_text.lower()
            if not is_inconclusive:
                continue
            excerpt = " ".join(diagnostic_text.split())[:240]
            qcec_inconclusive.append(
                {
                    "row_id": row_id,
                    "benchmark": qcec_row.get("benchmark", ""),
                    "N": qcec_row.get("N", ""),
                    "Depth": qcec_row.get("Depth", ""),
                    "target": target_result.get("target", qcec_row.get("target", "")),
                    "qcec_z_equivalence": target_result.get("qcec_z_equivalence", ""),
                    "qcec_x_equivalence": target_result.get("qcec_x_equivalence", ""),
                    "diagnostic_excerpt": excerpt,
                    "raw_log": qcec_row.get("raw_log", ""),
                }
            )
    return disagreements, qcec_inconclusive


def generate_tables(output_dir: str | None = None) -> dict:
    dirs = _prepare_dirs(output_dir)
    payload = _load_results_payload(dirs)
    manifest = read_json(MANIFEST_PATH)

    perf_rows = [row for row in payload["performance_rows"] if row["backend"] != "injection"]
    perf_rows = _active_performance_rows(manifest, perf_rows)
    table1_rows = _performance_table_rows(manifest["table1_main_cases"], perf_rows)
    table2_rows = _repair_table_rows(payload["repair_rows"])
    table3_rows = _performance_table_rows(manifest["table3_appendix_cases"], perf_rows)
    disagreement_rows, qcec_inconclusive_rows = _backend_diagnostic_rows(perf_rows)

    table1_csv = dirs["processed"] / "table1.csv"
    table2_csv = dirs["processed"] / "table2.csv"
    table3_csv = dirs["processed"] / "table3.csv"
    disagreement_csv = dirs["processed"] / "backend_disagreements.csv"
    qcec_inconclusive_csv = dirs["processed"] / "qcec_inconclusive.csv"
    figure_csv = dirs["figures"] / "figure3.csv"
    _write_csv(table1_csv, PERFORMANCE_FIELDNAMES, table1_rows)
    _write_csv(table2_csv, REPAIR_FIELDNAMES, table2_rows)
    _write_csv(table3_csv, PERFORMANCE_FIELDNAMES, table3_rows)
    _write_csv(disagreement_csv, BACKEND_DISAGREEMENT_FIELDNAMES, disagreement_rows)
    _write_csv(qcec_inconclusive_csv, QCEC_INCONCLUSIVE_FIELDNAMES, qcec_inconclusive_rows)
    _write_csv(figure_csv, FIGURE_FIELDNAMES, payload["figure_rows"])

    try:
        import matplotlib.pyplot as plt
    except Exception as exc:
        plot_note = f"matplotlib unavailable: {exc}"
    else:
        plot_note = "plots generated"
        _plot_figures(payload["figure_rows"], dirs["figures"])

    summary_md = dirs["processed"] / "summary.md"
    lines = [
        "# Artifact Summary",
        "",
        "## Outputs",
        f"- Table 1: `{relpath(table1_csv)}`",
        f"- Table 2: `{relpath(table2_csv)}`",
        f"- Table 3: `{relpath(table3_csv)}`",
        f"- Figure 3 data: `{relpath(figure_csv)}`",
        f"- Figure 3 images: `{relpath(dirs['figures'] / 'figure3.png')}`, `{relpath(dirs['figures'] / 'figure3.pdf')}`",
        f"- Backend disagreements: `{relpath(disagreement_csv)}`",
        f"- QCEC inconclusive diagnostics: `{relpath(qcec_inconclusive_csv)}`",
        "",
        "## Notes",
        f"- Result source files: {', '.join(payload['source_files'])}",
        f"- Default staged/full limits: timeout `{DEFAULT_AE_TIMEOUT_S}s`, memory `{DEFAULT_AE_MEM_GB}GB`; paper-budget reruns can use `{PAPER_TIMEOUT_S}s` and `{PAPER_MEM_GB}GB`.",
        f"- {plot_note}",
        f"- Table 1 rows: {len(table1_rows)}",
        f"- Table 2 rows: {len(table2_rows)}",
        f"- Table 3 rows: {len(table3_rows)}",
        f"- Non-resource backend disagreements: {len(disagreement_rows)}",
        f"- QCEC inconclusive diagnostics: {len(qcec_inconclusive_rows)}",
        "- Raw JSON logs retain `representative_run` metadata when an artifact-friendly substitute instance is used.",
        "- Random-circuit depth/runtime may differ from the paper while preserving the same benchmark family and scale trend."
    ]
    summary_md.write_text("\n".join(lines) + "\n")
    print(f"[tables] wrote {summary_md}")
    return {
        "table1": str(table1_csv),
        "table2": str(table2_csv),
        "table3": str(table3_csv),
        "figure3": str(figure_csv),
        "backend_disagreements": str(disagreement_csv),
        "qcec_inconclusive": str(qcec_inconclusive_csv),
        "summary": str(summary_md),
    }


def _plot_figures(rows: list[dict], figure_dir: Path) -> None:
    import matplotlib.pyplot as plt

    figure_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    mcx_rows = [row for row in rows if row["kind"] == "mcx" and row["result"] not in {RESULT_TIMEOUT, RESULT_MEMOUT}]
    grover_rows = [row for row in rows if row["kind"] == "grover" and row["result"] not in {RESULT_TIMEOUT, RESULT_MEMOUT}]

    for backend in sorted({row["series"] for row in mcx_rows}):
        backend_rows = sorted((row for row in mcx_rows if row["series"] == backend), key=lambda item: item["x"])
        axes[0].plot([row["x"] for row in backend_rows], [row["runtime_seconds"] for row in backend_rows], marker="o", label=backend)
    axes[0].set_title("MCX")
    axes[0].set_xlabel("Total Qubits")
    axes[0].set_ylabel("Time (s)")
    axes[0].grid(True)
    axes[0].legend()

    for series in sorted({row["series"] for row in grover_rows}):
        series_rows = sorted((row for row in grover_rows if row["series"] == series), key=lambda item: item["x"])
        axes[1].plot([row["x"] for row in series_rows], [row["runtime_seconds"] for row in series_rows], marker="o", label=series)
    axes[1].set_title("Grover")
    axes[1].set_xlabel("Rounds")
    axes[1].set_ylabel("Time (s)")
    axes[1].set_yscale("log")
    axes[1].grid(True)
    axes[1].legend(fontsize=7)

    fig.tight_layout()
    fig.savefig(figure_dir / "figure3.png", dpi=200)
    fig.savefig(figure_dir / "figure3.pdf")
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CAV 2026 artifact runner")
    parser.add_argument("command", choices=["smoke", "all", "table1", "table2", "figure3", "table3", "generate-tables"])
    parser.add_argument("--output-dir", default=None)
    parser.add_argument(
        "--timeout-s",
        type=int,
        default=DEFAULT_AE_TIMEOUT_S,
        help=(
            f"Per-task timeout for staged/full artifact runs. "
            f"Default is {DEFAULT_AE_TIMEOUT_S}s to match the paper timeout budget; "
            "use a smaller value such as 420s for a fast reviewer-friendly run."
        ),
    )
    parser.add_argument(
        "--mem-gb",
        type=int,
        default=DEFAULT_AE_MEM_GB,
        help=(
            f"Per-task address-space memory limit. Default is {DEFAULT_AE_MEM_GB}GB for full-suite stability; "
            f"use {PAPER_MEM_GB}GB to reproduce the paper memory budget or isolated large-case rechecks."
        ),
    )
    args = parser.parse_args(argv)

    if args.command == "smoke":
        run_smoke(args.output_dir, mem_gb=args.mem_gb)
    elif args.command == "all":
        run_all(args.output_dir, timeout_s=args.timeout_s, mem_gb=args.mem_gb)
    elif args.command == "table1":
        run_table1(args.output_dir, timeout_s=args.timeout_s, mem_gb=args.mem_gb)
    elif args.command == "table2":
        run_table2(args.output_dir, timeout_s=args.timeout_s, mem_gb=args.mem_gb)
    elif args.command == "figure3":
        run_figure3(args.output_dir, timeout_s=args.timeout_s, mem_gb=args.mem_gb)
    elif args.command == "table3":
        run_table3(args.output_dir, timeout_s=args.timeout_s, mem_gb=args.mem_gb)
    elif args.command == "generate-tables":
        generate_tables(args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
