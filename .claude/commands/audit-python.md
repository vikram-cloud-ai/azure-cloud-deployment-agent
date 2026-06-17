# Python Security Audit & Fix

## Task
Audit this Python project for dependency vulnerabilities, apply fixes, and verify nothing is broken by running the test suite.

## Steps

### 1. Identify the dependency files
Look for: `requirements.txt`, `pyproject.toml`, `Pipfile`, `setup.py`, `setup.cfg`

### 2. Run pip-audit
If pip-audit is not installed, install it first:
```bash
pip install pip-audit
```

Run the audit:
```bash
pip-audit
```

If the project uses a requirements file:
```bash
pip-audit -r requirements.txt
```

### 3. Analyze results
For each vulnerability found, identify:
- Package name and current version
- CVE or vulnerability ID
- Severity (critical / high / medium / low)
- Fixed version (if available)

### 4. Apply fixes
Upgrade vulnerable packages to their safe versions:
```bash
pip install --upgrade <package>==<fixed_version>
```

Then update the dependency file to reflect the new versions:
- For `requirements.txt`: update the pinned version or version constraint
- For `pyproject.toml`: update under `[project.dependencies]` or `[tool.poetry.dependencies]`
- For `Pipfile`: update then run `pipenv lock`

### 5. Run tests
Detect the test framework in use and run the full test suite:

**pytest** (check for `pytest.ini`, `conftest.py`, or `tests/` directory):
```bash
pytest
```

**unittest**:
```bash
python -m unittest discover
```

**tox** (check for `tox.ini`):
```bash
tox
```

If tests fail after upgrading a package:
- Check if the failure is related to the upgraded package
- If yes, flag it for human review — do not roll back automatically
- If no, note the pre-existing failure and continue

### 6. Re-run audit to verify
```bash
pip-audit
```
Confirm no vulnerabilities remain.

### 7. Report
Summarize what was found and fixed in this format:

**Vulnerabilities**

| Package | Old Version | New Version | CVE | Severity |
|---------|-------------|-------------|-----|----------|
| example | 1.0.0       | 1.2.3       | CVE-XXXX-XXXX | High |

**Test Results**

| Status | Tests Run | Passed | Failed | Skipped |
|--------|-----------|--------|--------|---------|
| ✅ / ❌ | 00        | 00     | 00     | 00      |

Flag any vulnerabilities that could not be fixed (e.g. no fix available, or breaking version change) and explain why.
Flag any test failures and whether they appear related to the upgrades or were pre-existing.

## Rules
- Do not upgrade packages beyond what is needed to resolve the vulnerability
- If a fix requires a major version bump, flag it for human review instead of auto-applying
- Do not remove packages to resolve vulnerabilities — find the safe version instead
- If pip-audit is unavailable, fall back to: `safety check`
- Always run tests after applying fixes, even if only one package was changed
- Do not mark the audit as complete if tests are failing due to an upgrade