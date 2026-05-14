# CAV 2026 Artifact: Formal Verification of Quantum Ancilla Safety

This repository packages the artifact for the paper "Formal Verification of Quantum Ancilla Safety" for CAV 2026 Artifact Evaluation. It integrates:

- dirty-ancilla verification with three backends: `Matrix`, `Quokka-Sharp`, `QCEC`
- an end-to-end `verify -> repair -> reverify` pipeline implemented on top of Quokka-Sharp
- repair backends in both computational basis and Pauli basis, with computational-basis repair used by default in the artifact
- reproducible error injection with fixed random seeds
- one-click scripts to reproduce the paper tables and figure

The artifact is structured to follow the CAV 2026 AE smoke-test/full-review workflow and the ACM artifact badging expectations. In particular, it provides:

- a fast smoke test
- a full evaluation script
- structured logs under `results/`
- generated CSV tables and Figure 3 data/plots

Archival DOI for this artifact version: https://doi.org/10.5281/zenodo.19784589

## Artifact Evaluation Metadata

Claimed badges:

- Functional: requested. The artifact provides a Docker-based workflow, a smoke test, staged table/figure scripts, and raw/processed outputs for the paper claims.
- Reusable: requested. The artifact includes source code, benchmark inputs, vendored GPMC source, documented extension points, and a permissive license.
- Available: requested. The artifact is archived at the version-specific DOI listed above.

Functional justification:

- The Docker image contains all runtime tools needed for the AE workflow: Python, Qiskit, NumPy, Matplotlib, MQT QCEC, Quokka-Sharp, and GPMC.
- The smoke test was run successfully in the Docker image with `docker run --rm ancilla-ae:latest ./run_kick_the_tires.sh`.
- The staged scripts reproduce the artifact outputs corresponding to the paper's main tables and Figure 3.
- The artifact records per-case raw JSON logs, generated CSV files, summary files, and disagreement diagnostics under `results/`.

Reusable justification:

- The repository includes the implementation source under `quokka_sharp/` and `ae/`, benchmark inputs under `benchmarks/` and `benchmark_for_tables/`, and runner scripts for smoke, staged, and full evaluations.
- GPMC is included as vendored source under `third_party/GPMC/` at upstream commit `df1aea7769887b62f59b803293678a1bbc5fe06d`; Docker builds compile it natively for the target container architecture.
- The project license is included in `LICENSE`, and provenance details are provided in `NOTICE.md`.
- New benchmarks can be added to the benchmark folders and registered in `ae/manifest.json`; tables can be regenerated with `python3 generate_tables.py`.
- Outside Docker, users can install the Python package from `./quokka_sharp`, build GPMC from `third_party/GPMC/`, set `GPMC_PATH`, and run the same scripts. Docker remains the recommended path for review reproducibility.

Replicated claims:

- Table 1 representative backend comparison.
- Table 2 verify-repair-reverify experiments.
- Figure 3 data and plots.
- Table 3 appendix/backend comparison data.

Not replicated exactly:

- Random generator families may not reproduce every paper depth/runtime value line by line. The artifact uses fixed or same-family representative instances and marks representative runs in the generated outputs.
- Very large boundary cases may report `Timeout` or `Memout` depending on host memory, CPU load, and configured timeout/memory budget; raw logs preserve the observed result.

Resource requirements:

- Recommended RAM: at least `24GB` available to Docker for the default staged/full workflow; `32GB` is recommended for paper-budget confirmations of large cases.
- CPU cores: at least 4 cores recommended; more cores can improve wall-clock time for long runs, but backend subprocesses are still bounded by the configured timeout and memory policy.
- Smoke test time: typically under 5 minutes in the Docker image on the tested host.
- Full review time: hardware-dependent and potentially long; the default per-task timeout is `3600s`, and reviewers may run staged scripts independently.

External connectivity:

- Runtime: no network access required after the Docker image is built or loaded.
- `amd64` path with the provided image archive: no network access is required to load and run `artifact/image.tar.gz`.
- Rebuild path, including `arm64`: network access is required only to pull the Docker base image and install Debian/Python dependencies during `docker build`; GPMC itself is built from vendored source and is not downloaded during review.

Tested artifact target:

