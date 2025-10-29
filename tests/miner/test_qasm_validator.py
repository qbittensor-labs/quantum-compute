import pytest

from qbittensor.miner.providers.base import Capability
from qbittensor.utils.qasm_validator import is_openqasm, extract_num_qubits, extract_gate_names, validate_against_capability


def test_qasm_detection():
    assert is_openqasm("OPENQASM 2.0;\nqreg q[2];")
    assert not is_openqasm("H;CX;MEASURE")


def test_extracts():
    src = """OPENQASM 2.0;\nqreg q[3];\nx q[0];\nrz q[1];\ncx q[0], q[2];\n"""
    assert extract_num_qubits(src) == 3
    gates = extract_gate_names(src)
    assert {"x", "rz", "cx"}.issubset(gates)


def test_validate_ok():
    src = """OPENQASM 2.0;\nqreg q[2];\nx q[0];\ncx q[0], q[1];\n"""
    cap = Capability(num_qubits=4, basis_gates=["x", "y", "z", "cx"], extras=None)
    validate_against_capability(src, cap)


def test_validate_qubits_exceeded():
    src = """OPENQASM 2.0;\nqreg q[5];\nx q[0];\n"""
    cap = Capability(num_qubits=4, basis_gates=["x"], extras=None)
    with pytest.raises(ValueError):
        validate_against_capability(src, cap)


def test_validate_unsupported_gates():
    src = """OPENQASM 2.0;\nqreg q[2];\nrz q[0];\n"""
    cap = Capability(num_qubits=4, basis_gates=["x", "y", "z", "cx"], extras=None)
    with pytest.raises(ValueError):
        validate_against_capability(src, cap)


