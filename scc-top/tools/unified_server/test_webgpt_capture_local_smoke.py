from __future__ import annotations

from pathlib import Path


def test_webgpt_archive_intake_and_export_smoke(tmp_path: Path):
    # Use a tmp repo_root-like layout but reuse real code paths.
    # We intentionally write into a temp docs root to avoid polluting the repo docs during tests.
    repo_root = tmp_path / "repo"
    (repo_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (repo_root / "docs").mkdir(parents=True, exist_ok=True)

    # Import after creating dirs (service will create artifacts/webgpt DB).
    from tools.unified_server.services.webgpt_archive_service import WebGPTArchiveService

    svc = WebGPTArchiveService(repo_root=repo_root)
    res = svc.intake(
        conversation_id="c_test_001",
        title="WebGPT Capture Smoke",
        source="pytest",
        messages=[
            {"role": "user", "content_text": "需求：把网页对话落盘成文档", "content_json": None, "message_id": "m1"},
            {"role": "assistant", "content_text": "收到。我会实现 intake + export。", "content_json": {"code_blocks": ["print('ok')"]}, "message_id": "m2"},
        ],
    )
    assert res.inserted >= 2

    out = svc.export_markdown(conversation_id="c_test_001", docs_root=(repo_root / "docs" / "INPUTS" / "WEBGPT"))
    assert out["ok"] is True
    assert (repo_root / out["doc_path"]).exists()
    assert (repo_root / out["index_path"]).exists()

