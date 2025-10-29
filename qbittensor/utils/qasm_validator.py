from __future__ import annotations

import re
from typing import Optional, Set

from qbittensor.miner.providers.base import Capability


_OPENQASM_HEADER_RE = re.compile(r"^\s*OPENQASM\s+\d+(?:\.\d+)?\s*;", re.IGNORECASE)
_QREG_RE = re.compile(r"^\s*qreg\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\[(\d+)\]\s*;", re.IGNORECASE)
_GATE_CALL_RE = re.compile(
    r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\[\d+\](?:\s*,\s*[a-zA-Z_][a-zA-Z0-9_]*\s*\[\d+\])*\s*;",
    re.IGNORECASE,
)


def is_openqasm(source: str) -> bool:
    """Return True if the source appears to be OpenQASM (v2/v3) by header."""
    if not source:
        return False
    first_line = source.splitlines()[0] if source.splitlines() else source
    return bool(_OPENQASM_HEADER_RE.match(first_line))


def extract_num_qubits(source: str) -> Optional[int]:
    """Extract total qubits declared in qreg statements (max across qregs)."""
    num = 0
    for line in source.splitlines():
        m = _QREG_RE.match(line)
        if m:
            size = int(m.group(2))
            num = max(num, size)
    return num or None


def extract_gate_names(source: str) -> Set[str]:
    """Extract gate names used as calls."""
    names: Set[str] = set()
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Skip non-unitary and declarations
        first = stripped.split()[0].lower()
        if first in {"openqasm", "include", "qreg", "creg", "gate", "opaque", "if", "for", "while", "measure", "barrier", "reset"}:
            continue
        m = _GATE_CALL_RE.match(line)
        if m:
            names.add(m.group(1).lower())
    return names


def validate_against_capability(source: str, capability: Capability) -> None:
    """Validate OpenQASM against device capability. Raises ValueError on violation.

    Checks:
    - Declared qubits do not exceed capability.num_qubits (if provided)
    - All called gates are within capability.basis_gates (if provided)
    """
    # Qubits
    declared = extract_num_qubits(source)
    if declared is not None and capability.num_qubits is not None:
        if declared > capability.num_qubits:
            raise ValueError(
                f"Circuit requires {declared} qubits, device supports {capability.num_qubits}"
            )

    # Gates
    used_gates = extract_gate_names(source)
    if capability.basis_gates:
        basis = {g.lower() for g in capability.basis_gates}
        # Common non-unitary statements to ignore
        ignored = {"measure", "barrier", "reset"}
        unknown = {g for g in used_gates if g not in basis and g not in ignored}
        if unknown:
            raise ValueError(f"Unsupported gate(s) for device: {sorted(unknown)}; basis={sorted(basis)}")