- Linux `x86_64` / `amd64`
- Linux `arm64`, by building the Docker image from the included source package
- Docker-based execution as the primary review path
- no network access required at runtime inside the container
- network access required only when building the Docker image to fetch the base image and Python wheels
- on Windows, Docker Desktop with WSL2 integration enabled for the current Ubuntu distribution
- Docker/WSL memory available to the container should be at least `24GB` for the default full-suite path; use at least `32GB` for paper-budget large-case confirmations

## Repository Layout

- `ae/`: unified artifact-evaluation API, manifest, generators, and experiment runner
- `benchmarks/`: benchmark families used by the paper
- `quokka_sharp/`: bundled Quokka-Sharp backend plus ancilla-safety extensions used by this artifact
- `run_kick_the_tires.sh`: smoke test entrypoint
- `run_all_experiments.sh`: one-click full evaluation entrypoint
- `run_table1.sh`, `run_table2.sh`, `run_figure3.sh`, `run_table3.sh`: staged review entrypoints
- `generate_tables.py`: regenerate tables/figure outputs from raw logs

## Provenance and Licensing

This artifact combines the Quokka-Sharp backend with new artifact-level code
for "Formal Verification of Quantum Ancilla Safety".

- The original Quokka-Sharp core is based on work by Jingyi Mei, Dekel Zak, Tim Coopmans, and Alfons Laarman.
- The ancilla-safety artifact contributions were developed by Jiqi Li and Jingyi Mei. These include the AE workflow, dirty-ancilla wrappers, repair pipeline integration, Docker packaging, benchmark mapping, and the computational-basis repair extension `quokka_sharp/quokka_sharp/repair_computational.py`.
- GPMC is vendored under `third_party/GPMC/` and is governed by its own license in `third_party/GPMC/LICENSE.md`.
- Copyright and license notices are in `LICENSE`; detailed provenance and third-party notices are in `NOTICE.md`.

Some ancilla-safety extensions live inside the `quokka_sharp/` package so that
they can call Quokka-Sharp internal APIs directly. This packaging choice does
not mean the whole artifact is the original Quokka-Sharp project; the artifact
itself is for the paper "Formal Verification of Quantum Ancilla Safety".

## Recommended Docker Review Path

Docker is the recommended AE path. The submitted zip contains both a complete
source tree and an optional prebuilt `amd64` Docker image archive at
`artifact/image.tar.gz`.

Before running the full artifact, configure Docker Desktop or the Docker host
with enough resources:

- RAM: at least `24GB` for the default staged/full workflow; `32GB` for paper-budget large-case confirmations.
- CPU cores: at least 4 cores recommended.
- Network: not needed at runtime after loading or building the image. Rebuilding, including on `arm64`, needs network only for the Docker base image and Debian/Python dependencies.

### 1. Prepare the Docker image

After unpacking the submitted zip, run the following commands from the artifact
root directory, the directory containing this `README.md` and `Dockerfile`.

On `amd64` hosts, reviewers can load the prebuilt image:

```bash
docker load < artifact/image.tar.gz
```

On `arm64` hosts, or if rebuilding is preferred, build from the included source
tree so that GPMC is compiled natively for the container architecture:

```bash
docker build -t ancilla-ae:latest .
```

### 2. Run the smoke test

```bash
mkdir -p results
docker run --rm -it -v "$PWD/results:/workspace/results" ancilla-ae:latest ./run_kick_the_tires.sh
```

Expected behavior:

- verifies at least one small benchmark with `Matrix`, `Quokka-Sharp`, and `QCEC`
- runs one small Quokka repair case
- writes smoke-test logs to `results/raw/`
- writes a smoke summary to `results/processed/smoke_summary.json`

Target runtime: under 5 minutes in the Docker image.

### 3. Run staged artifact outputs

The staged workflow is recommended for review because each stage can be run and
inspected independently:

```bash
mkdir -p results
docker run --rm -it -v "$PWD/results:/workspace/results" ancilla-ae:latest ./run_table1.sh --timeout-s 420
docker run --rm -it -v "$PWD/results:/workspace/results" ancilla-ae:latest ./run_table2.sh --timeout-s 420
docker run --rm -it -v "$PWD/results:/workspace/results" ancilla-ae:latest ./run_figure3.sh --timeout-s 420
docker run --rm -it -v "$PWD/results:/workspace/results" ancilla-ae:latest ./run_table3.sh --timeout-s 420
```

