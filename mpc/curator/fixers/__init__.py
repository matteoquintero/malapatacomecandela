# mpc/curator/fixers/__init__.py
from mpc.curator.fixers.thumbnails import ThumbnailFixer
from mpc.curator.fixers.tags import TagFixer
from mpc.curator.fixers.duplicates import DuplicateFixer
from mpc.curator.fixers.genres import GenreFixer
from mpc.curator.fixers.reconcile import ReconcileFixer
from mpc.curator.fixers.backfill import AudioSourceBackfiller, MbidBackfiller
from mpc.curator.fixers.metadata import MetadataFixer
from mpc.curator.fixers.video_thumbnails import VideoThumbnailFixer

__all__ = [
    "ThumbnailFixer", "TagFixer", "DuplicateFixer", "GenreFixer",
    "ReconcileFixer", "AudioSourceBackfiller", "MbidBackfiller",
    "MetadataFixer", "VideoThumbnailFixer",
]
