#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

step() {
  echo ""
  echo "== $1 =="
}

step "Python syntax (stable scope)"
python -m compileall "$repo_root/tools/scc" "$repo_root/scc-top/tools/unified_server" "$repo_root/scc-top/tools/scc"

step "Python unit tests"
python -m unittest discover -s "$repo_root/tools/scc/runtime/tests" -p "test_*.py"

step "Contract examples"
python "$repo_root/tools/scc/selftest/validate_contract_examples.py"

step "Safety gates"
python "$repo_root/tools/scc/selftest/selfcheck_no_hardcoded_paths.py"
python "$repo_root/tools/scc/selftest/selfcheck_no_shell_true.py"

step "Node syntax check (gateway)"
node --check "$repo_root/oc-scc-local/src/gateway.mjs"

step "Node unit tests (oc-scc-local)"
pushd "$repo_root/oc-scc-local" >/dev/null
if [[ ! -d node_modules ]]; then
  npm ci
fi
node --test
popd >/dev/null

echo ""
echo "OK: verify_all passed."

