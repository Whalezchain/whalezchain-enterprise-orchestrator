from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).with_name("validate_workflow_policy.py")


def run_policy(tmp_path: Path, body: str) -> subprocess.CompletedProcess[str]:
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    (workflow_dir / "ci-dry-run-test.yml").write_text(body, encoding="utf-8")
    env = dict(os.environ)
    env["CANDIDATE_WORKFLOW_GLOB"] = ".github/workflows/ci-dry-run-*.yml"
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
    )


GOOD = """name: Test
on:
  pull_request:
permissions:
  contents: read
jobs:
  validate:
    uses: owner/repo/.github/workflows/test.yml@0123456789abcdef0123456789abcdef01234567
    permissions:
      contents: read
"""


def test_accepts_pinned_minimum_permission_caller(tmp_path):
    result = run_policy(tmp_path, GOOD)
    assert result.returncode == 0
    assert "WORKFLOW_POLICY_PASS" in result.stdout


def test_rejects_tag_pinned_external_action(tmp_path):
    result = run_policy(tmp_path, GOOD.replace("@0123456789abcdef0123456789abcdef01234567", "@v4"))
    assert result.returncode == 1
    assert "not pinned to a full SHA" in result.stdout


def test_rejects_pull_request_target(tmp_path):
    result = run_policy(tmp_path, GOOD.replace("pull_request:", "pull_request_target:"))
    assert result.returncode == 1
    assert "pull_request_target is forbidden" in result.stdout


def test_rejects_inherited_secrets(tmp_path):
    result = run_policy(tmp_path, GOOD + "    secrets: inherit\n")
    assert result.returncode == 1
    assert "secrets: inherit is forbidden" in result.stdout


def test_rejects_secret_references(tmp_path):
    secret_ref = chr(36) + "{{ secrets.PROD_TOKEN }}"
    result = run_policy(tmp_path, GOOD + "    env:\n      TOKEN: " + secret_ref + "\n")
    assert result.returncode == 1
    assert "must not reference secrets" in result.stdout


def test_rejects_write_all_and_missing_job_permissions(tmp_path):
    without_permissions = GOOD.replace("    permissions:\n      contents: read\n", "")
    result = run_policy(tmp_path, without_permissions + "permissions: write-all\n")
    assert result.returncode == 1
    assert "job validate lacks job-level permissions" in result.stdout
    assert "write-all permissions are forbidden" in result.stdout


def test_rejects_production_environment(tmp_path):
    result = run_policy(tmp_path, GOOD + "    environment: production\n")
    assert result.returncode == 1
    assert "production environment is forbidden" in result.stdout
