#!/bin/bash
set -euo pipefail

# OpenClaw LACP Fusion Plugin Installer
# Version: 2.2.0
# Interactive CLI wizard for configuring and installing the plugin
# Installs to ~/.openclaw/extensions/engram/

# Require Bash 4.0+ (for associative arrays)
# Bash 3.2+ is fine (macOS default)

# Track whether install has started (vs still in wizard)
INSTALL_STARTED=false

_install_cleanup() {
    local exit_code=$?
    if [ "$exit_code" -ne 0 ]; then
        echo ""
        if [ "$INSTALL_STARTED" = "true" ]; then
            echo -e "\033[0;31mInstallation failed (exit code $exit_code).\033[0m"
            echo ""
            echo "To recover:"
            echo "  1. Re-run INSTALL.sh (it's safe to run again)"
            echo "  2. If gateway config is broken: restore from backup:"
            echo "     cp ~/.openclaw/openclaw.json.bak.* ~/.openclaw/openclaw.json"
            echo "  3. To remove partial install:"
            echo "     rm -rf ~/.openclaw/extensions/engram"
            echo ""
        else
            echo -e "\033[1;33mInstallation cancelled.\033[0m"
            echo ""
        fi
    fi
}
trap _install_cleanup EXIT

PLUGIN_NAME="engram"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_VERSION=$(node -p "require('${SCRIPT_DIR}/package.json').version" 2>/dev/null || echo "3.0.0")
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
ENGRAM_HOME="${ENGRAM_HOME:-$HOME/.engram}"
ENGRAM_CONFIG="$ENGRAM_HOME/config.json"
PLUGIN_PATH="$OPENCLAW_HOME/extensions/$PLUGIN_NAME"
GATEWAY_CONFIG="$OPENCLAW_HOME/openclaw.json"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}i${NC}  $1"; }
log_success() { echo -e "${GREEN}✓${NC}  $1"; }
log_warning() { echo -e "${YELLOW}!${NC}  $1"; }
log_error()   { echo -e "${RED}✗${NC}  $1"; }
log_step()    { echo -e "\n${BOLD}[$1/$TOTAL_STEPS] $2${NC}"; }

TOTAL_STEPS=10

# ─── Detect environment ──────────────────────────────────────────────────────

