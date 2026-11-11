#!/usr/bin/env python3
"""Fail-closed static checks for candidate caller/reusable workflow YAML."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path.cwd()
PATTERN = os.environ.get("CANDIDATE_WORKFLOW_GLOB", ".github/workflows/ci-dry-run-*.yml")
files = sorted(ROOT.glob(PATTERN))
errors: list[str] = []
if not files:
    errors.append(f"no workflows matched {PATTERN!r}")

USE_RE = re.compile(r"^\s*uses:\s*([^\s#]+)", re.M)
SHA_RE = re.compile(r"@[0-9a-f]{40}$")
JOB_RE = re.compile(r"^  ([A-Za-z0-9_-]+):\s*(?:#.*)?$", re.M)
secret_expression = chr(36) + "{{"

for path in files:
    text = path.read_text(encoding="utf-8")
    if re.search(r"(?m)^\s*pull_request_target\s*:", text):
        errors.append(f"{path}: pull_request_target is forbidden")
    if re.search(r"(?im)^\s*secrets\s*:\s*inherit\s*(?:#.*)?$", text):
        errors.append(f"{path}: secrets: inherit is forbidden")
    if secret_expression in text and "secrets." in text:
        errors.append(f"{path}: CI candidate must not reference secrets")
    if re.search(r"(?im)^\s*environment\s*:\s*['\"]?production\b", text):
        errors.append(f"{path}: production environment is forbidden")
    if re.search(r"(?im)^\s*permissions\s*:\s*(?:write-all|\{\s*['\"]?write-all)", text):
        errors.append(f"{path}: write-all permissions are forbidden")
    for ref in USE_RE.findall(text):
        if ref.startswith("./"):
            continue
        if not SHA_RE.search(ref):
            errors.append(f"{path}: action/reusable workflow is not pinned to a full SHA: {ref}")
    jobs_start = text.find("\njobs:")
    if jobs_start >= 0:
        jobs_text = text[jobs_start + 1:]
        starts = list(JOB_RE.finditer(jobs_text))
        for index, match in enumerate(starts):
            end = starts[index + 1].start() if index + 1 < len(starts) else len(jobs_text)
            block = jobs_text[match.start():end]
            if "uses:" in block or "runs-on:" in block:
                if not re.search(r"(?m)^    permissions:\s*$", block):
                    errors.append(f"{path}: job {match.group(1)} lacks job-level permissions")

if errors:
    print("WORKFLOW_POLICY_FAIL")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print(f"WORKFLOW_POLICY_PASS files={len(files)}")
for path in files:
    print(path.relative_to(ROOT))
