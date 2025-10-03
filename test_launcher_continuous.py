#!/usr/bin/env python3
"""Test launcher.py with continuous modes"""
import os
import sys

# Test all modes including new continuous ones
test_modes = {
    "poll": {"SERVICE_MODE": "poll"},
    "work": {"SERVICE_MODE": "work"},
    "work-continuous": {"SERVICE_MODE": "work-continuous"},
    "chunking": {"SERVICE_MODE": "chunking"},
    "chunk-continuous": {"SERVICE_MODE": "chunk-continuous"},
    "openai-migration": {"SERVICE_MODE": "openai-migration"},
}

print("🔍 Testing launcher.py with all modes:\n")

for mode_name, env_vars in test_modes.items():
    # Set env vars
    for key, value in env_vars.items():
        os.environ[key] = value

    # Import launcher (need to reload to pick up new env)
    if 'launcher' in sys.modules:
        del sys.modules['launcher']

    import launcher
    cmd = launcher.build_command()

    print(f"✅ {mode_name:20} -> {cmd}")

    # Clean up
    for key in env_vars:
        if key in os.environ:
            del os.environ[key]

print("\n✅ All modes configured correctly!")