detect_environment() {
    local os
    os="$(uname -s)"
    case "$os" in
        Darwin) DETECTED_OS="macos" ;;
        Linux)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                DETECTED_OS="wsl"
            else
                DETECTED_OS="linux"
            fi
            ;;
        *) DETECTED_OS="unknown" ;;
    esac

    # Scan for Obsidian vaults (directories containing .obsidian/)
    DETECTED_VAULTS=()
    local search_roots=()

    case "$DETECTED_OS" in
        macos)
            search_roots=("$HOME/Documents" "$HOME/Desktop")
            # Check mounted volumes (external drives, NAS, etc.)
            for vol in /Volumes/*/; do
                [ -d "$vol" ] && search_roots+=("${vol%/}")
            done
            ;;
        *)
            search_roots=("$HOME/Documents" "$HOME/Desktop")
            ;;
    esac

    echo -en "  Scanning for Obsidian vaults..."
    for root in "${search_roots[@]}"; do
        if [ -d "$root" ]; then
            while IFS= read -r vault_dir; do
                local vault="${vault_dir%/.obsidian}"
                DETECTED_VAULTS+=("$vault")
                echo -en "."
            done < <(find "$root" -maxdepth 3 -name ".obsidian" -type d 2>/dev/null)
        fi
    done
    echo " done"

    # Deduplicate (bash 3.2 compatible)
    if [ "${#DETECTED_VAULTS[@]}" -gt 0 ]; then
        local unique_vaults=()
        local seen_list=""
        for v in "${DETECTED_VAULTS[@]}"; do
            if [[ "$seen_list" != *"|${v}|"* ]]; then
                seen_list="${seen_list}|${v}|"
                unique_vaults+=("$v")
            fi
        done
        DETECTED_VAULTS=("${unique_vaults[@]}")
    fi
}

# ─── Interactive wizard ──────────────────────────────────────────────────────

# Detect gum for interactive prompts (falls back to read-based prompts)
HAS_GUM=false
if command -v gum &>/dev/null; then
    HAS_GUM=true
fi

prompt_value() {
    local prompt="$1"
    local default="$2"

    if [ "$HAS_GUM" = "true" ]; then
        echo -e "  ${CYAN}?${NC} ${prompt}" >&2
        gum input --placeholder "$default" --value "$default" --width 60
    else
        local result
        echo -en "  ${CYAN}?${NC} ${prompt} ${DIM}[${default}]${NC}: " >&2
        read -r result
        echo "${result:-$default}"
    fi
}

extract_first_word() {
    # Extracts the first word from a choice string like "auto          — description"
    echo "$1" | awk '{print $1}'
}

prompt_choice() {
    local prompt="$1"
    shift
    local options=("$@")
    local default="${options[0]}"

    if [ "$HAS_GUM" = "true" ]; then
        echo -e "  ${CYAN}?${NC} ${prompt}" >&2
        gum choose --cursor="> " --cursor.foreground="212" "${options[@]}"
    else
        echo -e "  ${CYAN}?${NC} ${prompt}" >&2
        for i in "${!options[@]}"; do
            local num=$((i + 1))
            if [ "$i" -eq 0 ]; then
                echo -e "    ${GREEN}${num})${NC} ${BOLD}${options[$i]}${NC} ${DIM}(default)${NC}" >&2
            else
                echo -e "    ${num}) ${options[$i]}" >&2
            fi
        done
        echo -en "    Choice [1-${#options[@]}]: " >&2
        read -r choice
        if [ -z "$choice" ] || [ "$choice" -lt 1 ] 2>/dev/null || [ "$choice" -gt "${#options[@]}" ] 2>/dev/null; then
            echo "$default"
        else
            echo "${options[$((choice - 1))]}"
        fi
    fi
}

prompt_yes_no() {
    local prompt="$1"
    local default="${2:-y}"

    if [ "$HAS_GUM" = "true" ]; then
        if [ "$default" = "y" ]; then
            gum confirm "$prompt" --default=yes
        else
            gum confirm "$prompt" --default=no
        fi
    else
        if [ "$default" = "y" ]; then
            echo -en "  ${CYAN}?${NC} ${prompt} ${DIM}[Y/n]${NC}: "
        else
            echo -en "  ${CYAN}?${NC} ${prompt} ${DIM}[y/N]${NC}: "
        fi
        read -r answer
        answer="${answer:-$default}"
        case "$answer" in
            [yY]|[yY][eE][sS]) return 0 ;;
            *) return 1 ;;
        esac
    fi
}

prompt_browse_directory() {
    if [ "$HAS_GUM" = "true" ]; then
        echo -e "  ${DIM}Navigate with arrow keys, Enter to select${NC}" >&2
        gum file --directory --height 12 "${1:-$HOME}"
    else
        local result
        echo -en "  ${CYAN}?${NC} Enter directory path: " >&2
        read -r result
        echo "$result"
    fi
}

# ─── Dependency installers ───────────────────────────────────────────────────

check_and_install_obsidian_headless() {
    if command -v ob &>/dev/null; then
        local ob_ver
        ob_ver=$(ob --version 2>/dev/null || echo "unknown")
        log_success "obsidian-headless found (ob $ob_ver)"
        return 0
    fi

    log_warning "obsidian-headless (ob) not found"
    echo -e "  ${DIM}Required for Connected and Curator modes (vault sync via ob sync).${NC}"
    echo ""

    if prompt_yes_no "Install obsidian-headless globally? (npm install -g obsidian-headless)" "y"; then
        echo ""
        if [ "$HAS_GUM" = "true" ]; then
            if gum spin --spinner dot --title "Installing obsidian-headless..." -- npm install -g obsidian-headless 2>/dev/null; then
                log_success "obsidian-headless installed"
            else
                log_error "obsidian-headless installation failed"
                return 1
            fi
        else
            log_info "Installing obsidian-headless (this may take a moment)..."
            if npm install -g obsidian-headless 2>&1 | tail -3; then
                log_success "obsidian-headless installed"
            else
                log_error "obsidian-headless installation failed"
                return 1
            fi
        fi

        if command -v ob &>/dev/null; then
            local ob_ver
            ob_ver=$(ob --version 2>/dev/null || echo "unknown")
            log_success "Verified: ob $ob_ver"
            return 0
        else
            log_error "ob command not found after install. Check your PATH"
            return 1
        fi
    else
        log_info "Skipped obsidian-headless installation"
        return 1
    fi
}

check_and_install_neo4j() {
    # Neo4j is optional — graph DB features degrade gracefully without it
    if command -v neo4j &>/dev/null; then
        local neo4j_version
        neo4j_version=$(neo4j --version 2>/dev/null | head -1 || echo "unknown")
        log_success "Neo4j found ($neo4j_version)"
        return 0
    fi

    log_warning "Neo4j not found"
    echo -e "  ${DIM}Neo4j provides the graph intelligence layer (entity relationships, spreading activation).${NC}"
    echo -e "  ${DIM}Engram works without it — graph features will gracefully degrade to JSON indexes.${NC}"
    echo ""

    if prompt_yes_no "Install Neo4j Community Edition? (brew install neo4j)" "n"; then
        echo ""
        if [ "$HAS_GUM" = "true" ]; then
            if gum spin --spinner dot --title "Installing Neo4j..." -- brew install neo4j 2>/dev/null; then
                log_success "Neo4j installed"
            else
                log_error "Neo4j installation failed"
                log_info "Install manually: brew install neo4j (macOS) or see https://neo4j.com/docs/operations-manual/current/installation/"
                return 1
            fi
        else
            log_info "Installing Neo4j (this may take a moment)..."
            if brew install neo4j 2>&1 | tail -5; then
                log_success "Neo4j installed"
            else
                log_error "Neo4j installation failed"
                log_info "Install manually: brew install neo4j (macOS) or see https://neo4j.com/docs/operations-manual/current/installation/"
                return 1
            fi
        fi

        if command -v neo4j &>/dev/null; then
            log_success "Verified: Neo4j ready"
            log_info "Start Neo4j with: neo4j start"
            log_info "Default bolt URL: bolt://localhost:7687"
            return 0
        else
            log_error "neo4j command not found after install"
            return 1
        fi
    else
        log_info "Skipped Neo4j installation (graph features will use fallback mode)"
        return 0  # Not a failure — Neo4j is optional
    fi
}

check_and_install_gitnexus() {
    if command -v gitnexus &>/dev/null; then
        log_success "GitNexus found ($(which gitnexus))"
        return 0
    fi

    log_warning "GitNexus not found"
    echo -e "  ${DIM}GitNexus provides Layer 4 code intelligence (AST analysis, dependency graphs).${NC}"
    echo ""

    if prompt_yes_no "Install GitNexus globally? (npm install -g gitnexus)" "y"; then
        echo ""
        if [ "$HAS_GUM" = "true" ]; then
            if gum spin --spinner dot --title "Installing GitNexus..." -- npm install -g gitnexus 2>/dev/null; then
                log_success "GitNexus installed"
            else
                log_error "GitNexus installation failed"
                return 1
            fi
        else
            log_info "Installing GitNexus (this may take a moment)..."
            if npm install -g gitnexus 2>&1 | tail -3; then
                log_success "GitNexus installed"
            else
                log_error "GitNexus installation failed"
                return 1
            fi
        fi

        if command -v gitnexus &>/dev/null; then
            log_success "Verified: GitNexus ready"
            return 0
        else
            log_error "gitnexus command not found after install"
            return 1
        fi
    else
        log_info "Skipped GitNexus installation"
        return 1
    fi
}

check_and_install_lossless_claw() {
    if [ -d "$OPENCLAW_HOME/extensions/lossless-claw" ]; then
        log_success "lossless-claw found at $OPENCLAW_HOME/extensions/lossless-claw"
        return 0
    fi

    log_warning "lossless-claw not found"
    echo -e "  ${DIM}lossless-claw provides the native LCM database context engine.${NC}"
    echo ""

    if prompt_yes_no "Install lossless-claw? (openclaw plugins install @martian-engineering/lossless-claw)" "y"; then
        echo ""
        if [ "$HAS_GUM" = "true" ]; then
            if gum spin --spinner dot --title "Installing lossless-claw..." -- openclaw plugins install @martian-engineering/lossless-claw 2>/dev/null; then
                log_success "lossless-claw installed"
            else
                log_error "lossless-claw installation failed"
                return 1
            fi
        else
            log_info "Installing lossless-claw (this may take a moment)..."
            if openclaw plugins install @martian-engineering/lossless-claw 2>&1 | tail -5; then
                log_success "lossless-claw installed"
            else
                log_error "lossless-claw installation failed"
                return 1
            fi
        fi

        if [ -d "$OPENCLAW_HOME/extensions/lossless-claw" ]; then
            log_success "Verified: lossless-claw extension present"
        else
            log_error "lossless-claw directory not found after install"
            return 1
        fi

        if [ -f "$OPENCLAW_HOME/lcm.db" ]; then
            log_success "Verified: lcm.db exists"
        else
            log_info "lcm.db not yet created. Will be initialized on first use"
        fi

        return 0
    else
        log_info "Skipped lossless-claw installation"
        return 1
    fi
}

check_and_install_qmd() {
    if command -v qmd &>/dev/null; then
        local qmd_ver
        qmd_ver=$(which qmd)
        log_success "QMD found"
        return 0
    fi

    log_warning "QMD not found"
    echo -e "  ${DIM}QMD provides semantic vector search over your vault for better memory retrieval.${NC}"
    echo ""

    if prompt_yes_no "Install QMD? (npm install -g @tobilu/qmd)" "y"; then
        echo ""
        if [ "$HAS_GUM" = "true" ]; then
            if gum spin --spinner dot --title "Installing QMD..." -- npm install -g @tobilu/qmd 2>/dev/null; then
                log_success "QMD installed"
            else
                log_error "QMD installation failed"
                return 1
            fi
        else
            log_info "Installing QMD (this may take a moment)..."
            if npm install -g @tobilu/qmd 2>&1 | tail -3; then
                log_success "QMD installed"
            else
                log_error "QMD installation failed"
                return 1
            fi
        fi

        if command -v qmd &>/dev/null; then
            log_success "Verified: QMD ready"
            return 0
        else
            log_error "qmd command not found after install"
            return 1
        fi
    else
        log_info "Skipped QMD installation"
        return 1
    fi
}

check_and_install_obsidian_cli() {
    # The npm package is "obsidian-cli" but the binary it installs is "obsidian"
    # We need to distinguish the CLI from the Obsidian desktop app
    if command -v obsidian &>/dev/null; then
        if obsidian --help 2>&1 | head -1 | grep -q "Usage:"; then
            log_success "Obsidian CLI found ($(which obsidian))"
            return 0
        fi
        # "obsidian" exists but it's the desktop app, not the CLI
        log_warning "Found Obsidian desktop app but not the CLI"
    fi

    log_warning "Obsidian CLI not found"
    echo -e "  ${DIM}Obsidian CLI lets you manage your vault from the terminal (open, create notes, run commands).${NC}"
    echo ""

    if prompt_yes_no "Install Obsidian CLI? (npm install -g obsidian-cli)" "n"; then
        echo ""
        if [ "$HAS_GUM" = "true" ]; then
            if gum spin --spinner dot --title "Installing Obsidian CLI..." -- npm install -g obsidian-cli 2>/dev/null; then
                log_success "Obsidian CLI installed"
            else
                log_error "Obsidian CLI installation failed"
                return 1
            fi
        else
            log_info "Installing Obsidian CLI (this may take a moment)..."
            if npm install -g obsidian-cli 2>&1 | tail -3; then
                log_success "Obsidian CLI installed"
            else
                log_error "Obsidian CLI installation failed"
                return 1
            fi
        fi

        # Refresh PATH hash and verify
        hash -r 2>/dev/null

        # Ensure npm global bin is in PATH for the user's shell
        local npm_bin
        npm_bin=$(npm bin -g 2>/dev/null || echo "")
        if [ -n "$npm_bin" ] && ! echo "$PATH" | tr ':' '\n' | grep -q "^${npm_bin}$"; then
            local shell_rc=""
            case "$(basename "${SHELL:-/bin/bash}")" in
                zsh)  shell_rc="$HOME/.zshrc" ;;
                bash) shell_rc="$HOME/.bashrc" ;;
                fish) shell_rc="$HOME/.config/fish/config.fish" ;;
                *)    shell_rc="$HOME/.profile" ;;
            esac
            if [ -n "$shell_rc" ] && [ -f "$shell_rc" ]; then
                if ! grep -q "$npm_bin" "$shell_rc" 2>/dev/null; then
                    echo "" >> "$shell_rc"
                    echo "# Added by Engram installer — npm global bin" >> "$shell_rc"
                    echo "export PATH=\"$npm_bin:\$PATH\"" >> "$shell_rc"
                    log_info "Added npm bin to $shell_rc"
                    export PATH="$npm_bin:$PATH"
                fi
            fi
        fi

        if command -v obsidian &>/dev/null && obsidian --help 2>&1 | head -1 | grep -q "Usage:"; then
            log_success "Verified: Obsidian CLI ready"
            return 0
        else
            log_warning "Obsidian CLI installed but 'obsidian' command not found in current session"
            log_info "Restart your terminal or run: source ~/.zshrc"
            return 0
        fi
    else
        log_info "Skipped Obsidian CLI installation"
        return 1
    fi
}

run_wizard() {
    echo ""
    echo -e "${BOLD}Configuration Wizard${NC}"
    echo -e "${DIM}Press Enter to accept defaults shown in brackets.${NC}"
    echo ""

    # Mode defaults
    WIZARD_MODE="standalone"
    WIZARD_CURATOR_URL=""
    WIZARD_CURATOR_TOKEN=""

    # 1. Obsidian vault path
    echo -e "${BOLD}Obsidian Vault${NC}"
    echo -e "  ${DIM}Your Obsidian vault stores knowledge graph data (Layer 2).${NC}"
    echo -e "  ${DIM}If you don't use Obsidian, a directory will be created for you.${NC}"
    echo ""

    if [ "${#DETECTED_VAULTS[@]}" -gt 0 ]; then
        echo -e "  ${GREEN}Found ${#DETECTED_VAULTS[@]} Obsidian vault(s):${NC}"
        echo ""

        local vault_choices=()
        for v in "${DETECTED_VAULTS[@]}"; do
            vault_choices+=("$v")
        done
        vault_choices+=("Browse for a different folder")
        vault_choices+=("Type a custom path")
        vault_choices+=("Skip — I don't use Obsidian")

        local vault_pick
        vault_pick=$(prompt_choice "Select your vault" "${vault_choices[@]}")

        case "$vault_pick" in
            "Browse for a different folder")
                WIZARD_VAULT=$(prompt_browse_directory "$HOME")
                ;;
            "Type a custom path")
                WIZARD_VAULT=$(prompt_value "Vault path" "$HOME/my-vault")
                ;;
            "Skip — I don't use Obsidian")
                WIZARD_VAULT="$OPENCLAW_HOME/data/knowledge"
                log_info "No vault selected — using default knowledge directory"
                ;;
            *)
                WIZARD_VAULT="$vault_pick"
                ;;
        esac
    else
        echo -e "  ${YELLOW}No Obsidian vaults detected.${NC}"
        echo ""
        local vault_pick
        vault_pick=$(prompt_choice "How would you like to set your vault?" \
            "Browse for folder" \
            "Type a custom path" \
            "Skip — I don't use Obsidian")

        case "$vault_pick" in
            "Browse for folder")
                WIZARD_VAULT=$(prompt_browse_directory "$HOME")
                ;;
            "Type a custom path")
                WIZARD_VAULT=$(prompt_value "Vault path" "$HOME/my-vault")
                ;;
            "Skip — I don't use Obsidian")
                WIZARD_VAULT="$OPENCLAW_HOME/data/knowledge"
                log_info "No vault selected — using default knowledge directory"
                ;;
        esac
    fi
    echo -e "  ${GREEN}✓${NC} Vault: $WIZARD_VAULT"
    echo ""

    # 2. Context engine (detect first, ask only if needed)
    echo -e "${BOLD}Context Engine${NC}"
    echo -e "  ${DIM}Controls how LACP stores and retrieves context facts.${NC}"
    echo ""

    # Auto-detect what's available
    local has_lossless_claw=false
    local has_lcm_db=false
    if [ -d "$OPENCLAW_HOME/extensions/lossless-claw" ]; then
        has_lossless_claw=true
        echo -e "  ${GREEN}+${NC} lossless-claw extension detected"
    fi
    if [ -f "$OPENCLAW_HOME/lcm.db" ]; then
        has_lcm_db=true
        echo -e "  ${GREEN}+${NC} LCM database found (~/.openclaw/lcm.db)"
    fi
    echo ""

    if [ "$has_lossless_claw" = "true" ]; then
        # lossless-claw is installed, recommend it but let them choose
        local ce_choice
        ce_choice=$(prompt_choice "Context engine (lossless-claw detected)" \
            "lossless-claw — native LCM database (recommended, already installed)" \
            "file-based    — JSON files on disk (simpler, no database)")
        WIZARD_CONTEXT_ENGINE=$(extract_first_word "$ce_choice")
    else
        # No lossless-claw, offer to install or use file-based
        local ce_choice
        ce_choice=$(prompt_choice "Context engine" \
            "file-based    — JSON files on disk (no extra dependencies)" \
            "lossless-claw — install native LCM database for better performance")
        WIZARD_CONTEXT_ENGINE=$(extract_first_word "$ce_choice")
    fi

    if [ -z "$WIZARD_CONTEXT_ENGINE" ]; then
        WIZARD_CONTEXT_ENGINE="file-based"
    fi
    echo -e "  ${GREEN}✓${NC} Context engine: $WIZARD_CONTEXT_ENGINE"
    echo ""

    # 3. Safety profile
    echo -e "${BOLD}Safety Profile${NC}"
    echo -e "  ${DIM}Controls which execution hooks are active and how they behave.${NC}"
    echo ""
    local profile_choice
    profile_choice=$(prompt_choice "Profile" \
        "autonomous    — all hooks, warn-only (agents keep working, escalate when needed)" \
        "balanced      — session context + quality gate (recommended for interactive use)" \
        "context-only  — just git context injection, no safety gates" \
        "guard-rail    — safety gates only, no context injection" \
        "minimal-stop  — quality gate only (lightweight)" \
        "hardened-exec — all 4 hooks, blocks dangerous ops" \
        "full-audit    — all hooks, strict mode, verbose logging")
    WIZARD_PROFILE=$(extract_first_word "$profile_choice")
    echo -e "  ${GREEN}✓${NC} Safety profile: $WIZARD_PROFILE"
    echo ""

    # 4. Operating mode
    echo -e "${BOLD}Operating Mode${NC}"
    echo -e "  ${DIM}Controls how this node participates in the knowledge network.${NC}"
    echo -e "  ${DIM}Standalone is the default. Everything runs locally.${NC}"
    echo ""
    local mode_choice
    mode_choice=$(prompt_choice "Mode" \
        "standalone — local vault, all brain commands active (default)" \
        "connected  — sync to shared vault, mutations delegated to curator" \
        "curator    — server node: connectors, mycelium, git backup, invites")
    WIZARD_MODE=$(extract_first_word "$mode_choice")
    echo -e "  ${GREEN}✓${NC} Operating mode: $WIZARD_MODE"
    echo ""

    # Connected mode: collect curator URL and invite token
    if [ "$WIZARD_MODE" = "connected" ]; then
        echo -e "${BOLD}Curator Connection${NC}"
        echo -e "  ${DIM}Your curator admin should have given you a URL and invite token.${NC}"
        echo ""
        WIZARD_CURATOR_URL=$(prompt_value "Curator URL" "https://curator.example.com")
        WIZARD_CURATOR_TOKEN=$(prompt_value "Invite token" "")
        if [ -z "$WIZARD_CURATOR_TOKEN" ]; then
            log_warning "No invite token provided. You can set this later via openclaw-lacp-connect join"
        fi
        echo -e "  ${GREEN}✓${NC} Curator URL: $WIZARD_CURATOR_URL"
        echo ""
    fi

    # Curator mode: placeholder flags
    if [ "$WIZARD_MODE" = "curator" ]; then
        echo -e "${BOLD}Curator Server Setup${NC}"
        echo -e "  ${DIM}Full curator configuration (connectors, schedule, git backup, invites)${NC}"
        echo -e "  ${DIM}will be available in a future release. Setting curator flags for now.${NC}"
        echo ""
        log_info "Curator mode flags will be written to config."
        echo ""
    fi

    # Dependency: obsidian-headless (required for connected/curator)
    if [ "$WIZARD_MODE" = "connected" ] || [ "$WIZARD_MODE" = "curator" ]; then
        echo -e "${BOLD}Required Dependency: obsidian-headless${NC}"
        echo ""
        if ! check_and_install_obsidian_headless; then
            echo ""
            log_warning "Cannot proceed with $WIZARD_MODE mode without obsidian-headless."
            log_info "Falling back to standalone mode. You can switch later with:"
            log_info "  1. npm install -g obsidian-headless"
            log_info "  2. openclaw-lacp-connect join --token <token>"
            echo ""
            WIZARD_MODE="standalone"
            WIZARD_CURATOR_URL=""
            WIZARD_CURATOR_TOKEN=""
            echo -e "  ${YELLOW}!${NC} Mode changed to: standalone"
            echo ""
        fi
    fi

    # 4.5. Core dependencies (QMD + optional Obsidian CLI)
    echo -e "${BOLD}Dependencies${NC}"
    echo ""
    check_and_install_qmd || true
    echo ""
    check_and_install_obsidian_cli || true
    echo ""
    check_and_install_neo4j || true
    echo ""

    # 5. Advanced config (optional)
    WIZARD_ADVANCED=false
    if prompt_yes_no "Configure advanced options?" "n"; then
        WIZARD_ADVANCED=true
        echo ""
        echo -e "${BOLD}Advanced Configuration${NC}"

        local tier_choice
        tier_choice=$(prompt_choice "Default policy tier" \
            "review   — require review before execution" \
            "safe     — auto-approve safe operations" \
            "critical — all operations require approval")
        WIZARD_POLICY_TIER=$(extract_first_word "$tier_choice")
        if [ -z "$WIZARD_POLICY_TIER" ]; then
            WIZARD_POLICY_TIER="review"
        fi
        echo -e "  ${GREEN}✓${NC} Policy tier: $WIZARD_POLICY_TIER"
        echo ""

        WIZARD_CODE_GRAPH="false"
        if prompt_yes_no "Enable code intelligence (AST analysis)?" "n"; then
            echo ""
            echo -e "${BOLD}Dependency: GitNexus${NC}"
            echo ""
            if check_and_install_gitnexus; then
                WIZARD_CODE_GRAPH="true"
                log_success "Code intelligence enabled with GitNexus"
            else
                echo ""
                log_warning "GitNexus not available. Code intelligence disabled"
                log_info "Install later: npm install -g gitnexus"
                WIZARD_CODE_GRAPH="false"
            fi
            echo ""
        fi
        WIZARD_PROVENANCE=$(prompt_yes_no "Enable provenance tracking?" "y" && echo "true" || echo "false")
        WIZARD_LOCAL_FIRST=$(prompt_yes_no "Local-first mode (no external sync)?" "y" && echo "true" || echo "false")

        # Guard configuration
        echo ""
        echo -e "${BOLD}Guard Configuration${NC}"
        echo -e "  ${DIM}Controls how the pretool guard handles dangerous commands.${NC}"
        echo ""

        local guard_level_choice
        guard_level_choice=$(prompt_choice "Default guard block level" \
            "block — block dangerous commands (ask user first)" \
            "warn  — warn but allow execution (log to guard-blocks.jsonl)" \
            "log   — silently log matches (no interruption)")
        WIZARD_GUARD_LEVEL=$(extract_first_word "$guard_level_choice")
        echo -e "  ${GREEN}✓${NC} Guard block level: $WIZARD_GUARD_LEVEL"
        echo ""

        if prompt_yes_no "Configure individual guard rules?" "n"; then
            echo ""
            # Generate guard-rules.json with current defaults first
            local guard_config="$PLUGIN_PATH/config/guard-rules.json"
            if [ -f "$SCRIPT_DIR/plugin/config/guard-rules.json" ] && [ ! -f "$guard_config" ]; then
                mkdir -p "$PLUGIN_PATH/config"
                cp "$SCRIPT_DIR/plugin/config/guard-rules.json" "$guard_config"
            fi

            if [ -f "$guard_config" ]; then
                # Set default level before launching TUI
                if command -v jq &>/dev/null && [ -n "$WIZARD_GUARD_LEVEL" ]; then
                    local tmp
                    tmp=$(mktemp)
                    jq --arg level "$WIZARD_GUARD_LEVEL" '.defaults.block_level = $level' "$guard_config" > "$tmp" && mv "$tmp" "$guard_config"
                fi

                # Launch interactive TUI
                python3 "$SCRIPT_DIR/plugin/lib/guard_tui.py" "$guard_config"
                echo ""
                log_success "Guard rules configured"
            else
                log_warning "Guard config not found — will use factory defaults"
            fi
            WIZARD_DISABLED_RULES=()
            WIZARD_RULE_OVERRIDES=()
        else
            WIZARD_DISABLED_RULES=()
            WIZARD_RULE_OVERRIDES=()
        fi
    else
        WIZARD_POLICY_TIER="review"
        WIZARD_CODE_GRAPH="false"
        WIZARD_PROVENANCE="true"
        WIZARD_LOCAL_FIRST="true"
        WIZARD_GUARD_LEVEL="block"
        WIZARD_DISABLED_RULES=()
    fi

    # Resolve context engine with dependency detection
    if [ "$WIZARD_CONTEXT_ENGINE" = "lossless-claw" ]; then
        echo -e "${BOLD}Dependency: lossless-claw${NC}"
        echo ""
        if check_and_install_lossless_claw; then
            WIZARD_CONTEXT_ENGINE_RESOLVED="lossless-claw"
        else
            echo ""
            log_warning "lossless-claw not available. Falling back to file-based context engine"
            log_info "Install later: openclaw plugins install @martian-engineering/lossless-claw"
            WIZARD_CONTEXT_ENGINE_RESOLVED="file-based"
        fi
        echo ""
    elif [ "$WIZARD_CONTEXT_ENGINE" = "auto" ]; then
        echo -e "  ${DIM}Auto-detecting context engine...${NC}"
        if [ -d "$OPENCLAW_HOME/extensions/lossless-claw" ] && [ -f "$OPENCLAW_HOME/lcm.db" ]; then
            WIZARD_CONTEXT_ENGINE_RESOLVED="lossless-claw"
            log_success "Detected: lossless-claw (LCM database + extension found)"
        elif [ -d "$OPENCLAW_HOME/extensions/lossless-claw" ]; then
            WIZARD_CONTEXT_ENGINE_RESOLVED="lossless-claw"
            log_success "Detected: lossless-claw (extension found, lcm.db will be created on first use)"
        else
            WIZARD_CONTEXT_ENGINE_RESOLVED="file-based"
            log_info "Detected: file-based (lossless-claw not installed)"
        fi
    else
        WIZARD_CONTEXT_ENGINE_RESOLVED="$WIZARD_CONTEXT_ENGINE"
    fi
    echo -e "  ${GREEN}✓${NC} Resolved context engine: $WIZARD_CONTEXT_ENGINE_RESOLVED"

    # 6. Confirmation
    echo ""
    echo -e "${BOLD}Installation Summary${NC}"
    echo ""
    echo -e "  Obsidian vault:    ${GREEN}${WIZARD_VAULT}${NC}"
    echo -e "  Context engine:    ${GREEN}${WIZARD_CONTEXT_ENGINE_RESOLVED}${NC}"
    echo -e "  Safety profile:    ${GREEN}${WIZARD_PROFILE}${NC}"
    echo -e "  Operating mode:    ${GREEN}${WIZARD_MODE}${NC}"
    echo -e "  Policy tier:       ${GREEN}${WIZARD_POLICY_TIER}${NC}"
    echo -e "  Code graph:        ${GREEN}${WIZARD_CODE_GRAPH}${NC}"
    echo -e "  Provenance:        ${GREEN}${WIZARD_PROVENANCE}${NC}"
    echo -e "  Guard level:       ${GREEN}${WIZARD_GUARD_LEVEL}${NC}"
    echo ""
    echo -e "  Install path:      ${DIM}${PLUGIN_PATH}${NC}"
    echo ""

    if ! prompt_yes_no "Proceed with installation?" "y"; then
        echo ""
        log_info "Installation cancelled."
        exit 0
    fi

    # Export wizard values for use by installation steps
    DETECTED_VAULT="$WIZARD_VAULT"
}

# ─── Step 1: Prerequisites ───────────────────────────────────────────────────

check_prerequisites() {
    log_step 1 "Checking prerequisites"
    local fail=0

    # OpenClaw home
    if [ ! -d "$OPENCLAW_HOME" ]; then
        log_warning "OpenClaw directory not found at $OPENCLAW_HOME — will be created"
        mkdir -p "$OPENCLAW_HOME"
    fi
    log_success "OpenClaw home: $OPENCLAW_HOME"

    # Gateway config (create minimal if missing)
    if [ ! -f "$GATEWAY_CONFIG" ]; then
        log_warning "Gateway config not found — creating minimal config"
        echo '{"plugins":{"allow":[],"entries":{},"installs":{}}}' > "$GATEWAY_CONFIG"
    fi
    log_success "Gateway config: $GATEWAY_CONFIG"

    # Python 3.9+
    if ! command -v python3 &>/dev/null; then
        log_error "Python 3.9+ required"
        fail=1
    else
        local py_version
        py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        log_success "Python $py_version"
    fi

    # git
    if ! command -v git &>/dev/null; then
        log_error "git required"
        fail=1
    else
        log_success "git found"
    fi

    # jq (needed for gateway config editing)
    if ! command -v jq &>/dev/null; then
        log_warning "jq not found — gateway config will not be auto-updated"
        log_info "  Install jq: brew install jq (macOS) or apt install jq (Linux)"
        HAS_JQ=false
    else
        log_success "jq found"
        HAS_JQ=true
    fi

    if [ "$fail" -ne 0 ]; then
        log_error "Prerequisites check failed"
        exit 1
    fi
}

# ─── Step 2: Create plugin directory ─────────────────────────────────────────

setup_plugin_directory() {
    log_step 2 "Installing plugin to $PLUGIN_PATH"

    mkdir -p "$PLUGIN_PATH"

    # Copy manifest
    cp "$SCRIPT_DIR/openclaw.plugin.json" "$PLUGIN_PATH/"
    cp "$SCRIPT_DIR/plugin.json" "$PLUGIN_PATH/"

    # Generate package.json (required by gateway for plugin resolution)
    cat > "$PLUGIN_PATH/package.json" << PKGJSON
{
  "name": "$PLUGIN_NAME",
  "version": "$PLUGIN_VERSION",
  "description": "LACP integration for OpenClaw — hooks, policy gates, gated execution, memory scaffolding, and evidence verification.",
  "license": "MIT",
  "type": "module",
  "main": "index.ts",
  "openclaw": {
    "extensions": [
      "./index.ts"
    ]
  }
}
PKGJSON
    log_success "package.json generated"

    # Copy plugin source tree
    if [ -d "$SCRIPT_DIR/plugin" ]; then
        # Hooks
        if [ -d "$SCRIPT_DIR/plugin/hooks" ]; then
            mkdir -p "$PLUGIN_PATH/hooks"
            cp -r "$SCRIPT_DIR/plugin/hooks/handlers" "$PLUGIN_PATH/hooks/"
            cp -r "$SCRIPT_DIR/plugin/hooks/profiles" "$PLUGIN_PATH/hooks/"
            cp -r "$SCRIPT_DIR/plugin/hooks/rules" "$PLUGIN_PATH/hooks/"
            cp "$SCRIPT_DIR/plugin/hooks/plugin.json" "$PLUGIN_PATH/hooks/"
            [ -d "$SCRIPT_DIR/plugin/hooks/tests" ] && cp -r "$SCRIPT_DIR/plugin/hooks/tests" "$PLUGIN_PATH/hooks/"
            local profile_count
            profile_count=$(ls -1 "$PLUGIN_PATH/hooks/profiles"/*.json 2>/dev/null | wc -l | tr -d ' ')
            log_success "Hooks installed (4 handlers, $profile_count profiles)"
        fi

        # Policy
        if [ -d "$SCRIPT_DIR/plugin/policy" ]; then
            mkdir -p "$PLUGIN_PATH/policy"
            cp -r "$SCRIPT_DIR/plugin/policy"/* "$PLUGIN_PATH/policy/"
            log_success "Policy engine installed"
        fi

        # Bin scripts
        if [ -d "$SCRIPT_DIR/plugin/bin" ]; then
            mkdir -p "$PLUGIN_PATH/bin"
            cp "$SCRIPT_DIR/plugin/bin"/engram-* "$PLUGIN_PATH/bin/" 2>/dev/null || true
            chmod +x "$PLUGIN_PATH/bin"/* 2>/dev/null || true
            local bin_count
            bin_count=$(ls -1 "$PLUGIN_PATH/bin"/ 2>/dev/null | wc -l | tr -d ' ')
            log_success "Bin scripts installed ($bin_count executables)"
        fi

        # Python library modules (mycelium, consolidation, etc.)
        if [ -d "$SCRIPT_DIR/plugin/lib" ]; then
            mkdir -p "$PLUGIN_PATH/lib"
            cp "$SCRIPT_DIR/plugin/lib"/*.py "$PLUGIN_PATH/lib/" 2>/dev/null || true
            cp "$SCRIPT_DIR/plugin/__init__.py" "$PLUGIN_PATH/__init__.py" 2>/dev/null || true
            cp "$SCRIPT_DIR/plugin/lib/__init__.py" "$PLUGIN_PATH/lib/__init__.py" 2>/dev/null || true
            local lib_count
            lib_count=$(ls -1 "$PLUGIN_PATH/lib"/*.py 2>/dev/null | wc -l | tr -d ' ')
            log_success "Python library modules installed ($lib_count modules)"
        fi

        # Python pip dependencies
        if [ -f "$SCRIPT_DIR/plugin/requirements.txt" ]; then
            cp "$SCRIPT_DIR/plugin/requirements.txt" "$PLUGIN_PATH/requirements.txt"
            log_info "Installing Python dependencies..."
            if python3 -m pip install -r "$PLUGIN_PATH/requirements.txt" --quiet 2>/dev/null; then
                log_success "Python dependencies installed"
            else
                log_warning "Some Python dependencies failed to install"
                log_info "  Run manually: pip install -r $PLUGIN_PATH/requirements.txt"
            fi
        fi

        # Config
        if [ -d "$SCRIPT_DIR/plugin/config" ]; then
            mkdir -p "$PLUGIN_PATH/config"
            cp -r "$SCRIPT_DIR/plugin/config"/* "$PLUGIN_PATH/config/" 2>/dev/null || true
            log_success "Config files installed"
        fi

        # V2 LCM
        if [ -d "$SCRIPT_DIR/plugin/v2-lcm" ]; then
            mkdir -p "$PLUGIN_PATH/v2-lcm"
            cp -r "$SCRIPT_DIR/plugin/v2-lcm"/* "$PLUGIN_PATH/v2-lcm/"
            log_success "V2 lifecycle manager installed"
        fi

        # Templates (TOOLS.md, AGENTS.md)
        if [ -d "$SCRIPT_DIR/plugin/templates" ]; then
            mkdir -p "$PLUGIN_PATH/templates"
            cp -r "$SCRIPT_DIR/plugin/templates"/* "$PLUGIN_PATH/templates/"
            log_success "Agent workspace templates installed"
        fi

        # Skills (curator-maintenance.md)
        if [ -d "$SCRIPT_DIR/plugin/skills" ]; then
            mkdir -p "$PLUGIN_PATH/skills"
            cp -r "$SCRIPT_DIR/plugin/skills"/* "$PLUGIN_PATH/skills/"
            log_success "Skills installed"
        fi
    fi

    # Copy docs
    if [ -d "$SCRIPT_DIR/docs" ]; then
        mkdir -p "$PLUGIN_PATH/docs"
        cp -r "$SCRIPT_DIR/docs"/* "$PLUGIN_PATH/docs/"
        log_success "Documentation installed"
    fi

    # Copy index.ts entry point (gateway requires this)
    if [ -f "$SCRIPT_DIR/plugin/index.ts" ]; then
        cp "$SCRIPT_DIR/plugin/index.ts" "$PLUGIN_PATH/index.ts"
        log_success "Gateway entry point (index.ts) installed"
    else
        log_warning "index.ts not found in distribution — gateway may fail to load plugin"
    fi

    # Symlink OpenClaw SDK (index.ts imports from openclaw/plugin-sdk)
    _link_openclaw_sdk

    log_success "Plugin files installed"
}

# ─── SDK Symlink Helper ──────────────────────────────────────────────────────

_link_openclaw_sdk() {
    # index.ts imports openclaw/plugin-sdk which must be resolvable via node_modules
    local target_dir="$PLUGIN_PATH/node_modules"
    mkdir -p "$target_dir"

    # Already linked?
    if [ -d "$target_dir/openclaw" ] || [ -L "$target_dir/openclaw" ]; then
        log_success "OpenClaw SDK already linked"
        return
    fi

    local sdk_path=""

    # 1. Check other installed plugins
    for ext_dir in "$OPENCLAW_HOME/extensions"/*/; do
        local candidate="$ext_dir/node_modules/openclaw"
        if [ -d "$candidate" ] && [ "$(basename "$ext_dir")" != "$PLUGIN_NAME" ]; then
            sdk_path="$candidate"
            break
        fi
    done

    # 2. Check global openclaw install via which
    if [ -z "$sdk_path" ]; then
        local openclaw_bin
        openclaw_bin=$(which openclaw 2>/dev/null || true)
        if [ -n "$openclaw_bin" ]; then
            # Resolve symlinks to find actual install
            local real_bin
            real_bin=$(readlink -f "$openclaw_bin" 2>/dev/null || realpath "$openclaw_bin" 2>/dev/null || echo "$openclaw_bin")
            local global_dir
            global_dir=$(dirname "$(dirname "$real_bin")")/lib/node_modules/openclaw
            if [ -d "$global_dir" ]; then
                sdk_path="$global_dir"
            fi
        fi
    fi

    # 3. Check common nvm/node paths
    if [ -z "$sdk_path" ]; then
        for candidate in \
            "$HOME/.nvm/versions/node"/*/lib/node_modules/openclaw \
            /usr/local/lib/node_modules/openclaw \
            /usr/lib/node_modules/openclaw; do
            if [ -d "$candidate" ]; then
                sdk_path="$candidate"
                break
            fi
        done
    fi

    if [ -n "$sdk_path" ]; then
        ln -s "$sdk_path" "$target_dir/openclaw"
        log_success "OpenClaw SDK linked from $sdk_path"

        # Also link @sinclair/typebox (used by agent tool schemas)
        local typebox_path
        typebox_path=$(dirname "$sdk_path")/@sinclair/typebox
        if [ -d "$typebox_path" ]; then
            mkdir -p "$target_dir/@sinclair"
            ln -s "$typebox_path" "$target_dir/@sinclair/typebox"
            log_success "@sinclair/typebox linked"
        fi
    else
        log_warning "Could not find OpenClaw SDK — index.ts may fail to load"
        log_info "  Fix manually: ln -s \$(find ~/.openclaw/extensions -path '*/node_modules/openclaw' -maxdepth 3 | head -1) $target_dir/openclaw"
    fi
}

