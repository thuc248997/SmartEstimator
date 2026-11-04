"""Pure, deterministic cost engine. No Django imports here.

Input: a Snapshot (dataclasses). Output: an EngineResult with per-line results, resource totals,
the Bảng 3.8 summary, warnings and an output hash. Same snapshot + ENGINE_VERSION → same output hash.
"""

from .core import ENGINE_VERSION, EngineResult, run
from .snapshot import LineInput, NormLine, PriceInput, ProjectParams, ResourceRef, Snapshot

__all__ = [
    "ENGINE_VERSION",
    "EngineResult",
    "LineInput",
    "NormLine",
    "PriceInput",
    "ProjectParams",
    "ResourceRef",
    "Snapshot",
    "run",
]
