"""
Unified model registry + routing helpers.

Goals:
- Discover models available from local CLIs (Codex/OpenCode).
- Persist a normalized registry for later use by routing / orchestration.
- Route by task difficulty to reduce token spend while staying reliable.
"""