# ─── Step 3: Create required directories ─────────────────────────────────────

create_data_directories() {
    log_step 3 "Creating data directories"

    local dirs=(
        "$OPENCLAW_HOME/data/knowledge"
        "$OPENCLAW_HOME/data/automation"
        "$OPENCLAW_HOME/data/approval-cache"
        "$OPENCLAW_HOME/data/project-sessions"
        "$OPENCLAW_HOME/provenance"
        "$OPENCLAW_HOME/agent-ids"
        "$PLUGIN_PATH/logs"
    )

    for dir in "${dirs[@]}"; do
        mkdir -p "$dir"
    done

    log_success "Knowledge directory: $OPENCLAW_HOME/data/knowledge/"
    log_success "Automation directory: $OPENCLAW_HOME/data/automation/"
    log_success "Provenance directory: $OPENCLAW_HOME/provenance/"
    log_success "Agent IDs directory: $OPENCLAW_HOME/agent-ids/"
}

# ─── Step 4: Generate env config ─────────────────────────────────────────────

generate_env_config() {
    log_step 4 "Generating environment config"

    local env_file="$PLUGIN_PATH/config/.engram.env"

    if [ -f "$env_file" ]; then
        log_warning "Config already exists at $env_file (preserving)"
        return
    fi

    # Map context engine to env value
    local context_engine_env=""
    if [ "$WIZARD_CONTEXT_ENGINE_RESOLVED" = "lossless-claw" ]; then
        context_engine_env="LACP_CONTEXT_ENGINE=lossless-claw"
    else
        context_engine_env="LACP_CONTEXT_ENGINE=file-based"
    fi

    cat > "$env_file" << ENVEOF
# ============================================================================
# OpenClaw LACP Fusion — Environment Configuration
# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# OS: $DETECTED_OS | Installer: v${PLUGIN_VERSION} (wizard)
# ============================================================================

# Layer 2: Knowledge Graph
LACP_OBSIDIAN_VAULT=$DETECTED_VAULT
LACP_KNOWLEDGE_ROOT=$OPENCLAW_HOME/data/knowledge
LACP_AUTOMATION_ROOT=$OPENCLAW_HOME/data/automation

# Context Engine
$context_engine_env

# Layer 5: Provenance
PROVENANCE_ROOT=$OPENCLAW_HOME/provenance
AGENT_ID_STORE=$OPENCLAW_HOME/agent-ids

# Feature Flags
LACP_LOCAL_FIRST=$WIZARD_LOCAL_FIRST
LACP_WITH_GITNEXUS=false
CODE_GRAPH_ENABLED=$WIZARD_CODE_GRAPH

# Operating Mode
LACP_MODE=$WIZARD_MODE
LACP_MUTATIONS_ENABLED=$([ "$WIZARD_MODE" = "connected" ] && echo "false" || echo "true")
$([ "$WIZARD_MODE" != "standalone" ] && [ -n "$WIZARD_CURATOR_URL" ] && echo "LACP_CURATOR_URL=$WIZARD_CURATOR_URL")
$([ "$WIZARD_MODE" = "connected" ] && [ -n "$WIZARD_CURATOR_TOKEN" ] && echo "LACP_CURATOR_TOKEN=$WIZARD_CURATOR_TOKEN")

# Hooks
OPENCLAW_HOOKS_PROFILE=$WIZARD_PROFILE

# To customize further, see the full template at:
# $PLUGIN_PATH/config/.engram.env.template
ENVEOF

    log_success "Config generated at $env_file"

    # Generate guard-rules.json with wizard settings
    local guard_config="$PLUGIN_PATH/config/guard-rules.json"
    if [ -f "$guard_config" ]; then
        log_warning "Guard config already exists at $guard_config (preserving)"
    elif [ -f "$SCRIPT_DIR/plugin/config/guard-rules.json" ]; then
        cp "$SCRIPT_DIR/plugin/config/guard-rules.json" "$guard_config"

        # Apply wizard guard level
        if [ "$HAS_JQ" = "true" ] && [ -n "$WIZARD_GUARD_LEVEL" ]; then
            local tmp
            tmp=$(mktemp)
            jq --arg level "$WIZARD_GUARD_LEVEL" '.defaults.block_level = $level' "$guard_config" > "$tmp" && mv "$tmp" "$guard_config"
            log_success "Guard default block level set to: $WIZARD_GUARD_LEVEL"
        fi

        # Apply disabled rules from wizard
        if [ "$HAS_JQ" = "true" ] && [ "${#WIZARD_DISABLED_RULES[@]}" -gt 0 ]; then
            for rule_id in "${WIZARD_DISABLED_RULES[@]}"; do
                local tmp
                tmp=$(mktemp)
                jq --arg rid "$rule_id" '
                    .rules = [.rules[] | if .id == $rid then .enabled = false else . end]
                ' "$guard_config" > "$tmp" && mv "$tmp" "$guard_config"
            done
            log_success "${#WIZARD_DISABLED_RULES[@]} guard rule(s) disabled per wizard selection"
        fi

        log_success "Guard config generated at $guard_config"
    else
        log_warning "Guard config template not found — will use factory defaults at runtime"
    fi
}

