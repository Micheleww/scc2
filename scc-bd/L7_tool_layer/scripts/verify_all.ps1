$ErrorActionPreference = "Stop"

function Run-Step([string]$label, [scriptblock]$fn) {
  Write-Host ""
  Write-Host "== $label =="
  & $fn
}

$scriptDir = Split-Path -Parent $PSCommandPath
$repoRoot = Split-Path -Parent $scriptDir
Push-Location $repoRoot
try {

  Run-Step "Python Syntax (Stable Scope)" {
    python -m compileall tools/scc scc-top/tools/unified_server scc-top/tools/scc
  }

  Run-Step "Python Unit Tests" {
    python -m unittest discover -s tools/scc/runtime/tests -p "test_*.py"
  }

  Run-Step "Contract Examples" {
    python tools/scc/selftest/validate_contract_examples.py
  }

  Run-Step "Safety Gates" {
    python tools/scc/selftest/selfcheck_no_hardcoded_paths.py
    python tools/scc/selftest/selfcheck_no_shell_true.py
  }

  Run-Step "Node Syntax Check (Gateway)" {
    node --check oc-scc-local/src/gateway.mjs
  }

  Run-Step "Node Unit Tests (oc-scc-local)" {
    Push-Location oc-scc-local
    try {
      if (-not (Test-Path "node_modules")) {
        npm ci
      }
      node --test
    } finally {
      Pop-Location
    }
  }

  Write-Host ""
  Write-Host "OK: verify_all passed."
} finally {
  Pop-Location
}
