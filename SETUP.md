# Repository Setup & Deployment Guide

This guide covers setting up the openclaw-lacp-fusion repository for distribution and deployment.

## Repository Structure

```
openclaw-lacp-fusion/
├── README.md                    Main documentation
├── LICENSE                      MIT license
├── INSTALL.sh                   Installation script
├── CONTRIBUTING.md              Contributing guidelines
├── CHANGELOG.md                 Version history
├── SETUP.md                     This file
├── plugin.json                  Plugin metadata
│
├── plugin/                      Plugin source code
│   ├── hooks/                   Phase 1: Execution hooks
│   │   ├── handlers/            Hook implementations (Python)
│   │   ├── profiles/            Safety profiles (JSON)
│   │   ├── rules/               Pattern definitions (YAML)
│   │   ├── tests/               Unit tests (60 tests)
│   │   └── *.md                 Hook documentation
│   ├── policy/                  Phase 2: Policy gates
│   │   ├── risk-policy.json     Routing configuration
│   │   └── *.py                 Policy tests
│   └── bin/                     Phase 2-4: Executables
│       ├── openclaw-route       Routing engine
│       ├── openclaw-gated-run   Gated execution
│       ├── openclaw-memory-*    Memory tools
│       ├── openclaw-verify      Verification
│       └── test_gated_run.sh    Functional tests
│
├── docs/                        User documentation
│   ├── COMPLETE-GUIDE.md        Full user guide (800 lines)
│   ├── DEPLOYMENT-TO-OPENCLAW.md Integration guide
│   ├── MEMORY-SCAFFOLDING.md    Memory architecture
│   ├── POLICY-GUIDE.md          Policy configuration
│   └── ROUTING-REFERENCE.md     Routing details
│
├── releases/                    Distribution packages
│   └── openclaw-lacp-fusion-1.0.0.zip
│
└── .github/                     GitHub configuration
    ├── workflows/               CI/CD workflows
    │   └── tests.yml            Test automation
    └── ISSUE_TEMPLATE/          Issue templates
        ├── bug_report.md
        └── feature_request.md
```

## Local Development

### 1. Clone Repository

```bash
git clone https://github.com/openclaw/plugins.git
cd openclaw-lacp-fusion
```

### 2. Install Development Environment

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install pytest pytest-cov pyyaml
```

### 3. Run Tests

```bash
# All tests
python3 -m pytest plugin/hooks/tests/ -v

# With coverage
python3 -m pytest plugin/hooks/tests/ --cov=plugin/ --cov-report=html

# Specific phase
python3 -m pytest plugin/hooks/tests/test_session_start.py -v
```

## GitHub Repository Setup

### 1. Create Repository

```bash
# On GitHub, create:
# - Name: openclaw-lacp-fusion
# - Description: LACP integration for OpenClaw
# - Visibility: Public
# - License: MIT
# - Add .gitignore: Python

# Don't initialize with README (we have one)
```

### 2. Add Remote & Push

```bash
cd /path/to/openclaw-lacp-fusion-repo

# Add remote
git remote add origin https://github.com/openclaw/openclaw-lacp-fusion.git

# Push to GitHub
git branch -M main
git push -u origin main
```

### 3. Configure Repository Settings

#### General
- Description: "LACP integration for OpenClaw — hooks, policy, memory, verification"
- Website: https://github.com/openclaw/openclaw-lacp-fusion
- Topics: `hooks`, `policy`, `safety`, `verification`, `openclaw`

#### Branches
- Default branch: `main`
- Branch protection rules:
  - Require pull request reviews: 1
  - Require status checks to pass: Yes (tests.yml)
  - Require branches to be up to date: Yes

#### Collaborators & Teams
- Add OpenClaw team with Maintain access
- Set up bot account with Write access for releases

#### Pages (Optional)
- Enable GitHub Pages
- Source: docs/ folder
- Theme: auto-selected

## Release Management

### Creating a Release

```bash
# 1. Update version
# - Update CHANGELOG.md
# - Update plugin.json version
# - Commit: git commit -m "bump: v1.0.1"

# 2. Create tag
git tag -a v1.0.1 -m "Release v1.0.1 - description"

# 3. Push
git push origin main
git push origin v1.0.1

# 4. Create GitHub Release
# - Go to Releases → Draft new release
# - Tag: v1.0.1
# - Title: v1.0.1
# - Description: Use CHANGELOG.md
# - Attach: releases/openclaw-lacp-fusion-1.0.1.zip

