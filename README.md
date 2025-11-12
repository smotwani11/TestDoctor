# 2GPTestDoctor 🩺

**Automated Test Fixer for 2GP Packaging Tests**

Diagnoses and heals common anti-patterns in 2GP packaging functional tests that cause timeouts and flaky failures in autobuilds.

2GPTestDoctor automatically detects and fixes common anti-patterns in functional tests that cause autobuild failures.

## The Problem

57+ functional tests in the 2GP packaging codebase are at risk of failing in autobuilds due to:
- Missing `registerNewOrg()` calls
- Missing `USE_TEST_QUEUE` settings
- Missing `@MqTypeMapping` annotations
- Missing countdown latches

These failures cause tests to timeout after 20+ minutes, blocking releases and wasting engineering time.

## The Solution

2GPTestDoctor scans your test files and:
1. **Detects** anti-patterns across 4 common rules
2. **Reports** issues with detailed analysis
3. **Auto-fixes** problems with one command
4. **Validates** fixes don't break existing tests

## Quick Start

```bash
# Scan a directory for issues
python3 testdoctor.py scan --path /path/to/tests

# Scan a specific file
python3 testdoctor.py scan --path /path/to/MyTest.java

# Generate report
python3 testdoctor.py report

# Auto-fix issues
python3 testdoctor.py fix --rule 1 --auto

# Fix all rules
python3 testdoctor.py fix --all --auto
```

## Rules

### Rule 1: Missing `registerNewOrg()` Calls
Tests that create scratch orgs must register them with the message queue framework.

### Rule 2: Missing `USE_TEST_QUEUE`
Tests extending `BaseTest` (not `BaseBuildOrgTest`) must use test queues.

### Rule 3: Missing `PACKAGE_INSTALL` Mappings
Tests that install packages must have proper MQ type mappings.

### Rule 4: Missing Countdown Latches
Tests that create versions or do conversions must have countdown latches.

## Impact

- **57 tests** identified with issues
- **10 files** missing registerNewOrg() calls
- **6 files** missing USE_TEST_QUEUE
- **30 files** missing PACKAGE_INSTALL mappings
- **11 files** missing countdown latches

## Demo

Refer `demo.sh` for a complete walkthrough.