# ─── Step 5: Write Engram config + host pointers ────────────────────────────

write_engram_config() {
    log_step 5 "Writing Engram config"

    mkdir -p "$ENGRAM_HOME"
    if [ -f "$ENGRAM_CONFIG" ]; then
        cp "$ENGRAM_CONFIG" "$ENGRAM_CONFIG.bak.$(date +%s)"
        log_info "Engram config backed up"
    fi

    # Defaults so nothing trips set -u
    local WIZARD_CURATOR_URL_SAFE="${WIZARD_CURATOR_URL:-}"
    local WIZARD_CONTEXT_ENGINE_SAFE="${WIZARD_CONTEXT_ENGINE_RESOLVED:-lossless-claw}"

    local mutations_enabled="true"
    if [ "$WIZARD_MODE" = "connected" ]; then
        mutations_enabled="false"
    fi

    # Pre-expand host paths so we never emit literal "~" into JSON
    local OPENCLAW_HOME_SAFE="${OPENCLAW_HOME:-$HOME/.openclaw}"
    local CLAUDE_HOME_SAFE="${CLAUDE_HOME:-$HOME/.claude}"
    local CODEX_HOME_SAFE="${CODEX_HOME:-$HOME/.codex}"

    if [ "$HAS_JQ" = "true" ]; then
        local tmp
        tmp=$(mktemp)
        jq -n \
            --arg vault "$DETECTED_VAULT" \
            --arg kr "$ENGRAM_HOME/knowledge" \
            --arg ar "$ENGRAM_HOME/automation" \
            --arg profile "$WIZARD_PROFILE" \
            --arg tier "$WIZARD_POLICY_TIER" \
            --argjson cg "$WIZARD_CODE_GRAPH" \
            --argjson prov "$WIZARD_PROVENANCE" \
            --argjson lf "$WIZARD_LOCAL_FIRST" \
            --arg ce "$WIZARD_CONTEXT_ENGINE_SAFE" \
            --arg mode "$WIZARD_MODE" \
            --argjson mut "$mutations_enabled" \
            --arg curatorUrl "$WIZARD_CURATOR_URL_SAFE" \
            --arg openclawHome "$OPENCLAW_HOME_SAFE" \
            --arg claudeHome "$CLAUDE_HOME_SAFE" \
            --arg codexHome "$CODEX_HOME_SAFE" \
            --argjson cch null \
            --argjson ccd null '
            {
              schemaVersion: 1,
              profile: $profile,
              vaultPath: $vault,
              knowledgeRoot: $kr,
              automationRoot: $ar,
              mode: $mode,
              mutationsEnabled: $mut,
              agentRole: "developer",
              curator: {
                url: (if $curatorUrl == "" then null else $curatorUrl end),
                token: null
              },
              features: {
                localFirst: $lf,
                provenanceEnabled: $prov,
                codeGraphEnabled: $cg,
                contextEngine: (if $ce == "" then null else $ce end)
              },
              policy: {
                tier: $tier,
                approvalCacheTtlMinutes: 60,
                costCeilingHourlyUsd: $cch,
                costCeilingDailyUsd: $ccd
              },
              lcm: {
                queryBatchSize: 32,
                promotionThreshold: 5,
                autoDiscoveryInterval: "daily"
              },
              qmd: { collections: [] },
              hosts: {
                openclaw: $openclawHome,
                claudeCode: $claudeHome,
                codex: $codexHome
              }
            }' > "$tmp"
        mv "$tmp" "$ENGRAM_CONFIG"
        log_success "Wrote $ENGRAM_CONFIG"
    else
        log_warning "jq not installed — falling back to engram-migrate-config"
        python3 "$SCRIPT_DIR/bin/engram-migrate-config" --target "$ENGRAM_HOME"
    fi
}

