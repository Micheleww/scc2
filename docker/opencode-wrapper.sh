#!/bin/sh
# opencode wrapper script for Linux container
# This script wraps the Windows opencode-cli.exe using wine or box86

# Check if wine is available
if command -v wine64 >/dev/null 2>&1; then
    exec wine64 /opt/opencode/opencode-cli.exe "$@"
elif command -v wine >/dev/null 2>&1; then
    exec wine /opt/opencode/opencode-cli.exe "$@"
else
    echo "Error: wine is not installed. Cannot run Windows binary on Linux." >&2
    echo "Please install wine or use a Windows container." >&2
    exit 1
fi
