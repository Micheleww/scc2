from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from tools.scc.chat_store import SCCChatStore
from tools.scc.capabilities.context_pins import PinRequestItem, build_pins
from tools.scc.capabilities.mentions import parse_mentions


@dataclass(frozen=True)
class ContextPack:
    ok: bool
    chat_id: str
    summary: str
    messages: List[Dict[str, Any]]
    pins: List[Dict[str, Any]]
    stats: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _norm_rel_path(path: str, *, repo_path: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    Normalize a potentially absolute/relative path into a safe repo-relative POSIX path.
    Returns (rel, error). If error is not None, rel will be None.
    """
    raw = str(path or "").strip()
    if not raw:
        return None, "empty_path"

    p = Path(raw)
    if p.is_absolute():
        try:
            rel = p.resolve().relative_to(Path(repo_path).resolve())
            return rel.as_posix(), None
        except Exception:
            return None, "absolute_outside_repo"

    rel = raw.replace("\\", "/").lstrip("/").strip()
    if not rel:
        return None, "empty_path"
    if ".." in rel.split("/"):
        return None, "invalid_path"
    return rel, None


def _normalize_scope_allow(scope_allow: Optional[Iterable[str]]) -> List[str]:
    out: List[str] = []
    for s in list(scope_allow or []):
        pref = str(s or "").strip().replace("\\", "/").strip("/")
        if not pref:
            continue
        if pref not in out:
            out.append(pref)
    return out


def _in_scope_allow(*, rel_path: str, scope_allow: List[str]) -> bool:
    if not scope_allow:
        return True
    p = str(rel_path or "").replace("\\", "/").lstrip("/").strip()
    if not p:
        return False
    for pref in scope_allow:
        if p == pref or p.startswith(pref + "/"):
            return True
    return False


def _dedupe_pin_items(items: Iterable[PinRequestItem]) -> List[PinRequestItem]:
    seen: set[Tuple[str, str, Optional[int], Optional[int]]] = set()
    out: List[PinRequestItem] = []
    for it in items:
        k = (
            str(it.path or "").replace("\\", "/"),
            str(it.kind or "file").lower(),
            it.start_line,
            it.end_line,
        )
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _pin_items_from_messages(*, messages: List[Dict[str, Any]], repo_path: Path) -> List[PinRequestItem]:
    """
    Best-effort extraction:
    - from @file mentions (supports @path, @path:10-20, @path#L10-L20)
    - from message.meta.pin_items / message.meta.pins (list of dicts)
    """
    out: List[PinRequestItem] = []

    for m in messages or []:
        content = str(m.get("content") or "")

        parsed = parse_mentions(content, repo_root=repo_path)
        for fm in parsed.file_mentions:
            rel, err = _norm_rel_path(str(fm.get("path") or ""), repo_path=repo_path)
            if err or not rel:
                continue
            start_line = fm.get("start_line")
            end_line = fm.get("end_line")
            if start_line is not None:
                out.append(
                    PinRequestItem(
                        path=rel,
                        kind="range",
                        start_line=start_line,
                        end_line=end_line,
                        label=str(fm.get("label") or "mention"),
                    )
                )
            else:
                out.append(PinRequestItem(path=rel, kind="file", label=str(fm.get("label") or "mention")))

        meta = m.get("meta") if isinstance(m.get("meta"), dict) else {}
        for key in ("pin_items", "pins"):
            pin_list = meta.get(key)
            if not isinstance(pin_list, list):
                continue
            for it in pin_list[:200]:
                if not isinstance(it, dict):
                    continue
                rel, err = _norm_rel_path(str(it.get("path") or ""), repo_path=repo_path)
                if err or not rel:
                    continue
                out.append(
                    PinRequestItem(
                        path=rel,
                        kind=str(it.get("kind") or "file"),
                        start_line=it.get("start_line"),
                        end_line=it.get("end_line"),
                        label=str(it.get("label") or key),
                    )
                )

    return _dedupe_pin_items(out)


def build_context_pack(
    *,
    repo_root: Path,
    chat_id: str,
    tail: int = 40,
    pin_repo_path: Optional[Path] = None,
    pin_items: Optional[List[PinRequestItem]] = None,
    scope_allow: Optional[List[str]] = None,
    include_pin_content: bool = True,
    max_chars_per_pin: int = 8000,
    max_total_pin_chars: int = 50_000,
    write_artifact: bool = True,
) -> ContextPack:
    """
    Deterministic token-saving strategy pack:
    - summary (long-term memory, stable)
    - last N messages (short-term context)
    - optional pins (precise code/file slices)

    This does NOT call any model.
    """
    store = SCCChatStore(repo_root=repo_root)
    snap = store.snapshot(chat_id=chat_id, tail=tail)
    summary = str(snap.get("summary") or "")
    messages = list(snap.get("messages") or [])

    pins: List[Dict[str, Any]] = []
    pin_errors: List[Dict[str, Any]] = []

    pin_repo = (pin_repo_path or repo_root).resolve()
    if scope_allow is None:
        try:
            meta = store.create(chat_id=str(chat_id)).get("meta") or {}
            if isinstance(meta, dict) and isinstance(meta.get("scope_allow"), list):
                scope_allow = meta.get("scope_allow")
        except Exception:
            pass
    if scope_allow is None:
        for m in reversed(messages or []):
            meta = m.get("meta") if isinstance(m.get("meta"), dict) else {}
            if isinstance(meta.get("scope_allow"), list):
                scope_allow = meta.get("scope_allow")
                break

    allow = _normalize_scope_allow(scope_allow)

    merged_items: List[PinRequestItem] = []
    for it in list(pin_items or []):
        rel, err = _norm_rel_path(it.path, repo_path=pin_repo)
        if err or not rel:
            pin_errors.append({"path": str(it.path or ""), "error": err or "invalid_path"})
            continue
        if not _in_scope_allow(rel_path=rel, scope_allow=allow):
            pin_errors.append({"path": rel, "error": "not_in_scope_allow"})
            continue
        merged_items.append(
            PinRequestItem(
                path=rel,
                kind=str(it.kind or "file"),
                start_line=it.start_line,
                end_line=it.end_line,
                label=str(it.label or ""),
            )
        )

    # auto-pins from the chat tail: @file mentions / meta pins
    for it in _pin_items_from_messages(messages=messages, repo_path=pin_repo):
        if not _in_scope_allow(rel_path=it.path, scope_allow=allow):
            pin_errors.append({"path": it.path, "error": "not_in_scope_allow"})
            continue
        merged_items.append(it)

    merged_items = _dedupe_pin_items(merged_items)

    if merged_items:
        res = build_pins(
            repo_path=pin_repo,
            items=merged_items,
            include_content=include_pin_content,
            max_chars_per_item=max_chars_per_pin,
            max_total_chars=max_total_pin_chars,
        )
        d = res.to_dict()
        pins = list(d.get("pins") or [])
        pin_errors.extend(list(d.get("errors") or []))

    approx_chars = len(summary) + sum(len(str(m.get("content") or "")) for m in messages)
    approx_chars += sum(len(str(p.get("content") or "")) for p in pins)

    pack = ContextPack(
        ok=True,
        chat_id=str(chat_id),
        summary=summary,
        messages=messages,
        pins=pins,
        stats={
            "tail": int(tail),
            "messages_count": len(messages),
            "pins_count": len(pins),
            "pin_items_count": len(merged_items),
            "scope_allow": allow,
            "pin_errors": pin_errors,
            "approx_chars_total": approx_chars,
        },
    )

    if write_artifact:
        try:
            store.write_context_pack(chat_id=str(chat_id), context_pack=pack.to_dict())
        except Exception:
            pass

    return pack
