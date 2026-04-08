# mpc/download/__init__.py — compat shim → mpc.acquisition
# Este módulo se mantiene solo para compatibilidad con imports antiguos.
# El código nuevo debe importar desde mpc.acquisition.*
from mpc.acquisition.request import DownloadRequest
from mpc.acquisition.result import DownloadResult, DownloadStatus, DownloadError
from mpc.acquisition.engine import DownloadEngine, DownloadConfig

__all__ = [
    "DownloadEngine", "DownloadConfig",
    "DownloadRequest",
    "DownloadResult", "DownloadStatus", "DownloadError",
]
