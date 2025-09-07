"""Stage 6 Hybrid Chunking Package.

Avoid heavy imports at module import time to keep tests lightweight.
Use lazy attribute access if needed.
"""

__all__ = [
    "Stage6Pipeline",
    "ChunkProcessor",
    "BatchCoordinator",
]

def __getattr__(name):
    if name == "Stage6Pipeline":
        from .pipeline import Stage6Pipeline
        return Stage6Pipeline
    if name == "ChunkProcessor":
        from .processor import ChunkProcessor
        return ChunkProcessor
    if name == "BatchCoordinator":
        from .coordinator import BatchCoordinator
        return BatchCoordinator
    raise AttributeError(name)
