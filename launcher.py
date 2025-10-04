"""
Universal launcher for Railway deployments.

Selects a start command based on SERVICE_MODE env var so that multiple
services can share the same repository and root railway.toml.

Supported SERVICE_MODE values:
  - poll               -> python main.py poll --workers {POLL_WORKERS} --batch-size {POLL_BATCH}
  - work               -> python main.py work [--simplified] --workers {WORK_WORKERS} --batch-size {WORK_BATCH}
  - work-continuous    -> python services/work_continuous_service.py --interval {WORK_CONTINUOUS_INTERVAL} --batch {WORK_CONTINUOUS_BATCH}
  - embedding          -> python main.py services run-once --services embedding --embedding-batch {EMBEDDING_BATCH}
  - chunking           -> python main.py services run-once --services chunking --chunking-batch {CHUNKING_BATCH}
  - chunk-continuous   -> python services/chunk_continuous_service.py --interval {CHUNK_CONTINUOUS_INTERVAL} --batch {CHUNK_CONTINUOUS_BATCH}
  - openai-migration   -> python services/openai_embedding_migration_service.py --interval {MIGRATION_INTERVAL}
  - bot                -> python start_telegram_bot.py

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

    work_continuous_interval = os.getenv("WORK_CONTINUOUS_INTERVAL", "30")
    work_continuous_batch = os.getenv("WORK_CONTINUOUS_BATCH", "50")

    emb_batch = os.getenv("EMBEDDING_BATCH", "1000")

    chunk_batch = os.getenv("CHUNKING_BATCH", "100")
    chunk_continuous_interval = os.getenv("CHUNK_CONTINUOUS_INTERVAL", "30")
    chunk_continuous_batch = os.getenv("CHUNK_CONTINUOUS_BATCH", "100")

    mig_interval = os.getenv("MIGRATION_INTERVAL", "60")
    # OpenAI embedding migration batch size (fallback to service default 100)
    mig_batch = os.getenv("OPENAI_EMBEDDING_BATCH_SIZE", os.getenv("MIGRATION_BATCH", "100"))

    if mode == "poll":
        return f"python main.py poll --workers {poll_workers} --batch-size {poll_batch}"

    if mode == "work":
        simplified_flag = " --simplified" if work_simplified else ""
        return f"python main.py work{simplified_flag} --workers {work_workers} --batch-size {work_batch}"

    if mode == "work-continuous":
        return f"python services/work_continuous_service.py --interval {work_continuous_interval} --batch {work_continuous_batch}"

    if mode == "embedding":
        return f"python main.py services run-once --services embedding --embedding-batch {emb_batch}"

    if mode == "chunking":
        return f"python main.py services run-once --services chunking --chunking-batch {chunk_batch}"

    if mode == "chunk-continuous":
        return f"python services/chunk_continuous_service.py --interval {chunk_continuous_interval} --batch {chunk_continuous_batch}"

    if mode == "openai-migration":
        # Default to continuous mode; the migration service requires a subcommand
        return f"python services/openai_embedding_migration_service.py continuous --interval {mig_interval} --batch-size {mig_batch}"

    if mode == "bot":
        return "python start_telegram_bot.py"

    # Fallback: print help and exit non-zero
    print(f"Unsupported SERVICE_MODE='{mode}'. Supported: poll|work|work-continuous|embedding|chunking|chunk-continuous|openai-migration|bot", file=sys.stderr)
    sys.exit(2)


def main():
    cmd = build_command()
    print(f"launcher.py -> executing: {cmd}")
    # Use shell=True for compatibility with Railway container images
    proc = subprocess.run(cmd, shell=True)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