With the fast reviewer-friendly `420s` timeout, measured staged runtimes on the
authors' Docker/WSL host are approximately: Table 1 around 1 hour, Table 2
around 10 minutes, Figure 3 around 12 minutes, and Table 3 longer than Table 1
but under 2 hours. These fast staged runs are intended for AE practicality and
produce about 80% of the large-table data on the authors' host.

For paper-budget confirmation of a selected stage, use the default `3600s`
timeout and optionally the `32GB` memory budget:

```bash
docker run --rm -it -v "$PWD/results:/workspace/results" ancilla-ae:latest ./run_all_experiments.sh table3 --timeout-s 3600 --mem-gb 32
```

To run all stages in one command:

```bash
mkdir -p results
docker run --rm -it -v "$PWD/results:/workspace/results" ancilla-ae:latest ./run_all_experiments.sh
```

### 4. Inspect outputs on the host

The commands above mount `results/` from the host into the container, so outputs
are available locally after each run:

```bash
ls results/processed
ls results/figures
```

The main generated files are:

- `results/processed/table1.csv`
- `results/processed/table2.csv`
- `results/processed/table3.csv`
- `results/processed/summary.md`
- `results/figures/figure3.csv`
- `results/figures/figure3.png`
- `results/figures/figure3.pdf`

Reviewers can open `results/figures/figure3.png` or
`results/figures/figure3.pdf` directly on the host.

If a run was executed without a bind mount, copy results out of a named
container before removing it:

```bash
docker run --name ancilla-ae-run -it ancilla-ae:latest ./run_figure3.sh
docker cp ancilla-ae-run:/workspace/results ./results
docker rm ancilla-ae-run
```

To regenerate tables and plots from existing raw logs:

```bash
docker run --rm -it -v "$PWD/results:/workspace/results" ancilla-ae:latest python3 generate_tables.py
```

## Output Mapping

The artifact writes outputs to:

- `results/raw/`: raw per-case JSON logs
- `results/processed/table1.csv`: main backend-comparison table
- `results/processed/table2.csv`: verify-repair-reverify table
- `results/processed/table3.csv`: appendix backend-comparison table
- `results/figures/figure3.csv`: Figure 3 plotting data
- `results/figures/figure3.png`: raster plot for Figure 3
- `results/figures/figure3.pdf`: vector plot for Figure 3
- `results/processed/backend_disagreements.csv`: cases where non-resource backend outputs disagree
- `results/processed/qcec_inconclusive.csv`: QCEC internal inconclusive diagnostics, including ZX/simulation disagreement messages
- `results/processed/summary.md`: high-level run summary and notes
- `generated/injected/`: QASM files created by explicit random/error injection
- `generated/repaired/`: repaired QASM files and the corresponding generated ancilla target files

The Docker image does not include precomputed `results/`. Reviewers generate `results/` by running the smoke test, a staged table/figure script, or the full evaluation script.

Mapping to the paper:

- `table1.csv` corresponds to the main backend-comparison table in the paper body
- `table2.csv` corresponds to the verify-repair-reverify table in the paper body
- `figure3.csv` / `figure3.png` / `figure3.pdf` correspond to Figure 3 in the paper body
- `table3.csv` corresponds to the large appendix comparison table
- `benchmark_for_tables/table1/`, `benchmark_for_tables/table2/`, `benchmark_for_tables/table3/`, and `benchmark_for_tables/figure3/` store the fixed paper-mapping benchmark files used by the artifact
- These fixed QASM benchmark instances define the paper-to-artifact mapping used by `ae/manifest.json`; runtime generators are used only for explicitly marked representative/fallback cases.
- Figure 3 Grover labels use total qubits `N`; for these circuits `N = 2w - 1`, where `w` is the Grover working-register size.

## Reproducible Error Injection

Repair experiments use deterministic error injection driven by seeds stored in `ae/manifest.json`.

Properties:

- the same seed always yields the same injected gates and angles
- injected gates are appended at the end of the target circuit
- supported injection modes:
- `logic_only`: gates from `{x, rx(theta)}`
- `phase_only`: gates from `{z, rz(theta), s, t}`
- `entangling_only`: gate set `{cx}`, with the selected ancilla used as the control and a second qubit chosen as the target
- `hybrid`: contains both logic and phase components
- `arbitrary`: gates from `{x, y, z, h, s, t, rx(theta), rz(theta), cx}`

Angles are sampled from `[0, pi]`.

## Representative Runs and Random Benchmarks

Some benchmark families are generator-based. For those cases:

