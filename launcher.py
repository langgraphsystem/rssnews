"""
Universal launcher for Railway deployments.

Selects a start command based on SERVICE_MODE env var so that multiple
services can share the same repository and root railway.toml.

Supported SERVICE_MODE values:
  - poll               -> python main.py poll --workers {POLL_WORKERS} --batch-size {POLL_BATCH}
  - work               -> python main.py work [--simplified] --workers {WORK_WORKERS} --batch-size {WORK_BATCH}
  - embedding          -> python main.py services run-once --services embedding --embedding-batch {EMBEDDING_BATCH}
  - chunking           -> python main.py services run-once --services chunking --chunking-batch {CHUNKING_BATCH}
  - openai-migration   -> python services/openai_embedding_migration_service.py continuous --interval {MIGRATION_INTERVAL}

Default SERVICE_MODE: openai-migration (keeps backward compatibility until services set explicit modes).
"""

import os
import shlex
import subprocess
import sys


def build_command() -> str:
    mode = os.getenv("SERVICE_MODE", "openai-migration").strip().lower()

    # Common parameters from env with sane defaults
    poll_workers = os.getenv("POLL_WORKERS", "10")
    poll_batch = os.getenv("POLL_BATCH", "10")

    work_workers = os.getenv("WORK_WORKERS", "10")
    work_batch = os.getenv("WORK_BATCH", "50")
    work_simplified = os.getenv("WORK_SIMPLIFIED", "false").lower() == "true"

    emb_batch = os.getenv("EMBEDDING_BATCH", "1000")
    chunk_batch = os.getenv("CHUNKING_BATCH", "100")

    mig_interval = os.getenv("MIGRATION_INTERVAL", "60")

    if mode == "poll":
        return f"python main.py poll --workers {poll_workers} --batch-size {poll_batch}"

    if mode == "work":
        simplified_flag = " --simplified" if work_simplified else ""
        return f"python main.py work{simplified_flag} --workers {work_workers} --batch-size {work_batch}"

    if mode == "embedding":
        return f"python main.py services run-once --services embedding --embedding-batch {emb_batch}"

    if mode == "chunking":
        return f"python main.py services run-once --services chunking --chunking-batch {chunk_batch}"

    if mode == "openai-migration":
        return f"python services/openai_embedding_migration_service.py continuous --interval {mig_interval}"

    # Fallback: print help and exit non-zero
    print(f"Unsupported SERVICE_MODE='{mode}'. Supported: poll|work|embedding|chunking|openai-migration", file=sys.stderr)
    sys.exit(2)


def main():
    cmd = build_command()
    print(f"launcher.py -> executing: {cmd}")
    # Use shell=True for compatibility with Railway container images
    proc = subprocess.run(cmd, shell=True)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()