# 5. Publish
# Click "Publish release"
```

### Versioning

Follow semver:
- **1.0.0** → **1.0.1** (Patch: bug fixes)
- **1.0.0** → **1.1.0** (Minor: features)
- **1.0.0** → **2.0.0** (Major: breaking)

## CI/CD Pipeline

### GitHub Actions Workflow

The `.github/workflows/tests.yml` workflow:
- Triggers on push to main/develop and PRs
- Tests on: Ubuntu + macOS
- Python versions: 3.9, 3.10, 3.11, 3.12
- Runs: lint, tests, coverage

```yaml
# Automatically runs:
- Flake8 linting
- pytest test suite
- Coverage report (to Codecov)
```

### Adding More Workflows

For additional automation, create `.github/workflows/workflow-name.yml`:

```yaml
name: Custom Workflow
on: [push, pull_request]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: |
          python -m pip install -e .
          python -m pytest
```

## Distribution Channels

### 1. GitHub Releases

```bash
# Users download from:
# https://github.com/openclaw/openclaw-lacp-fusion/releases/download/v1.0.0/

# Or via latest:
# https://github.com/openclaw/openclaw-lacp-fusion/releases/latest
```

### 2. Package Registries

#### Homebrew (macOS)

Create `Formula/openclaw-lacp-fusion.rb`:

```ruby
class OpenclawLacpFusion < Formula
  desc "LACP integration for OpenClaw"
  homepage "https://github.com/openclaw/openclaw-lacp-fusion"
  url "https://github.com/openclaw/openclaw-lacp-fusion/releases/download/v1.0.0/openclaw-lacp-fusion-1.0.0.zip"
  sha256 "..."
  
  depends_on "bash" => "5.0"
  depends_on "python" => "3.9"
  
  def install
    system "bash", "INSTALL.sh"
  end
end
```

Then submit to Homebrew:

```bash
brew tap-new openclaw/plugins
brew extract --version=1.0.0 openclaw-lacp-fusion openclaw/plugins
```

#### NPM (Node.js)

Create `package.json`:

```json
{
  "name": "openclaw-lacp-fusion",
  "version": "1.0.0",
  "description": "LACP integration for OpenClaw",
  "bin": {
    "openclaw-lacp-install": "./INSTALL.sh"
  },
  "repository": {
    "type": "git",
    "url": "https://github.com/openclaw/openclaw-lacp-fusion.git"
  },
  "keywords": ["openclaw", "hooks", "policy", "safety"],
  "author": "OpenClaw Community",
  "license": "MIT"
}
```

Publish:

```bash
npm publish
```

### 3. Plugin Registry

Register on clawhub.com:

```json
{
  "name": "openclaw-lacp-fusion",
  "version": "1.0.0",
  "downloadUrl": "https://github.com/openclaw/openclaw-lacp-fusion/releases/download/v1.0.0/openclaw-lacp-fusion-1.0.0.zip",
  "checksum": "sha256:...",
  "requirements": {
    "openclaw": ">=0.23.0",
    "python": ">=3.9",
    "bash": ">=5.0"
  }
}
```

## Documentation Hosting

### Option 1: GitHub Pages

```bash
# Enable in Settings → Pages
# Source: /docs folder
# Theme: auto

# Build docs:
cd docs
# Docs are already in Markdown — GitHub renders automatically
```

### Option 2: Custom Domain

```bash
# Add CNAME:
echo "lacp-fusion.openclaw.ai" > docs/CNAME

# Push:
git add docs/CNAME
git commit -m "docs: add custom domain"
git push
```

## Maintenance

### Regular Tasks

**Weekly:**
- Review and respond to issues
- Review pull requests
- Monitor test results

**Monthly:**
- Triage issues
- Plan next release
- Review metrics

**Quarterly:**
- Major version planning
- Community feedback review
- Performance audit

### Security

- Keep dependencies up to date
- Review third-party code
- Report security issues privately
- Publish security advisories when needed

```bash
# Check for vulnerabilities
pip install safety
safety check
```

## Troubleshooting

### Tests Fail Locally

```bash
# Ensure Python version
python3 --version  # Should be 3.9+

# Install dependencies
pip install -r requirements.txt

# Run with verbose output
python3 -m pytest -vv --tb=long
```

### CI Fails on GitHub

- Check workflow logs: GitHub → Actions → Latest run
- Common issues:
  - Missing dependencies: Update requirements.txt
  - Python version: Check matrix in tests.yml
  - Permission issues: Check git config

### Release Issues

- Tag already exists: `git tag -d v1.0.1; git push origin :v1.0.1`
- Wrong commit: Create new tag with `-f`: `git tag -f v1.0.1`
- Release not showing: Check tag format matches `vX.Y.Z`

## Support

- **GitHub Issues:** https://github.com/openclaw/openclaw-lacp-fusion/issues
- **Discord:** https://discord.com/invite/clawd
- **Email:** plugins@openclaw.ai

---

**Next:** Follow [CONTRIBUTING.md](./CONTRIBUTING.md) for development workflow
