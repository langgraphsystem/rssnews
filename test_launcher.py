#!/usr/bin/env python3
"""Test launcher.py command generation"""
import os

test_modes = {
    "poll": {"SERVICE_MODE": "poll"},
    "work": {"SERVICE_MODE": "work"},
    "chunking": {"SERVICE_MODE": "chunking"},
    "openai-migration": {"SERVICE_MODE": "openai-migration"},
}

print("🔍 Тестирование launcher.py для всех режимов:\n")

for mode_name, env_vars in test_modes.items():
    # Set env vars
    for key, value in env_vars.items():
        os.environ[key] = value

    # Import launcher
    import launcher
    cmd = launcher.build_command()

    print(f"✅ {mode_name:20} -> {cmd}")

    # Clean up
    for key in env_vars:
        if key in os.environ:
            del os.environ[key]