- the artifact may generate a same-family/same-scale representative instance at runtime
- depth and runtime may differ from the exact paper values
- such rows are marked with `representative_run=True` in the generated outputs

This is especially relevant for:

- random circuits
- identity-random circuits
- very large instances that are not practical for a normal AE time budget

The default timeout used by one-click staged/full AE scripts is `3600s` per task, matching the paper timeout budget. The default memory limit is `24GB` per backend subprocess; reviewers can request the paper memory budget with `--mem-gb 32` for any stage or for the full run. For quick debugging or reviewer-friendly staged runs, use `--timeout-s 420`; on the authors' host this fast setting completes Table 1 in about 1 hour, Table 2 in about 10 minutes, Figure 3 in about 12 minutes, and Table 3 in under 2 hours while producing about 80% of the large-table data.

## Resource-Boundary Cases

Some large instances are close to the practical memory or runtime boundary on commodity review machines. This is most visible for QCEC on large MCX-style circuits, for Quokka-Sharp on the largest MCX instances, and for Grover instances when the optional fast `420s` timeout is used. These cases can be sensitive to transient host load, OS memory pressure, and whether they are run as part of a long full-suite execution or as an isolated single benchmark.

For that reason, a `Timeout` or `Memout` on such a boundary case should be read as an environment-dependent resource limit unless the raw logs also show a semantic backend disagreement. The artifact keeps per-case JSON logs under `results/raw/` and reports non-resource disagreements separately in `results/processed/backend_disagreements.csv`.

If a large case fails only in the full staged run, we recommend rerunning that stage or rerunning the individual benchmark on an otherwise idle machine before treating the result as a tool-level failure. For example, the `Grover` `N=9` Table 1 instance may finish under the default paper timeout but still hit the optional fast `420s` timeout on some hosts. The CSV files report the actual observed run result; the paper-timeout and memory policy can be requested with `--timeout-s 3600 --mem-gb 32` when a longer confirmation run is desired.

The largest Table 3 rows, `MCX 7999` and `MCX 9999`, are best confirmed as isolated Quokka-Sharp runs under the paper memory budget. A default full-suite run with `--mem-gb 24` may conservatively report a resource failure for these largest MCX instances; use `--timeout-s 3600 --mem-gb 32` for an isolated paper-budget confirmation.

## Repair Backend

The integrated repair pipeline now supports two repair modes:

- `comp`: computational-basis repair
- `pauli`: Pauli-basis repair

The artifact defaults to `comp` because it avoids CCX expansion and is typically much faster on MCX-heavy and Grover-style benchmarks. This default is recorded per Table 2 case in `ae/manifest.json` and exported in generated repair-table rows as `RepairMode`.

Verification remains unchanged:

- all backend comparison experiments still use the same dirty-safe diagnosis interface
- only the Quokka-based repair pipeline is affected by the repair backend choice

Repair actions in `table2.csv` are reported in the canonical single-qubit form used by the repair synthesizer, `Rz(a); Rx(b); Rz(c)`. This is an output convention rather than a minimal gate-count claim. Some non-hybrid repairs that appear as three gates are equivalent to a single-axis rotation after simplification. For example, a logic repair reported as `Rz(-pi); Rx(theta); Rz(pi)` is equal to `Rx(-theta)` up to the usual global-phase convention. The raw logs keep the explicit angles so this equivalence can be checked directly.

## Table 2 Fixed Benchmark Mapping

For the verify-repair-reverify table, the artifact now prefers the fixed paper-aligned QASM files in:

- `benchmark_for_tables/table2/`

These files take precedence over runtime random injection for the main Table 2 reproduction path. If the observed diagnosis differs from the paper text, the artifact reports the actual code result in the generated CSV/summary rather than forcing the paper label.

When a Table 2 benchmark verifies multiple targets, the artifact writes all targets into one pipeline invocation rather than launching one pipeline per target. The raw log is shared across the corresponding CSV rows, which keeps the review run faster while preserving per-target table entries.

The Table 2 `Identity Random` row uses a small fixed injected `s1` representative that preserves the intended repair behavior: `a_1` remains in the fail list while `a_2` is repaired. This avoids a larger identity-random instance that can hit the fast AE timeout without changing the repair scenario being demonstrated.

For the appendix comparison table, the artifact similarly uses fixed sources collected in:

- `benchmark_for_tables/table3/`

Notes for the appendix table:

- `Identity Random` uses unmodified `s1` representative instances. The appendix uses `N=5,6,7` to match the stable Table 1 mapping; injected identity-random instances are reserved for Table 2 repair evaluation.
- `Pure Random` uses fixed instances at `N=30`, `N=50`, and `N=70` from `benchmark_for_tables/table3/`.
- The current AE configuration maps these rows to `random_q30_g60_s0.qasm`, `random_q50_g100_s0.qasm`, and `random_q70_g70_s0.qasm`.

## Docker Image Details

The image installs:

- Python 3.11
- `qiskit`, `numpy`, `matplotlib`, `mqt.qcec`
- Quokka-Sharp from the local `quokka_sharp/` package
- `GPMC` under `/opt/gpmc/bin/gpmc`

The Docker build compiles `GPMC` from the vendored source in `third_party/GPMC/` during image construction, then copies the resulting executable into the final image. The vendored source is pinned to upstream commit `df1aea7769887b62f59b803293678a1bbc5fe06d`, so the build does not need to download GPMC during AE review. Compiling inside Docker also lets `amd64` and `arm64` reviewers build a native solver for their container architecture instead of relying on a prebuilt `x86-64` binary.

To regenerate the prebuilt image archive after rebuilding locally:

```bash
docker save ancilla-ae:latest | gzip > artifact/image.tar.gz
```

## Quokka Solver Configuration

The artifact runner writes a Quokka configuration file to:

- `results/processed/quokka_config.json`

It expects the GPMC binary at:

- `/opt/gpmc/bin/gpmc`

This is the default path configured by the Dockerfile. You can override it locally with:

```bash
export GPMC_PATH=/custom/path/to/gpmc
```

## Optional Local Source Execution

Docker is the recommended review path. Local execution outside Docker is
optional and requires installing the dependencies manually:

- Python 3.10+
- Qiskit
- NumPy
- Matplotlib
- `mqt.qcec`
- Quokka-Sharp Python package from `./quokka_sharp`
- GPMC for Quokka-Sharp, either from the Docker build or from a local build of `third_party/GPMC`

For a local source build of GPMC:

```bash
cd third_party/GPMC
sh ./build.sh r
cd ../..
export GPMC_PATH="$PWD/third_party/GPMC/bin/gpmc"
pip install ./quokka_sharp
```

After that, the same entrypoints can be used outside Docker, subject to the
local Python and solver environment:

```bash
./run_kick_the_tires.sh
./run_table1.sh --timeout-s 420
./run_table2.sh --timeout-s 420
./run_figure3.sh --timeout-s 420
./run_table3.sh --timeout-s 420
python3 generate_tables.py
```

## Known Limitations

- Only Quokka-Sharp supports repair; `Matrix` and `QCEC` are verification-only backends.
- Large cases may timeout or use representative runs depending on artifact practicality.
- Randomly generated benchmark families may not match the exact paper depth/runtime values line-by-line, but remain in-family and same-scale.

## Troubleshooting

- If Quokka fails immediately, check whether `GPMC_PATH` is correct or the Docker build finished successfully.
- If QCEC is missing outside Docker, install `mqt.qcec` or use the Docker image.
- If QCEC reports an internal ZX/simulation disagreement, the artifact captures that backend diagnostic in the raw JSON log and lists it in `results/processed/qcec_inconclusive.csv`.
- If a large MCX or Grover-family benchmark reports `Timeout` or `Memout`, check the corresponding raw JSON log and consider an isolated rerun on an idle machine or with `--timeout-s 3600 --mem-gb 32`. Resource failures near the configured limit do not by themselves indicate a semantic mismatch between backends.
- If backend outputs disagree after excluding `Timeout`, `Memout`, and setup errors, inspect `results/processed/backend_disagreements.csv`.
- If plots are not generated, check whether `matplotlib` is installed.
- If a run is interrupted, rerun `python3 generate_tables.py` after raw logs are available.

## Packaging Checklist

Before final artifact submission, make sure the final package also includes:

- `LICENSE`
- this `README.md`
- `Dockerfile`, `.dockerignore`, benchmark folders, runner scripts, and `third_party/GPMC/`
- Docker image archive such as `image.tar.gz`
- DOI information for the archival upload: https://doi.org/10.5281/zenodo.19784589
- SHA256 checksum of the packaged artifact
- any conference-specific metadata requested by the CAV AE submission form