update_host_pointers() {
    # Leave a tiny pointer in openclaw.json so OpenClaw still discovers Engram,
    # but the actual config lives in ~/.engram/config.json.
    if [ "$HAS_JQ" != "true" ] || [ ! -f "$GATEWAY_CONFIG" ]; then
        return
    fi
    cp "$GATEWAY_CONFIG" "$GATEWAY_CONFIG.bak.$(date +%s)"
    local tmp
    tmp=$(mktemp)
    jq --arg cfg "$ENGRAM_CONFIG" '
      .plugins.allow = (
        if (.plugins.allow | index("engram")) then .plugins.allow
        else .plugins.allow + ["engram"]
        end
      )
      | .plugins.entries["engram"] = {
          "enabled": true,
          "configRef": $cfg
        }
    ' "$GATEWAY_CONFIG" > "$tmp" && mv "$tmp" "$GATEWAY_CONFIG"
    log_success "Updated openclaw.json to point at $ENGRAM_CONFIG"
}

# ─── Step 6: Initialize Obsidian vault ───────────────────────────────────────

init_obsidian_vault() {
    log_step 6 "Checking Obsidian vault"

    if [ -d "$DETECTED_VAULT" ]; then
        log_success "Obsidian vault exists at $DETECTED_VAULT"
    else
        log_info "Creating Obsidian vault directory at $DETECTED_VAULT"
        mkdir -p "$DETECTED_VAULT"
        log_success "Obsidian vault directory created"
    fi
}

