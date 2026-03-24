#!/bin/bash
set -euo pipefail

# OpenClaw LACP Fusion Plugin Installer
# Version: 2.2.0
# Interactive CLI wizard for configuring and installing the plugin
# Installs to ~/.openclaw/extensions/openclaw-lacp-fusion/

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
            echo "     rm -rf ~/.openclaw/extensions/openclaw-lacp-fusion"
            echo ""
        else
            echo -e "\033[1;33mInstallation cancelled.\033[0m"
            echo ""
        fi
    fi
}
trap _install_cleanup EXIT

PLUGIN_NAME="openclaw-lacp-fusion"
PLUGIN_VERSION="2.2.0"
OPENCLAW_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}"
PLUGIN_PATH="$OPENCLAW_HOME/extensions/$PLUGIN_NAME"
GATEWAY_CONFIG="$OPENCLAW_HOME/openclaw.json"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

TOTAL_STEPS=8

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
    if command -v obsidian-cli &>/dev/null; then
        local obs_ver
        obs_ver=$(obsidian-cli --version 2>/dev/null || echo "unknown")
        log_success "Obsidian CLI found"
        return 0
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

        if command -v obsidian-cli &>/dev/null; then
            log_success "Verified: Obsidian CLI ready"
            return 0
        else
            log_error "obsidian-cli command not found after install"
            return 1
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

    local env_file="$PLUGIN_PATH/config/.openclaw-lacp.env"

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
# $PLUGIN_PATH/config/.openclaw-lacp.env.template
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

# ─── Step 5: Update gateway config ──────────────────────────────────────────

update_gateway_config() {
    log_step 5 "Updating gateway config"

    if [ "$HAS_JQ" != "true" ]; then
        log_warning "Skipping gateway config update (jq not installed)"
        log_info "  Add manually to $GATEWAY_CONFIG:"
        echo '  "plugins.allow": add "openclaw-lacp-fusion"'
        echo '  "plugins.entries.openclaw-lacp-fusion": { "enabled": true, "config": { ... } }'
        return
    fi

    # Backup gateway config
    cp "$GATEWAY_CONFIG" "$GATEWAY_CONFIG.bak.$(date +%s)"
    log_info "Gateway config backed up"

    # Check if plugin already registered
    if jq -e '.plugins.entries["openclaw-lacp-fusion"]' "$GATEWAY_CONFIG" &>/dev/null; then
        log_warning "Plugin already registered in gateway config"
        return
    fi

    # Resolve context engine for JSON (null for file-based)
    local ce_json="null"
    if [ "$WIZARD_CONTEXT_ENGINE_RESOLVED" = "lossless-claw" ]; then
        ce_json='"lossless-claw"'
    fi

    # Add to plugins.allow if not present
    local tmp
    tmp=$(mktemp)

    jq --arg name "$PLUGIN_NAME" '
      .plugins.allow = (
        if (.plugins.allow | index($name)) then .plugins.allow
        else .plugins.allow + [$name]
        end
      )
    ' "$GATEWAY_CONFIG" > "$tmp" && mv "$tmp" "$GATEWAY_CONFIG"
    log_success "Added to plugins.allow"

    # Compute mutations flag
    local mutations_enabled="true"
    if [ "$WIZARD_MODE" = "connected" ]; then
        mutations_enabled="false"
    fi

    # Add plugin entry with wizard values
    tmp=$(mktemp)
    jq --arg vault "$DETECTED_VAULT" \
       --arg kr "$OPENCLAW_HOME/data/knowledge" \
       --arg profile "$WIZARD_PROFILE" \
       --arg tier "$WIZARD_POLICY_TIER" \
       --argjson cg "$WIZARD_CODE_GRAPH" \
       --argjson prov "$WIZARD_PROVENANCE" \
       --argjson lf "$WIZARD_LOCAL_FIRST" \
       --argjson ce "$ce_json" \
       --arg mode "$WIZARD_MODE" \
       --arg mutations "$mutations_enabled" \
       --arg curatorUrl "$WIZARD_CURATOR_URL" '
      .plugins.entries["openclaw-lacp-fusion"] = {
        "enabled": true,
        "config": {
          "profile": $profile,
          "obsidianVault": $vault,
          "knowledgeRoot": $kr,
          "localFirst": $lf,
          "provenanceEnabled": $prov,
          "codeGraphEnabled": $cg,
          "policyTier": $tier,
          "contextEngine": $ce,
          "mode": $mode,
          "mutationsEnabled": $mutations,
          "curatorUrl": (if $curatorUrl == "" then null else $curatorUrl end)
        }
      }
    ' "$GATEWAY_CONFIG" > "$tmp" && mv "$tmp" "$GATEWAY_CONFIG"
    log_success "Plugin entry added to gateway config"

    # Add install record
    tmp=$(mktemp)
    jq --arg ver "$PLUGIN_VERSION" --arg path "$PLUGIN_PATH" --arg now "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" '
      .plugins.installs["openclaw-lacp-fusion"] = {
        "source": "path",
        "spec": "openclaw-lacp-fusion",
        "installPath": $path,
        "version": $ver,
        "resolvedVersion": $ver,
        "installedAt": $now
      }
    ' "$GATEWAY_CONFIG" > "$tmp" && mv "$tmp" "$GATEWAY_CONFIG"
    log_success "Install record added to gateway config"
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

# ─── Step 7: Run validation ─────────────────────────────────────────────────

run_validation() {
    log_step 7 "Validating installation"

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
        if jq -e '.plugins.entries["openclaw-lacp-fusion"].enabled' "$GATEWAY_CONFIG" &>/dev/null; then
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
    log_step 8 "Installation complete"

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
    echo "  Config:  $PLUGIN_PATH/config/.openclaw-lacp.env"
    echo "  Gateway: $GATEWAY_CONFIG"
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

# ─── Main ────────────────────────────────────────────────────────────────────

main() {
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

    # Run interactive wizard
    run_wizard

    echo ""
    INSTALL_STARTED=true
    log_info "Starting installation..."

    check_prerequisites
    setup_plugin_directory
    create_data_directories
    generate_env_config
    update_gateway_config
    init_obsidian_vault
    run_validation
    print_summary

    log_success "Done! Run 'openclaw gateway restart' to activate the plugin."
    exit 0
}

main "$@"
