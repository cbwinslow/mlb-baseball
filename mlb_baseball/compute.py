"""Compute device detection with automatic CPU fallback.

Provides a simple interface to check GPU availability (Numba CUDA)
and select the appropriate compute device. The K40/K80 GPUs support
compute capability 3.5/3.7, which is compatible with Numba CUDA
but not modern XGBoost/PyTorch.

Set MLB_FORCE_CPU=1 to disable GPU even when available.
"""

import logging
import os

logger = logging.getLogger(__name__)

_FORCE_CPU = os.environ.get("MLB_FORCE_CPU", "").lower() in ("1", "true", "yes")


def gpu_available() -> bool:
    """Check if Numba CUDA is available and not force-disabled."""
    if _FORCE_CPU:
        return False
    try:
        from numba import cuda  # type: ignore[import-untyped]

        return cuda.is_available()
    except ImportError:
        return False


def get_device() -> str:
    """Return 'cuda' or 'cpu'."""
    if gpu_available():
        logger.info("GPU detected, using CUDA acceleration")
        return "cuda"
    logger.info("Using CPU (set MLB_FORCE_CPU=0 and install numba for GPU)")
    return "cpu"


def device_info() -> dict[str, object]:
    """Return diagnostic information about compute devices."""
    info: dict[str, object] = {
        "device": get_device(),
        "force_cpu": _FORCE_CPU,
    }
    try:
        from numba import cuda  # type: ignore[import-untyped]

        info["numba_available"] = True
        info["cuda_available"] = cuda.is_available()
        if cuda.is_available():
            gpus = []
            for gpu in cuda.gpus:
                gpus.append(
                    {
                        "name": gpu.name.decode() if isinstance(gpu.name, bytes) else str(gpu.name),
                        "compute_capability": gpu.compute_capability,
                    }
                )
            info["gpus"] = gpus
    except ImportError:
        info["numba_available"] = False
        info["cuda_available"] = False
    return info
