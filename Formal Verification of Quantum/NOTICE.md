# Provenance and Third-Party Notices

This artifact accompanies the paper "Formal Verification of Quantum Ancilla
Safety" by Jiqi Li and Jingyi Mei.

## Quokka-Sharp Core

The bundled `quokka_sharp/quokka_sharp/` package contains Quokka-Sharp core
functionality based on work by Jingyi Mei, Dekel Zak, Tim Coopmans, and Alfons
Laarman. This includes the original Quokka-Sharp simulation, verification,
equivalence-checking, synthesis, and CNF-encoding infrastructure.

The original Quokka-Sharp copyright notice is preserved in `LICENSE`.

## Ancilla-Safety Artifact Contributions

The artifact-level implementation for "Formal Verification of Quantum Ancilla
Safety" was developed by Jiqi Li and Jingyi Mei. These contributions include
the artifact evaluation workflow, Docker packaging, benchmark mapping, dirty
ancilla verification wrappers, repair pipeline integration, generated table and
figure scripts, and the computational-basis repair extension
`quokka_sharp/quokka_sharp/repair_computational.py`.

Some of these extensions live inside the `quokka_sharp/` source tree so that
they can reuse Quokka-Sharp internal APIs. Their location in that package does
not change the provenance described here.

## GPMC

The `third_party/GPMC/` directory contains vendored GPMC source code from
https://github.com/System-Verification-Lab/GPMC at upstream commit
`df1aea7769887b62f59b803293678a1bbc5fe06d`. GPMC is distributed under the
license terms included in `third_party/GPMC/LICENSE.md`.

