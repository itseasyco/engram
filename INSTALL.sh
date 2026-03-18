#!/bin/bash
set -euo pipefail

# OpenClaw LACP Fusion Plugin Installer
# Version: 1.0.0
# Description: Install LACP fusion (hooks + policy + memory + evidence) into OpenClaw

PLUGIN_NAME="openclaw-lacp-fusion"
PLUGIN_VERSION="1.0.0"
OPENCLAW_HOME="${OPENCLAW_HOME:=$HOME/.openclaw}"
PLUGIN_PATH="$OPENCLAW_HOME/plugins/$PLUGIN_NAME"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}ℹ${NC}  $1"
}

log_success() {
    echo -e "${GREEN}✓${NC}  $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC}  $1"
}

log_error() {
    echo -e "${RED}✗${NC}  $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check OpenClaw is installed
    if [ ! -d "$OPENCLAW_HOME" ]; then
        log_error "OpenClaw not found at $OPENCLAW_HOME"
        echo "Set OPENCLAW_HOME=/path/to/.openclaw and try again"
        exit 1
    fi
    log_success "OpenClaw found at $OPENCLAW_HOME"
    
    # Check bash version
    if [ "${BASH_VERSINFO[0]}" -lt 5 ]; then
        log_error "Bash 5.0+ required (you have ${BASH_VERSION})"
        exit 1
    fi
    log_success "Bash version ${BASH_VERSION}"
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3.9+ required"
        exit 1
    fi
    local py_version=$(python3 --version 2>&1 | awk '{print $2}')
    log_success "Python $py_version found"
    
    # Check git
    if ! command -v git &> /dev/null; then
        log_error "git required"
        exit 1
    fi
    log_success "git found"
}

# Create plugin directory structure
setup_plugin_directory() {
    log_info "Setting up plugin directory at $PLUGIN_PATH..."
    
    # Create base plugin dir
    mkdir -p "$PLUGIN_PATH"
    
    # Copy core files
    cp "$SCRIPT_DIR/plugin.json" "$PLUGIN_PATH/"
    
    # Copy from source distribution
    if [ -d "$SCRIPT_DIR/hooks" ]; then
        cp -r "$SCRIPT_DIR/hooks" "$PLUGIN_PATH/plugins/"
    fi
    
    if [ -d "$SCRIPT_DIR/policy" ]; then
        mkdir -p "$PLUGIN_PATH/config/policy"
        cp -r "$SCRIPT_DIR/policy"/* "$PLUGIN_PATH/config/policy/"
    fi
    
    if [ -d "$SCRIPT_DIR/bin" ]; then
        mkdir -p "$PLUGIN_PATH/bin"
        cp "$SCRIPT_DIR/bin"/* "$PLUGIN_PATH/bin/"
        chmod +x "$PLUGIN_PATH/bin"/*
    fi
    
    if [ -d "$SCRIPT_DIR/docs" ]; then
        cp -r "$SCRIPT_DIR/docs" "$PLUGIN_PATH/"
    fi
    
    if [ -d "$SCRIPT_DIR/tests" ]; then
        cp -r "$SCRIPT_DIR/tests" "$PLUGIN_PATH/"
    fi
    
    log_success "Plugin directory created"
}

# Initialize git repo
setup_git() {
    log_info "Initializing git repository..."
    
    if [ ! -d "$PLUGIN_PATH/.git" ]; then
        cd "$PLUGIN_PATH"
        git init
        git config user.email "openclaw-plugin@localhost"
        git config user.name "OpenClaw Plugin Manager"
        git add .
        git commit -m "chore: initial commit — openclaw-lacp-fusion v$PLUGIN_VERSION"
        log_success "Git repository initialized"
    else
        log_warning "Git repository already exists"
    fi
}

# Run tests
run_tests() {
    log_info "Running test suite..."
    
    if [ -f "$PLUGIN_PATH/tests/test_integration.py" ]; then
        cd "$PLUGIN_PATH"
        if python3 -m pytest tests/ -v --tb=short 2>&1 | head -50; then
            log_success "Test suite passed"
        else
            log_warning "Some tests failed (see above)"
        fi
    else
        log_warning "No test suite found"
    fi
}

# Create configuration
setup_configuration() {
    log_info "Setting up configuration..."
    
    # Create default profile selection
    local profile_config="$PLUGIN_PATH/.profile"
    if [ ! -f "$profile_config" ]; then
        echo "balanced" > "$profile_config"
        log_success "Default profile set to 'balanced'"
    fi
    
    # Create data directories
    mkdir -p "$PLUGIN_PATH/data/approval-cache"
    mkdir -p "$PLUGIN_PATH/data/project-sessions"
    mkdir -p "$PLUGIN_PATH/logs"
    
    log_success "Configuration directories created"
}

# Print summary
print_summary() {
    cat << EOF

${GREEN}✓ Installation Complete${NC}

Plugin: $PLUGIN_NAME v$PLUGIN_VERSION
Location: $PLUGIN_PATH

${BLUE}Next Steps:${NC}
1. Review configuration: cat $PLUGIN_PATH/docs/COMPLETE-GUIDE.md
2. Select a profile: echo 'minimal-stop' > $PLUGIN_PATH/.profile
   (options: minimal-stop, balanced, hardened-exec)
3. Test execution: $PLUGIN_PATH/bin/openclaw-route --help
4. Enable in OpenClaw: See deployment guide at $PLUGIN_PATH/docs/DEPLOYMENT-TO-OPENCLAW.md

${BLUE}Documentation:${NC}
- Complete Guide: $PLUGIN_PATH/docs/COMPLETE-GUIDE.md
- Deployment: $PLUGIN_PATH/docs/DEPLOYMENT-TO-OPENCLAW.md
- Operations: $PLUGIN_PATH/plugins/lacp-hooks/OPERATIONS.md
- Troubleshooting: $PLUGIN_PATH/plugins/lacp-hooks/TROUBLESHOOTING.md

${BLUE}Tests:${NC}
- Run all: python3 -m pytest $PLUGIN_PATH/tests/ -v
- Run specific: python3 -m pytest $PLUGIN_PATH/tests/test_integration.py -v

EOF
}

main() {
    echo ""
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║  OpenClaw LACP Fusion Plugin Installer v$PLUGIN_VERSION"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    
    check_prerequisites
    setup_plugin_directory
    setup_git
    setup_configuration
    run_tests
    print_summary
    
    log_success "Installation successful!"
    exit 0
}

main "$@"