# ─── Step 7: Initialize stack and integrations ────────────────────────────

INSTALL_LOG="${OPENCLAW_HOME:-$HOME/.openclaw}/logs/install-$(date +%Y%m%d-%H%M%S).log"
mkdir -p "$(dirname "$INSTALL_LOG")" 2>/dev/null || true

_run_init_task() {
    # Run a task with animated dots: _run_init_task "label" "command" timeout_secs
    local label="$1"
    local cmd="$2"
    local timeout_secs="${3:-30}"

    printf "  ${DIM}%-30s${NC} " "$label"

    # Log the command being run
    echo "--- $label ---" >> "$INSTALL_LOG"
    echo "cmd: $cmd" >> "$INSTALL_LOG"
    echo "timeout: ${timeout_secs}s" >> "$INSTALL_LOG"
    echo "started: $(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$INSTALL_LOG"

    # Run command in background, capture output to log
    bash -c "$cmd" >> "$INSTALL_LOG" 2>&1 &
    local pid=$!

    # Animate dots while waiting, with manual timeout
    local dots=""
    local elapsed=0
    while kill -0 "$pid" 2>/dev/null; do
        if [ "$elapsed" -ge "$timeout_secs" ]; then
            kill "$pid" 2>/dev/null || true
            wait "$pid" 2>/dev/null || true  # ignore exit code from killed process
            echo "exit: timeout after ${timeout_secs}s ($(date -u +%Y-%m-%dT%H:%M:%SZ))" >> "$INSTALL_LOG"
            printf "\r  %-30s ${YELLOW}— timed out${NC}     \n" "$label"
            return 0
        fi
        dots="${dots}."
        if [ ${#dots} -gt 5 ]; then
            dots="."
        fi
        printf "\r  ${DIM}%-30s${NC} ${DIM}%-5s${NC}" "$label" "$dots"
        sleep 0.3
        elapsed=$((elapsed + 1))  # roughly 0.3s per tick, close enough
    done

    # Check result — capture exit code without triggering set -e
    local exit_code=0
    wait "$pid" 2>/dev/null || exit_code=$?
    echo "exit: $exit_code ($(date -u +%Y-%m-%dT%H:%M:%SZ))" >> "$INSTALL_LOG"
    echo "" >> "$INSTALL_LOG"

    if [ $exit_code -eq 0 ]; then
        printf "\r  %-30s ${GREEN}✓${NC}     \n" "$label"
    else
        printf "\r  %-30s ${YELLOW}— failed${NC}     \n" "$label"
    fi

    return 0
}

init_stack_and_integrations() {
    log_step 7 "Initializing memory stack and integrations"
    echo ""

    local bin_dir="$PLUGIN_PATH/bin"
    local total=0
    local done=0

    # Count tasks
    [ -d "$DETECTED_VAULT" ] && [ -x "$bin_dir/engram-brain-graph" ] && (( total++ )) || true
    [ -x "$bin_dir/engram-agent-id" ] && (( total++ )) || true
    [ "$WIZARD_PROVENANCE" = "true" ] && [ -x "$bin_dir/engram-provenance" ] && (( total++ )) || true
    [ "$WIZARD_CONTEXT_ENGINE_RESOLVED" = "lossless-claw" ] && [ "$HAS_JQ" = "true" ] && (( total++ )) || true
    [ "$WIZARD_CODE_GRAPH" = "true" ] && (( total++ )) || true
    command -v qmd &>/dev/null && [ -d "$DETECTED_VAULT" ] && (( total++ )) || true

    # Note: Knowledge graph init, agent identity, and provenance chain are
    # per-project and initialize automatically when an agent first works on
    # a repo (via the session-start hook). They don't belong in global setup.
    printf "  %-30s ${DIM}per-project (auto on first session)${NC}\n" "Knowledge graph"
    printf "  %-30s ${DIM}per-project (auto on first session)${NC}\n" "Agent identity"
    printf "  %-30s ${DIM}per-project (auto on first session)${NC}\n" "Provenance chain"

    # Lossless-claw config
    if [ "$WIZARD_CONTEXT_ENGINE_RESOLVED" = "lossless-claw" ] && [ "$HAS_JQ" = "true" ]; then
        _run_init_task "Lossless-claw config" \
          "tmp=\$(mktemp) && jq '.features.contextEngine = \"lossless-claw\"' '$ENGRAM_CONFIG' > \"\$tmp\" && mv \"\$tmp\" '$ENGRAM_CONFIG'" 5 || true
    fi

    # GitNexus / code graph
    if [ "$WIZARD_CODE_GRAPH" = "true" ]; then
        if command -v gitnexus &>/dev/null; then
            if [ "$HAS_JQ" = "true" ]; then
                _run_init_task "Code graph config" \
                  "tmp=\$(mktemp) && jq '.features.codeGraphEnabled = true' '$ENGRAM_CONFIG' > \"\$tmp\" && mv \"\$tmp\" '$ENGRAM_CONFIG'" 5 || true
            fi
            if [ -x "$bin_dir/engram-brain-graph" ]; then
                _run_init_task "MCP server configs" "bash '$bin_dir/engram-brain-graph' mcp-config '$DETECTED_VAULT' --output '$PLUGIN_PATH/config/mcp-servers.json'" 15 || true
            fi
            log_info "  Run 'engram brain analyze' to index your codebase"
        else
            printf "  ${YELLOW}[  — ]${NC} Code graph ${DIM}(GitNexus not installed — run: npm install -g gitnexus)${NC}\n"
        fi
    fi

    # QMD indexing
    export PATH="$HOME/.bun/bin:$PATH"
    if command -v qmd &>/dev/null && [ -d "$DETECTED_VAULT" ]; then
        _run_init_task "QMD vault indexing" "cd '$DETECTED_VAULT' && qmd update && qmd embed" 120 || true
    fi

    echo ""
    echo -e "  ${DIM}Log: ${INSTALL_LOG}${NC}"
    echo ""
}

# ─── Step 8: Write TOOLS.md to agent workspaces ───────────────────────────

write_tools_md() {
    log_step 8 "Configuring agent workspaces"

    local template_file="$PLUGIN_PATH/templates/tools-engram.md"

    if [ ! -f "$template_file" ]; then
        log_warning "Engram TOOLS.md template not found — skipping workspace setup"
        return
    fi

    # Read selected agents from wizard config
    local config_file="/tmp/engram-wizard-config.json"
    local agent_count=0

    if [ -f "$config_file" ] && command -v node &>/dev/null; then
        agent_count=$(node -p "
            var c = JSON.parse(require('fs').readFileSync('$config_file','utf8'));
            (c.agents && c.agents.selected) ? c.agents.selected.length : 0
        " 2>/dev/null || echo "0")
    fi

    if [ "$agent_count" = "0" ]; then
        log_info "No agents selected — skipping TOOLS.md generation"
        return
    fi

    # Get agent workspaces as JSON
    local workspaces_json
    workspaces_json=$(node -p "
        var c = JSON.parse(require('fs').readFileSync('$config_file','utf8'));
        JSON.stringify(c.agents.workspaces || {})
    " 2>/dev/null || echo "{}")

    # Iterate over selected agents
    local agents_json
    agents_json=$(node -p "
        var c = JSON.parse(require('fs').readFileSync('$config_file','utf8'));
        JSON.stringify(c.agents.selected || [])
    " 2>/dev/null || echo "[]")

    # Parse agents array
    local agent_ids
    agent_ids=$(echo "$agents_json" | python3 -c "import json,sys; [print(a) for a in json.load(sys.stdin)]" 2>/dev/null || true)

    local updated=0
    local created=0

    while IFS= read -r agent_id; do
        [ -z "$agent_id" ] && continue

        # Get workspace path for this agent
        local workspace
        workspace=$(echo "$workspaces_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('$agent_id',''))" 2>/dev/null || echo "")

        if [ -z "$workspace" ] || [ ! -d "$workspace" ]; then
            log_warning "Agent '$agent_id': no workspace directory found — skipping"
            continue
        fi

        local tools_file="$workspace/TOOLS.md"

        if [ -f "$tools_file" ]; then
            # Check if engram section already exists
            if grep -q "## Engram" "$tools_file" 2>/dev/null; then
                log_info "Agent '$agent_id': TOOLS.md already has Engram section — skipping"
                continue
            fi
            # Append
            echo "" >> "$tools_file"
            cat "$template_file" >> "$tools_file"
            log_success "Agent '$agent_id': appended Engram docs to TOOLS.md"
            (( updated++ )) || true
        else
            # Create new
            echo "# Tools" > "$tools_file"
            echo "" >> "$tools_file"
            cat "$template_file" >> "$tools_file"
            log_success "Agent '$agent_id': created TOOLS.md with Engram docs"
            (( created++ )) || true
        fi
    done <<< "$agent_ids"

    if [ $((updated + created)) -gt 0 ]; then
        log_success "Updated $updated / created $created TOOLS.md file(s)"
    fi

    # ── Write shared/ENGRAM.md (single source of truth) ──────────────────
    local shared_dir="$HOME/.openclaw/shared"
    mkdir -p "$shared_dir"

    local engram_shared="$shared_dir/ENGRAM.md"
    local engram_shared_template="$PLUGIN_PATH/templates/engram-shared.md"
    if [ -f "$engram_shared_template" ]; then
        cp "$engram_shared_template" "$engram_shared"
        log_success "Wrote shared/ENGRAM.md (memory workflow for all agents)"
    else
        log_warning "engram-shared.md template not found — shared/ENGRAM.md not updated"
    fi

    # ── Generate shared/repositories.json from GitNexus registry ──────────
    local repo_init="$PLUGIN_PATH/bin/engram-repo-init"
    if [ -x "$repo_init" ] || [ -f "$repo_init" ]; then
        python3 "$repo_init" 2>/dev/null && log_success "Generated shared/repositories.json from GitNexus registry" \
            || log_warning "repositories.json generation failed — run 'engram repo init' manually"
    else
        log_info "engram-repo-init not found — skipping repositories.json generation"
    fi

    # ── Add ENGRAM.md reference to agent AGENTS.md files ──────────────────
    # Only inject a single reference line, never the full boilerplate.
    local agents_ref_updated=0

    while IFS= read -r agent_id; do
        [ -z "$agent_id" ] && continue

        local workspace
        workspace=$(echo "$workspaces_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('$agent_id',''))" 2>/dev/null || echo "")

        if [ -z "$workspace" ] || [ ! -d "$workspace" ]; then
            continue
        fi

        local agents_file="$workspace/AGENTS.md"

        if [ -f "$agents_file" ]; then
            # Skip if already references ENGRAM.md
            if grep -q "ENGRAM.md" "$agents_file" 2>/dev/null; then
                continue
            fi
            # Remove old full boilerplate if present
            if grep -q "## Engram — Memory-First Workflow" "$agents_file" 2>/dev/null; then
                python3 -c "
import re, sys
with open('$agents_file', 'r') as f:
    content = f.read()
content = re.sub(r'\n*## Engram — Memory-First Workflow.*', '', content, flags=re.DOTALL)
with open('$agents_file', 'w') as f:
    f.write(content.rstrip() + '\n')
" 2>/dev/null || true
            fi
            # Append slim reference
            echo "" >> "$agents_file"
            echo "## Engram" >> "$agents_file"
            echo "- [\`ENGRAM.md\`](~/.openclaw/shared/ENGRAM.md) — memory workflow (non-negotiable, read every session)" >> "$agents_file"
            (( agents_ref_updated++ )) || true
        fi
    done <<< "$agent_ids"

    if [ "$agents_ref_updated" -gt 0 ]; then
        log_success "Added ENGRAM.md reference to $agents_ref_updated AGENTS.md file(s)"
    fi
}

# ─── Step 9: Platform setup (Claude Code / Codex) ───────────────────────────

setup_platforms() {
    local platforms="${WIZARD_PLATFORMS:-}"
    if [ -z "$platforms" ]; then
        log_info "No platforms selected — skipping platform setup"
        return
    fi

    log_step 9 "Setting up platform integrations"

    # Claude Code: install hooks + MCP server
    if echo "$platforms" | grep -q "claude-code"; then
        log_info "Configuring Claude Code..."

        # Hooks
        local hooks_script="$PLUGIN_PATH/hooks/adapters/setup-claude-code.sh"
        if [ -f "$hooks_script" ]; then
            bash "$hooks_script" --global 2>/dev/null && \
                log_success "Claude Code hooks installed (global)" || \
                log_warning "Claude Code hooks setup had issues"
        fi

        # MCP server
        local mcp_script="$PLUGIN_PATH/mcp/setup-mcp.sh"
        if [ -f "$mcp_script" ]; then
            bash "$mcp_script" --global 2>/dev/null && \
                log_success "Claude Code MCP server registered (global)" || \
                log_warning "Claude Code MCP setup had issues"
        fi

        # Install MCP dependencies
        local mcp_dir="$PLUGIN_PATH/mcp"
        if [ -f "$mcp_dir/package.json" ]; then
            (cd "$mcp_dir" && npm install --production 2>/dev/null) && \
                log_success "MCP server dependencies installed" || \
                log_warning "MCP dependency install had issues — run: cd $mcp_dir && npm install"
        fi

        # Copy rules files
        if [ -f "$PLUGIN_PATH/rules/ENGRAM.md" ]; then
            log_info "Engram behavioral rules available at: $PLUGIN_PATH/rules/ENGRAM.md"
            log_info "Append to your project CLAUDE.md for automatic memory behaviors"
        fi
    fi

    # Codex: MCP server only
    if echo "$platforms" | grep -q "codex"; then
        log_info "Configuring Codex..."

        # MCP server (same as Claude Code, but user places in .codex/mcp.json)
        local mcp_script="$PLUGIN_PATH/mcp/setup-mcp.sh"
        if [ -f "$mcp_script" ]; then
            local mcp_json
            mcp_json=$(bash "$mcp_script" --print 2>/dev/null | head -n -1)
            if [ -n "$mcp_json" ]; then
                log_success "Codex MCP config generated"
                log_info "To activate: save the mcpServers block to .codex/mcp.json in your repo"
                log_info "Run: bash $mcp_script --print"
            fi
        fi

        # Install MCP dependencies (if not already done for claude-code)
        local mcp_dir="$PLUGIN_PATH/mcp"
        if [ -f "$mcp_dir/package.json" ] && [ ! -d "$mcp_dir/node_modules" ]; then
            (cd "$mcp_dir" && npm install --production 2>/dev/null) && \
                log_success "MCP server dependencies installed" || \
                log_warning "MCP dependency install had issues"
        fi
    fi

    # OpenClaw: native plugin (already handled by main install)
    if echo "$platforms" | grep -q "openclaw"; then
        log_success "OpenClaw: native plugin already configured via gateway"
    fi
}

# ─── Step 10: Run validation ────────────────────────────────────────────────

run_validation() {
    log_step 9 "Validating installation"

    local pass=0
    local fail=0

    # Check plugin manifest
    if [ -f "$PLUGIN_PATH/openclaw.plugin.json" ]; then
        (( pass++ )) || true
        log_success "openclaw.plugin.json present"
        # Verify kind and name fields
        if [ "$HAS_JQ" = "true" ]; then
            if jq -e '.kind' "$PLUGIN_PATH/openclaw.plugin.json" &>/dev/null && \
               jq -e '.name' "$PLUGIN_PATH/openclaw.plugin.json" &>/dev/null; then
                (( pass++ )) || true
                log_success "Manifest has required 'kind' and 'name' fields"
            else
                log_warning "Manifest missing 'kind' or 'name' field — gateway may reject"
                (( fail++ )) || true
            fi
        fi
    else
        log_error "Missing openclaw.plugin.json"
        (( fail++ )) || true
    fi

    # Check package.json with required fields
    if [ -f "$PLUGIN_PATH/package.json" ]; then
        (( pass++ )) || true
        log_success "package.json present"
        if [ "$HAS_JQ" = "true" ]; then
            local pkg_ok=true
            jq -e '.type == "module"' "$PLUGIN_PATH/package.json" &>/dev/null || pkg_ok=false
            jq -e '.main == "index.ts"' "$PLUGIN_PATH/package.json" &>/dev/null || pkg_ok=false
            jq -e '.openclaw.extensions' "$PLUGIN_PATH/package.json" &>/dev/null || pkg_ok=false
            if [ "$pkg_ok" = "true" ]; then
                (( pass++ )) || true
                log_success "package.json has required fields (type, main, openclaw.extensions)"
            else
                log_warning "package.json missing required fields — gateway may not discover plugin"
                (( fail++ )) || true
            fi
        fi
    else
        log_error "Missing package.json"
        (( fail++ )) || true
    fi

    # Check index.ts entry point
    if [ -f "$PLUGIN_PATH/index.ts" ]; then
        (( pass++ )) || true
        log_success "index.ts entry point present"
    else
        log_error "Missing index.ts — gateway cannot load plugin"
        (( fail++ )) || true
    fi

    # Check OpenClaw SDK symlink
    if [ -d "$PLUGIN_PATH/node_modules/openclaw" ] || [ -L "$PLUGIN_PATH/node_modules/openclaw" ]; then
        (( pass++ )) || true
        log_success "OpenClaw SDK linked in node_modules"
    else
        log_warning "OpenClaw SDK not found in node_modules — index.ts imports will fail"
        (( fail++ )) || true
    fi

    # Check hooks handlers
    for handler in session-start pretool-guard stop-quality-gate write-validate; do
        if [ -f "$PLUGIN_PATH/hooks/handlers/${handler}.py" ]; then
            (( pass++ )) || true
        else
            log_warning "Missing hook handler: ${handler}.py"
            (( fail++ )) || true
        fi
    done

    # Check bin scripts exist
    local bin_count
    bin_count=$(ls -1 "$PLUGIN_PATH/bin"/engram-* 2>/dev/null | wc -l | tr -d ' ')
    if [ "$bin_count" -gt 0 ]; then
        (( pass++ )) || true
        log_success "$bin_count bin scripts installed"
    else
        log_warning "No bin scripts found"
        (( fail++ )) || true
    fi

    # Check guard config
    if [ -f "$PLUGIN_PATH/config/guard-rules.json" ]; then
        (( pass++ )) || true
        log_success "Guard config present"
    else
        log_warning "Guard config missing — will use factory defaults"
    fi

    # Check gateway registration
    if [ "$HAS_JQ" = "true" ]; then
        if jq -e '.plugins.entries["engram"].enabled' "$GATEWAY_CONFIG" &>/dev/null; then
            (( pass++ )) || true
            log_success "Plugin registered in gateway config"
        else
            log_warning "Plugin not registered in gateway config"
            (( fail++ )) || true
        fi

        # Verify gateway config is valid JSON
        if jq '.' "$GATEWAY_CONFIG" &>/dev/null; then
            (( pass++ )) || true
            log_success "Gateway config is valid JSON"
        else
            log_error "Gateway config has JSON syntax errors"
            (( fail++ )) || true
        fi
    fi

    # Check data directories
    for dir in "$OPENCLAW_HOME/data/knowledge" "$OPENCLAW_HOME/provenance"; do
        if [ -d "$dir" ]; then
            (( pass++ )) || true
        else
            (( fail++ )) || true
        fi
    done

    echo ""
    if [ "$fail" -eq 0 ]; then
        log_success "Validation passed ($pass checks)"
    else
        log_warning "Validation: $pass passed, $fail warnings"
    fi
}

# ─── Step 8: Summary ────────────────────────────────────────────────────────

print_summary() {
    log_step 10 "Installation complete"

    echo ""
    echo -e "${GREEN}✓ Engram v${PLUGIN_VERSION} installed${NC}"
    echo ""
    echo -e "${BOLD}Configuration:${NC}"
    echo -e "  ${GREEN}✓${NC} Plugin:       $PLUGIN_PATH"
    echo -e "  ${GREEN}✓${NC} Vault:        $DETECTED_VAULT"
    echo -e "  ${GREEN}✓${NC} Engine:       $WIZARD_CONTEXT_ENGINE_RESOLVED"
    echo -e "  ${GREEN}✓${NC} Profile:      $WIZARD_PROFILE"
    echo -e "  ${GREEN}✓${NC} Policy tier:  $WIZARD_POLICY_TIER"
    echo -e "  ${GREEN}✓${NC} Mode:         $WIZARD_MODE"
    echo ""
    echo -e "${BOLD}Next steps:${NC}"
    echo "  1. Restart OpenClaw:     openclaw gateway restart"
    echo "  2. Check status:         engram status"
    echo "  3. Run diagnostics:      engram doctor"
    echo "  4. Query memory:         engram memory query <topic>"
    echo ""
    echo -e "${BOLD}Locations:${NC}"
    echo "  Config:  $PLUGIN_PATH/config/.engram.env"
    echo "  Gateway: $GATEWAY_CONFIG"
    echo "  Engram config: $ENGRAM_CONFIG"
    echo "  Logs:    $PLUGIN_PATH/logs/"
    echo "  Docs:    $PLUGIN_PATH/docs/"
    echo ""
    echo -e "${BOLD}Profiles:${NC}"
    echo "  autonomous    — all hooks, warn-only (agents keep working)"
    echo "  balanced      — session context + quality gate (default)"
    echo "  context-only  — just git context injection"
    echo "  guard-rail    — safety gates, no context injection"
    echo "  minimal-stop  — quality gate only (lightweight)"
    echo "  hardened-exec — all hooks, blocks dangerous ops"
    echo "  full-audit    — all hooks, strict mode, verbose logging"
    echo ""
}

# ─── Load config from JSON file (--from-config mode) ────────────────────────

load_config_from_json() {
    local config_file="$1"

    if [ ! -f "$config_file" ]; then
        log_error "Config file not found: $config_file"
        exit 1
    fi

    if ! command -v node &>/dev/null; then
        log_error "node is required to parse wizard config JSON"
        exit 1
    fi

    # Parse JSON config using node (portable, no jq dependency for this step)
    WIZARD_VAULT=$(node -p "JSON.parse(require('fs').readFileSync('$config_file','utf8')).vault_path" 2>/dev/null)
    WIZARD_CONTEXT_ENGINE=$(node -p "JSON.parse(require('fs').readFileSync('$config_file','utf8')).context_engine" 2>/dev/null)
    WIZARD_PROFILE=$(node -p "JSON.parse(require('fs').readFileSync('$config_file','utf8')).profile" 2>/dev/null)
    WIZARD_MODE=$(node -p "JSON.parse(require('fs').readFileSync('$config_file','utf8')).mode" 2>/dev/null)
    WIZARD_POLICY_TIER=$(node -p "JSON.parse(require('fs').readFileSync('$config_file','utf8')).policy_tier" 2>/dev/null)
    WIZARD_CODE_GRAPH=$(node -p "JSON.parse(require('fs').readFileSync('$config_file','utf8')).code_graph" 2>/dev/null)
    WIZARD_PROVENANCE=$(node -p "JSON.parse(require('fs').readFileSync('$config_file','utf8')).provenance" 2>/dev/null)
    WIZARD_GUARD_LEVEL=$(node -p "JSON.parse(require('fs').readFileSync('$config_file','utf8')).guard_level" 2>/dev/null)
    WIZARD_CURATOR_URL=$(node -p "var v=JSON.parse(require('fs').readFileSync('$config_file','utf8')).curator_url;v||''" 2>/dev/null)
    WIZARD_CURATOR_TOKEN=$(node -p "var v=JSON.parse(require('fs').readFileSync('$config_file','utf8')).curator_token;v||''" 2>/dev/null)

    # Defaults for values the wizard may not set
    WIZARD_LOCAL_FIRST="true"
    WIZARD_DISABLED_RULES=()
    WIZARD_RULE_OVERRIDES=()

    # Validate required fields
    if [ -z "$WIZARD_VAULT" ] || [ "$WIZARD_VAULT" = "undefined" ]; then
        log_error "Missing vault_path in config file"
        exit 1
    fi
    if [ -z "$WIZARD_PROFILE" ] || [ "$WIZARD_PROFILE" = "undefined" ]; then
        log_error "Missing profile in config file"
        exit 1
    fi

    # Set defaults for optional fields
    if [ -z "$WIZARD_MODE" ] || [ "$WIZARD_MODE" = "undefined" ]; then WIZARD_MODE="standalone"; fi
    if [ -z "$WIZARD_CONTEXT_ENGINE" ] || [ "$WIZARD_CONTEXT_ENGINE" = "undefined" ]; then WIZARD_CONTEXT_ENGINE="file-based"; fi
    if [ -z "$WIZARD_POLICY_TIER" ] || [ "$WIZARD_POLICY_TIER" = "undefined" ]; then WIZARD_POLICY_TIER="review"; fi
    if [ -z "$WIZARD_CODE_GRAPH" ] || [ "$WIZARD_CODE_GRAPH" = "undefined" ]; then WIZARD_CODE_GRAPH="false"; fi
    if [ -z "$WIZARD_PROVENANCE" ] || [ "$WIZARD_PROVENANCE" = "undefined" ]; then WIZARD_PROVENANCE="true"; fi
    if [ -z "$WIZARD_GUARD_LEVEL" ] || [ "$WIZARD_GUARD_LEVEL" = "undefined" ]; then WIZARD_GUARD_LEVEL="block"; fi

    # Resolve context engine (same logic as interactive wizard, but non-interactive)
    if [ "$WIZARD_CONTEXT_ENGINE" = "lossless-claw" ]; then
        if [ -d "$OPENCLAW_HOME/extensions/lossless-claw" ]; then
            WIZARD_CONTEXT_ENGINE_RESOLVED="lossless-claw"
        else
            log_warning "lossless-claw not installed — falling back to file-based"
            WIZARD_CONTEXT_ENGINE_RESOLVED="file-based"
        fi
    elif [ "$WIZARD_CONTEXT_ENGINE" = "auto" ]; then
        if [ -d "$OPENCLAW_HOME/extensions/lossless-claw" ]; then
            WIZARD_CONTEXT_ENGINE_RESOLVED="lossless-claw"
        else
            WIZARD_CONTEXT_ENGINE_RESOLVED="file-based"
        fi
    else
        WIZARD_CONTEXT_ENGINE_RESOLVED="$WIZARD_CONTEXT_ENGINE"
    fi

    # Parse platforms array
    WIZARD_PLATFORMS=$(node -p "
        var c = JSON.parse(require('fs').readFileSync('$config_file','utf8'));
        (c.platforms || []).join(',')
    " 2>/dev/null || echo "")

    # Set DETECTED_VAULT for use by installation steps
    DETECTED_VAULT="$WIZARD_VAULT"

    log_success "Loaded wizard config from $config_file"
    echo ""
    echo -e "${BOLD}Configuration (from wizard):${NC}"
    echo -e "  Vault:           ${GREEN}${WIZARD_VAULT}${NC}"
    echo -e "  Context engine:  ${GREEN}${WIZARD_CONTEXT_ENGINE_RESOLVED}${NC}"
    echo -e "  Safety profile:  ${GREEN}${WIZARD_PROFILE}${NC}"
    echo -e "  Operating mode:  ${GREEN}${WIZARD_MODE}${NC}"
    echo -e "  Policy tier:     ${GREEN}${WIZARD_POLICY_TIER}${NC}"
    echo -e "  Code graph:      ${GREEN}${WIZARD_CODE_GRAPH}${NC}"
    echo -e "  Provenance:      ${GREEN}${WIZARD_PROVENANCE}${NC}"
    echo -e "  Guard level:     ${GREEN}${WIZARD_GUARD_LEVEL}${NC}"
    echo ""
}

# ─── Main ────────────────────────────────────────────────────────────────────

main() {
    local from_config=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --from-config)
                from_config="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done

    echo ""
    echo -e "${BOLD}${CYAN}"
    echo "  ███████╗███╗   ██╗ ██████╗ ██████╗  █████╗ ███╗   ███╗"
    echo "  ██╔════╝████╗  ██║██╔════╝ ██╔══██╗██╔══██╗████╗ ████║"
    echo "  █████╗  ██╔██╗ ██║██║  ███╗██████╔╝███████║██╔████╔██║"
    echo "  ██╔══╝  ██║╚██╗██║██║   ██║██╔══██╗██╔══██║██║╚██╔╝██║"
    echo "  ███████╗██║ ╚████║╚██████╔╝██║  ██║██║  ██║██║ ╚═╝ ██║"
    echo "  ╚══════╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝"
    echo -e "${NC}"
    echo -e "  ${DIM}Shared Intelligence Graph for AI Agents
  by Easy Labs — https://itseasy.co${NC}"
    echo -e "  ${DIM}Installer v${PLUGIN_VERSION}${NC}"
    echo ""

    detect_environment
    log_info "Detected OS: $DETECTED_OS"

    if [ -n "$from_config" ]; then
        # Non-interactive mode: load config from JSON file
        load_config_from_json "$from_config"
    else
        # Interactive mode: run the wizard prompts
        run_wizard
    fi

    echo ""
    INSTALL_STARTED=true
    log_info "Starting installation..."

    check_prerequisites
    setup_plugin_directory
    create_data_directories
    generate_env_config
    write_engram_config
    update_host_pointers
    init_obsidian_vault
    init_stack_and_integrations
    write_tools_md
    setup_platforms
    run_validation
    print_summary

    log_success "Done! Run 'openclaw gateway restart' to activate the plugin."
    exit 0
}

main "$@"
