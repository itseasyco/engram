# Contributing to OpenClaw LACP Fusion

Thank you for your interest in contributing to OpenClaw LACP Fusion! This document provides guidelines and instructions for contributing.

## Code of Conduct

Be respectful, inclusive, and constructive. We're all here to make agent safety better.

## Getting Started

### 1. Fork & Clone

```bash
# Fork on GitHub, then:
git clone https://github.com/YOUR-USERNAME/engram.git
cd engram
git remote add upstream https://github.com/openclaw/plugins.git
```

### 2. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or: git checkout -b fix/issue-description
```

### 3. Make Changes

All contributions should:
- Follow the existing code style
- Include tests for new functionality
- Update documentation as needed
- Pass all existing tests

### 4. Test Thoroughly

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run specific tests
python3 -m pytest tests/test_session_start.py -v

# Check coverage
python3 -m pytest tests/ --cov=. --cov-report=html
```

**All tests must pass before submitting a PR.**

### 5. Commit & Push

```bash
git add .
git commit -m "feat: description of change"
git push origin feature/your-feature-name
```

### 6. Submit a Pull Request

- Title: Clear, concise description
- Description: What changed and why
- Link any related issues
- Include test results

## Contribution Areas

### 1. Bug Fixes

Found a bug? Submit an issue with:
- Description of the bug
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment (OpenClaw version, Python version, OS)

Then submit a PR with:
- Test case that reproduces the bug
- Fix that makes the test pass
- Any documentation updates needed

### 2. Features

Have an idea for a new feature? Start a discussion:
- Open an issue describing the feature
- Explain the use case
- Propose implementation approach
- Wait for feedback before coding

Then:
- Write tests for the new feature
- Implement the feature
- Update documentation
- Submit PR

### 3. Documentation

Help improve documentation:
- Fix typos and clarifications
- Add examples
- Improve explanations
- Add troubleshooting guides

Documentation PRs are always welcome!

### 4. Tests

Increase test coverage:
- Add tests for edge cases
- Test error conditions
- Test configuration variations
- Performance tests

### 5. Performance

Optimize existing code:
- Profile to identify bottlenecks
- Benchmark before/after
- Ensure no functionality changes
- Document performance gains

## Code Style

### Python

```python
# Use snake_case for functions/variables
def handle_dangerous_pattern(pattern: str) -> bool:
    """Single-line docstring for simple functions.
    
    Longer docstrings should use triple quotes and describe:
    - What it does
    - Parameters
    - Return value
    """
    # Comments for why, not what
    if pattern in BLOCKED_PATTERNS:
        return True
    return False
```

### Bash

```bash
#!/bin/bash
set -euo pipefail

# Use functions for reusability
log_info() {
    echo "[INFO] $1"
}

# Use quotes
if [ -f "$file" ]; then
    log_info "File found: $file"
fi
```

### JSON/YAML

```json
{
  "name": "value",
  "nested": {
    "key": "value"
  }
}
```

## Testing Requirements

### Coverage

- New code must have tests
- Aim for 80%+ coverage
- Test happy path + error cases

### Test Structure

```python
import pytest

class TestSessionStart:
    def test_git_context_injection(self):
        """Test that git context is injected."""
        # Arrange
        context = {}
        
        # Act
        result = inject_git_context(context)
        
        # Assert
        assert "branch" in result
        assert "commits" in result
```

### Run Tests

```bash
# All tests
python3 -m pytest tests/ -v

# Specific file
python3 -m pytest tests/test_pretool_guard.py -v

# Single test
python3 -m pytest tests/test_pretool_guard.py::TestDangerousPatterns::test_blocks_npm_publish -v

# With coverage
python3 -m pytest tests/ --cov=. --cov-report=html
```

## Documentation

### Update When

- Adding a feature → update relevant guide
- Fixing a bug → update if behavior changes
- Adding tests → update test documentation
- Changing configuration → update POLICY-GUIDE.md

### Documentation Files

- **README.md** — Quick start
- **docs/COMPLETE-GUIDE.md** — Full user guide
- **docs/POLICY-GUIDE.md** — Policy configuration
- **docs/DEPLOYMENT-TO-OPENCLAW.md** — Integration
- **docs/MEMORY-SCAFFOLDING.md** — Memory system
- **docs/ROUTING-REFERENCE.md** — Routing engine

## Commit Messages

Use conventional commits:

```
feat: add support for custom hooks
fix: correct dangerous pattern detection
docs: clarify policy configuration
test: add tests for edge cases
refactor: improve routing performance
```

Format: `<type>: <description>`

Types: feat, fix, docs, test, refactor, perf, chore

## Pull Request Process

1. **Before creating PR:**
   - [ ] Tests pass (`pytest tests/ -v`)
   - [ ] Code follows style guidelines
   - [ ] Documentation updated
   - [ ] Commit messages are clear
   - [ ] Rebased on latest `main`

2. **Create PR:**
   - [ ] Clear title
   - [ ] Description of changes
   - [ ] Motivation/context
   - [ ] Related issues (fixes #123)
   - [ ] Screenshots (if applicable)

3. **Review process:**
   - [ ] At least one review required
   - [ ] All feedback addressed
   - [ ] Tests pass in CI
   - [ ] Ready to merge

## Reporting Issues

### Bug Report

```markdown
**Describe the bug**
Clear description of what the bug is.

**Steps to reproduce**
1. Install with ...
2. Run command ...
3. See error ...

**Expected behavior**
What should happen.

**Actual behavior**
What actually happens.

**Environment**
- OpenClaw version: X.Y.Z
- Python version: X.Y.Z
- Bash version: X.Y.Z
- OS: macOS/Linux/Windows
```

### Feature Request

```markdown
**Is your feature request related to a problem?**
Describe the problem it solves.

**Describe the solution**
Describe the feature.

**Describe alternatives considered**
Other approaches you've thought of.

**Why should this be implemented?**
Use cases and benefits.
```

## Development Setup

```bash
# Clone repo
git clone https://github.com/YOUR-USERNAME/engram.git
cd engram

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run tests
python3 -m pytest tests/ -v
```

## Release Process

Releases are managed by maintainers. Version numbering follows semver:

- **1.0.0 → 1.0.1** — Patch (bug fixes)
- **1.0.0 → 1.1.0** — Minor (features)
- **1.0.0 → 2.0.0** — Major (breaking changes)

## Questions?

- **Discord:** https://discord.com/invite/clawd
- **Email:** plugins@openclaw.ai
- **Issues:** https://github.com/openclaw/plugins/issues

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing! 🎉
