"""Public package surface for Epistemic CI."""

from .core import OBSERVATION_SCHEMA, RESULT_SCHEMA, CheckResult, run_all

__all__ = ["OBSERVATION_SCHEMA", "RESULT_SCHEMA", "CheckResult", "run_all"]
__version__ = "0.1.0"
