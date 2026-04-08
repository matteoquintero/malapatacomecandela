# mpc/acquisition/ — BC2: Adquisición
# Responsabilidad: convertir un candidato en un archivo válido.
from mpc.acquisition.engine import DownloadEngine, DownloadConfig
from mpc.acquisition.request import DownloadRequest
from mpc.acquisition.result import DownloadResult, DownloadStatus, DownloadError
from mpc.acquisition.events import TrackDownloaded, TrackSkipped
from mpc.acquisition.use_cases import DownloadTrackUseCase, DownloadBatchUseCase

__all__ = [
    "DownloadEngine", "DownloadConfig",
    "DownloadRequest",
    "DownloadResult", "DownloadStatus", "DownloadError",
    "TrackDownloaded", "TrackSkipped",
    "DownloadTrackUseCase", "DownloadBatchUseCase",
]
