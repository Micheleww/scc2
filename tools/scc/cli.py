#!/usr/bin/env python3
"""Unified CLI entry point for SCC tools.

This module provides a single entry point for all SCC tools,
eliminating the need for multiple standalone scripts.

Usage:
    python -m tools.scc.cli <command> [options]
    sccctl <command> [options]

Commands:
    gates       Run CI gates
    validate    Validate contracts and schemas
    ops         Run operations (sync, publish, etc.)
    runtime     Run child tasks and orchestration
    map         Map-related operations
    selftest    Run self-tests
"""
from __future__ import annotations

import argparse
import sys
from typing import Any

from tools.scc.lib.utils import load_json, norm_rel


def cmd_gates(args: argparse.Namespace) -> int:
    """Run CI gates."""
    from tools.scc.gates import run_ci_gates
    errors = run_ci_gates.main()
    return 1 if errors else 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate contracts and schemas."""
    if args.subcommand == "contracts":
        from tools.scc.selftest import validate_contract_examples
        return validate_contract_examples.main()
    elif args.subcommand == "release":
        from tools.scc.selftest import validate_release_record
        return validate_release_record.main()
    else:
        print(f"Unknown validate subcommand: {args.subcommand}")
        return 1


def cmd_ops(args: argparse.Namespace) -> int:
    """Run operations."""
    if args.subcommand == "patterns-sync":
        from tools.scc.ops import patterns_registry_sync
        return patterns_registry_sync.main()
    elif args.subcommand == "playbooks-sync":
        from tools.scc.ops import playbooks_registry_sync
        return playbooks_registry_sync.main()
    elif args.subcommand == "skills-sync":
        from tools.scc.ops import skills_drafts_registry_sync
        return skills_drafts_registry_sync.main()
    elif args.subcommand == "playbook-publish":
        from tools.scc.ops import playbook_publisher
        return playbook_publisher.main()
    elif args.subcommand == "playbook-stage":
        from tools.scc.ops import playbook_stage
        return playbook_stage.main()
    elif args.subcommand == "playbook-rollback":
        from tools.scc.ops import playbook_rollback
        return playbook_rollback.main()
    elif args.subcommand == "release-integrate":
        from tools.scc.ops import release_integrate
        return release_integrate.main()
    elif args.subcommand == "metrics-rollup":
        from tools.scc.ops import metrics_rollup
        return metrics_rollup.main()
    elif args.subcommand == "board-maintenance":
        from tools.scc.ops import board_maintenance
        return board_maintenance.main()
    elif args.subcommand == "eval-replay":
        from tools.scc.ops import eval_replay
        return eval_replay.main()
    elif args.subcommand == "ssot-sync":
        from tools.scc.ops import ssot_sync
        return ssot_sync.main()
    else:
        print(f"Unknown ops subcommand: {args.subcommand}")
        return 1


def cmd_map(args: argparse.Namespace) -> int:
    """Map-related operations."""
    if args.subcommand == "build":
        from tools.scc.map import map_sqlite_v1
        return map_sqlite_v1.main()
    elif args.subcommand == "query":
        from tools.scc.map import map_query_sqlite_v1
        return map_query_sqlite_v1.main()
    elif args.subcommand == "query-batch":
        from tools.scc.map import map_query_sqlite_batch_v1
        return map_query_sqlite_batch_v1.main()
    else:
        print(f"Unknown map subcommand: {args.subcommand}")
        return 1


def cmd_selftest(args: argparse.Namespace) -> int:
    """Run self-tests."""
    if args.subcommand == "no-hardcoded-paths":
        from tools.scc.selftest import selfcheck_no_hardcoded_paths
        return selfcheck_no_hardcoded_paths.main()
    elif args.subcommand == "no-shell-true":
        from tools.scc.selftest import selfcheck_no_shell_true
        return selfcheck_no_shell_true.main()
    elif args.subcommand == "contracts":
        from tools.scc.selftest import validate_contract_examples
        return validate_contract_examples.main()
    elif args.subcommand == "release":
        from tools.scc.selftest import validate_release_record
        return validate_release_record.main()
    else:
        print(f"Unknown selftest subcommand: {args.subcommand}")
        return 1


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="sccctl",
        description="SCC (Self-Contained Code) Tools CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    sccctl gates                    # Run all CI gates
    sccctl validate contracts       # Validate contract examples
    sccctl ops patterns-sync        # Sync patterns registry
    sccctl map build                # Build map SQLite database
    sccctl selftest contracts       # Run contract self-tests
        """.strip(),
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # gates command
    gates_parser = subparsers.add_parser("gates", help="Run CI gates")
    gates_parser.set_defaults(func=cmd_gates)
    
    # validate command
    validate_parser = subparsers.add_parser("validate", help="Validate contracts and schemas")
    validate_subparsers = validate_parser.add_subparsers(dest="subcommand")
    validate_subparsers.add_parser("contracts", help="Validate contract examples")
    validate_subparsers.add_parser("release", help="Validate release records")
    validate_parser.set_defaults(func=cmd_validate)
    
    # ops command
    ops_parser = subparsers.add_parser("ops", help="Run operations")
    ops_subparsers = ops_parser.add_subparsers(dest="subcommand")
    ops_subparsers.add_parser("patterns-sync", help="Sync patterns registry")
    ops_subparsers.add_parser("playbooks-sync", help="Sync playbooks registry")
    ops_subparsers.add_parser("skills-sync", help="Sync skills drafts registry")
    ops_subparsers.add_parser("playbook-publish", help="Publish playbook")
    ops_subparsers.add_parser("playbook-stage", help="Stage playbook")
    ops_subparsers.add_parser("playbook-rollback", help="Rollback playbook")
    ops_subparsers.add_parser("release-integrate", help="Integrate release")
    ops_subparsers.add_parser("metrics-rollup", help="Rollup metrics")
    ops_subparsers.add_parser("board-maintenance", help="Board maintenance")
    ops_subparsers.add_parser("eval-replay", help="Eval replay")
    ops_subparsers.add_parser("ssot-sync", help="SSOT sync")
    ops_parser.set_defaults(func=cmd_ops)
    
    # map command
    map_parser = subparsers.add_parser("map", help="Map operations")
    map_subparsers = map_parser.add_subparsers(dest="subcommand")
    map_subparsers.add_parser("build", help="Build map SQLite database")
    map_subparsers.add_parser("query", help="Query map database")
    map_subparsers.add_parser("query-batch", help="Batch query map database")
    map_parser.set_defaults(func=cmd_map)
    
    # selftest command
    selftest_parser = subparsers.add_parser("selftest", help="Run self-tests")
    selftest_subparsers = selftest_parser.add_subparsers(dest="subcommand")
    selftest_subparsers.add_parser("no-hardcoded-paths", help="Check for hardcoded paths")
    selftest_subparsers.add_parser("no-shell-true", help="Check for shell=True")
    selftest_subparsers.add_parser("contracts", help="Validate contracts")
    selftest_subparsers.add_parser("release", help="Validate releases")
    selftest_parser.set_defaults(func=cmd_selftest)
    
    args = parser.parse_args(argv)
    
    if not args.command:
        parser.print_help()
        return 1
    
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
