"""Public package surface for Epistemic CI."""

from .core import BINDING_SCHEMA, OBSERVATION_SCHEMA, RESULT_SCHEMA, CheckResult, run_all

__all__ = [
    "BINDING_SCHEMA",
    "OBSERVATION_SCHEMA",
    "RESULT_SCHEMA",
    "CheckResult",
    "run_all",
]
__version__ = "0.2.0"
