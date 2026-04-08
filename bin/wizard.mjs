#!/usr/bin/env node

// Engram Interactive Configuration Wizard
// Platform-first flow: choose target platforms, then configure accordingly.
// Outputs config to /tmp/engram-wizard-config.json for INSTALL.sh to consume.

import {
  intro,
  outro,
  select,
  confirm,
  spinner,
  multiselect,
  text,
  note,
  log,
  isCancel,
  cancel,
} from '@clack/prompts';
import { styleText } from 'node:util';
import { execSync, exec } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, writeFileSync, mkdirSync, statSync } from 'node:fs';
import { join, resolve, basename, dirname } from 'node:path';
import { homedir, platform } from 'node:os';
import { fileURLToPath } from 'node:url';

// ── Constants ───────────────────────────────────────────────────────────────

const HOME = homedir();
const OPENCLAW_HOME = process.env.OPENCLAW_HOME || join(HOME, '.openclaw');
const ENGRAM_HOME = join(HOME, '.engram');
const CONFIG_OUTPUT = '/tmp/engram-wizard-config.json';

// Where this script lives — used to find sibling files (adapters, mcp, etc.)
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const REPO_ROOT = resolve(__dirname, '..');
const PLUGIN_ROOT = existsSync(join(REPO_ROOT, 'plugin')) ? join(REPO_ROOT, 'plugin') : REPO_ROOT;
const ENGRAM_CONFIG_PATH = join(ENGRAM_HOME, 'config.json');

function writeEngramConfig(payload) {
  mkdirSync(ENGRAM_HOME, { recursive: true });
  const merged = {
    schemaVersion: 1,
    profile: payload.profile ?? 'autonomous',
    vaultPath: payload.vaultPath,
    knowledgeRoot: payload.knowledgeRoot ?? join(ENGRAM_HOME, 'knowledge'),
    automationRoot: payload.automationRoot ?? join(ENGRAM_HOME, 'automation'),
    mode: payload.mode ?? 'standalone',
    mutationsEnabled: payload.mutationsEnabled ?? true,
    agentRole: payload.agentRole ?? 'developer',
    curator: {
      url: payload.curatorUrl ?? null,
      token: payload.curatorToken ?? null,
    },
    features: {
      localFirst: payload.localFirst ?? true,
      provenanceEnabled: payload.provenanceEnabled ?? true,
      codeGraphEnabled: payload.codeGraphEnabled ?? true,
      contextEngine: payload.contextEngine ?? 'lossless-claw',
    },
    policy: {
      tier: payload.policyTier ?? 'review',
      approvalCacheTtlMinutes: 60,
    },
    lcm: {
      queryBatchSize: 32,
      promotionThreshold: 5,
      autoDiscoveryInterval: 'daily',
    },
    qmd: {
      collections: payload.qmdCollections ?? [],
    },
    hosts: {
      openclaw: payload.openclawHome ?? OPENCLAW_HOME,
      claudeCode: process.env.CLAUDE_HOME ?? join(HOME, '.claude'),
      codex: process.env.CODEX_HOME ?? join(HOME, '.codex'),
    },
  };
  writeFileSync(ENGRAM_CONFIG_PATH, JSON.stringify(merged, null, 2) + '\n', 'utf-8');
  return ENGRAM_CONFIG_PATH;
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function cyan(str) {
  return styleText('cyan', str);
}

function bold(str) {
  return styleText('bold', str);
}

function dim(str) {
  return styleText('dim', str);
}

function green(str) {
  return styleText('green', str);
}

function yellow(str) {
  return styleText('yellow', str);
}

function red(str) {
  return styleText('red', str);
}

function commandExists(cmd) {
  try {
    execSync(`command -v ${cmd}`, { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

function getCommandOutput(cmd) {
  try {
    return execSync(cmd, { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'ignore'] }).trim();
  } catch {
    return null;
  }
}

function runCommand(cmd) {
  return new Promise((resolve, reject) => {
    exec(cmd, { encoding: 'utf-8' }, (error, stdout, stderr) => {
      if (error) reject(error);
      else resolve(stdout);
    });
  });
}

function runCommandLive(cmd) {
  return new Promise((resolve, reject) => {
    const child = exec(cmd, { encoding: 'utf-8' });
    child.stdout?.on('data', (data) => process.stdout.write(dim(data)));
    child.stderr?.on('data', (data) => process.stderr.write(dim(data)));
    child.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`Command exited with code ${code}`));
    });
  });
}

function handleCancel(value) {
  if (isCancel(value)) {
    cancel('Installation cancelled.');
    process.exit(0);
  }
  return value;
}

// ── Vault Scanner ───────────────────────────────────────────────────────────

function scanForVaults() {
  const searchRoots = [];
  const os = platform();

  if (os === 'darwin') {
    searchRoots.push(join(HOME, 'Documents'), join(HOME, 'Desktop'));
    // Check mounted volumes
    try {
      const volumes = readdirSync('/Volumes');
      for (const vol of volumes) {
        const volPath = join('/Volumes', vol);
        try {
          if (statSync(volPath).isDirectory()) {
            searchRoots.push(volPath);
          }
        } catch { /* skip inaccessible volumes */ }
      }
    } catch { /* /Volumes not readable */ }
  } else {
    searchRoots.push(join(HOME, 'Documents'), join(HOME, 'Desktop'));
  }

  const vaults = new Set();

  for (const root of searchRoots) {
    if (!existsSync(root)) continue;
    try {
      const result = getCommandOutput(
        `find "${root}" -maxdepth 3 -name ".obsidian" -type d 2>/dev/null`
      );
      if (result) {
        for (const line of result.split('\n')) {
          const trimmed = line.trim();
          if (trimmed) {
            // Strip trailing /.obsidian to get vault root
            vaults.add(trimmed.replace(/\/.obsidian$/, ''));
          }
        }
      }
    } catch { /* scan failed for this root */ }
  }

  return [...vaults];
}

// ── Dependency Detection ────────────────────────────────────────────────────

function detectDependencies() {
  const deps = {};

  // Core tools
  deps.python3 = commandExists('python3');
  deps.pip = commandExists('pip3') || commandExists('pip');
  deps.pipx = commandExists('pipx');
  deps.brew = commandExists('brew');
  deps.apt = commandExists('apt-get');
  deps.node = commandExists('node');

  // PDF extraction
  deps.pdftotext = commandExists('pdftotext');

  // Media ingestion
  deps.ffmpeg = commandExists('ffmpeg');
  deps.insanelyFastWhisper = commandExists('insanely-fast-whisper');

  // Reactive watcher
  deps.watchdog = getCommandOutput('python3 -c "import watchdog; print(1)"') === '1';

  // QMD
  deps.qmd = commandExists('qmd');
  if (deps.qmd) {
    deps.qmdPath = getCommandOutput('which qmd');
  }

  // Obsidian CLI
  deps.obsidianCli = false;
  if (commandExists('obsidian')) {
    const help = getCommandOutput('obsidian --help 2>&1 | head -1');
    if (help && help.includes('Usage:')) {
      deps.obsidianCli = true;
      deps.obsidianCliPath = getCommandOutput('which obsidian');
    }
  }

  // obsidian-headless (ob)
  deps.obsidianHeadless = commandExists('ob');
  if (deps.obsidianHeadless) {
    deps.obVersion = getCommandOutput('ob --version') || 'unknown';
  }

  // OpenClaw
  deps.openclaw = commandExists('openclaw') && existsSync(join(OPENCLAW_HOME, 'openclaw.json'));

  // lossless-claw
  deps.losslessClaw = existsSync(join(OPENCLAW_HOME, 'extensions', 'lossless-claw'));
  deps.lcmDb = existsSync(join(OPENCLAW_HOME, 'lcm.db'));

  // GitNexus
  deps.gitnexus = commandExists('gitnexus');
  if (deps.gitnexus) {
    deps.gitnexusPath = getCommandOutput('which gitnexus');
  }

  return deps;
}

// ── Guard Rules Loader ──────────────────────────────────────────────────────

function loadGuardRules() {
  const paths = [
    join(PLUGIN_ROOT, 'config', 'guard-rules.json'),
    join(process.cwd(), 'plugin', 'config', 'guard-rules.json'),
    join(OPENCLAW_HOME, 'extensions', 'engram', 'config', 'guard-rules.json'),
  ];

  for (const p of paths) {
    if (existsSync(p)) {
      try {
        return JSON.parse(readFileSync(p, 'utf-8'));
      } catch { /* malformed JSON */ }
    }
  }
  return null;
}

// ── Banner ──────────────────────────────────────────────────────────────────

function showBanner() {
  const banner = `
${cyan(bold('  ███████╗███╗   ██╗ ██████╗ ██████╗  █████╗ ███╗   ███╗'))}
${cyan(bold('  ██╔════╝████╗  ██║██╔════╝ ██╔══██╗██╔══██╗████╗ ████║'))}
${cyan(bold('  █████╗  ██╔██╗ ██║██║  ███╗██████╔╝███████║██╔████╔██║'))}
${cyan(bold('  ██╔══╝  ██║╚██╗██║██║   ██║██╔══██╗██╔══██║██║╚██╔╝██║'))}
${cyan(bold('  ███████╗██║ ╚████║╚██████╔╝██║  ██║██║  ██║██║ ╚═╝ ██║'))}
${cyan(bold('  ╚══════╝╚═╝  ╚═══╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝'))}
${dim('                                              w i z a r d')}
`;
  console.log(banner);
}

// ── Claude Code Direct Install ──────────────────────────────────────────────

async function installClaudeCode(vaultPath, safetyProfile, guardLevel) {
  log.step(bold('Installing for Claude Code'));

  // 1. Register MCP server in ~/.claude.json
  const setupMcp = join(PLUGIN_ROOT, 'mcp', 'setup-mcp.sh');
  if (existsSync(setupMcp)) {
    try {
      const output = getCommandOutput(`LACP_OBSIDIAN_VAULT="${vaultPath}" bash "${setupMcp}" --global 2>&1`);
      if (output) log.info(dim(output));
      log.success('MCP server registered in ~/.claude.json');
    } catch (err) {
      log.warn('MCP server registration failed — run manually:');
      log.info(dim(`  bash "${setupMcp}" --global`));
    }
  } else {
    log.warn(`MCP setup script not found at ${setupMcp}`);
  }

  // 2. Register hooks in ~/.claude/settings.json
  const setupHooks = join(PLUGIN_ROOT, 'hooks', 'adapters', 'setup-claude-code.sh');
  if (existsSync(setupHooks)) {
    try {
      const output = getCommandOutput(`ENGRAM_DIR="${PLUGIN_ROOT}" bash "${setupHooks}" --global 2>&1`);
      if (output) log.info(dim(output));
      log.success('Hooks registered in ~/.claude/settings.json');
    } catch (err) {
      log.warn('Hooks registration failed — run manually:');
      log.info(dim(`  bash "${setupHooks}" --global`));
    }
  } else {
    log.warn(`Hooks setup script not found at ${setupHooks}`);
  }

  log.success('Claude Code configuration complete');
  log.info(dim('MCP server starts automatically when Claude Code launches.'));
  log.info(dim('Hooks fire on every session start, tool call, write, and stop.'));
}

// ── Codex Direct Install ────────────────────────────────────────────────────

async function installCodex(vaultPath) {
  log.step(bold('Installing for Codex'));

  // 1. Print MCP config for Codex
  const setupMcp = join(PLUGIN_ROOT, 'mcp', 'setup-mcp.sh');
  if (existsSync(setupMcp)) {
    const mcpJson = getCommandOutput(`LACP_OBSIDIAN_VAULT="${vaultPath}" bash "${setupMcp}" --print 2>&1`);
    if (mcpJson) {
      log.success('Codex MCP config generated');
      log.info('Save this to .codex/mcp.json in your project:');
      log.info(dim(mcpJson.split('\n').filter(l => !l.startsWith('#')).join('\n')));
    }
  }

  log.success('Codex configuration complete');
}

// ── Main Wizard ─────────────────────────────────────────────────────────────

async function main() {
  showBanner();

  intro(bold('Engram Configuration Wizard'));

  log.info(dim('Arrow keys to navigate, Enter to select. Press Ctrl+C to cancel.'));

  // ── Step 1: Platform Selection ──────────────────────────────────────────

  log.step(bold('Platform'));
  log.message(dim('Which AI coding platforms are you using? This determines what gets configured.'));

  // Auto-detect available platforms
  const deps = detectDependencies();
  const platformOptions = [];

  if (deps.openclaw) {
    platformOptions.push({ value: 'openclaw', label: 'OpenClaw', hint: 'detected — native plugin (hooks + tools + agents)' });
  } else {
    platformOptions.push({ value: 'openclaw', label: 'OpenClaw', hint: 'not detected — native plugin integration' });
  }
  platformOptions.push({ value: 'claude-code', label: 'Claude Code', hint: 'hooks + MCP server (auto-starts with Claude)' });
  platformOptions.push({ value: 'codex', label: 'Codex (OpenAI)', hint: 'MCP server for tools' });

  const selectedPlatforms = handleCancel(await multiselect({
    message: 'Select your platforms',
    options: platformOptions,
    required: true,
  }));

  if (!selectedPlatforms || selectedPlatforms.length === 0) {
    cancel('At least one platform is required.');
    process.exit(0);
  }

  log.success(`Platforms: ${green(selectedPlatforms.join(', '))}`);

  const hasOpenClaw = selectedPlatforms.includes('openclaw');
  const hasClaudeCode = selectedPlatforms.includes('claude-code');
  const hasCodex = selectedPlatforms.includes('codex');

  // ── Step 2: Vault Selection ─────────────────────────────────────────────

  log.step(bold('Obsidian Vault'));
  log.message(dim('Your Obsidian vault stores the knowledge graph. All platforms share it.'));

  const s = spinner();
  s.start('Scanning for Obsidian vaults...');
  const detectedVaults = scanForVaults();
  s.stop(
    detectedVaults.length > 0
      ? `Found ${detectedVaults.length} Obsidian vault${detectedVaults.length === 1 ? '' : 's'}`
      : 'No Obsidian vaults detected'
  );

  const vaultOptions = [];
  for (const v of detectedVaults) {
    vaultOptions.push({ value: v, label: v, hint: 'detected' });
  }
  vaultOptions.push({ value: '__custom__', label: 'Enter a custom path' });
  vaultOptions.push({ value: '__skip__', label: 'Skip -- I don\'t use Obsidian', hint: 'uses default directory' });

  let vaultChoice = handleCancel(await select({
    message: 'Select your vault',
    options: vaultOptions,
  }));

  let vaultPath;
  if (vaultChoice === '__custom__') {
    const custom = handleCancel(await text({
      message: 'Vault path',
      placeholder: join(HOME, 'my-vault'),
      validate: (val) => {
        if (!val) return 'Path is required';
      },
    }));
    vaultPath = resolve(custom.replace(/^~/, HOME));
  } else if (vaultChoice === '__skip__') {
    const defaultDir = hasOpenClaw ? join(OPENCLAW_HOME, 'data', 'knowledge') : join(ENGRAM_HOME, 'knowledge');
    vaultPath = defaultDir;
    log.info(`No vault selected — using default: ${dim(defaultDir)}`);
  } else {
    vaultPath = vaultChoice;
  }

  log.success(`Vault: ${green(vaultPath)}`);

  // ── Vault migration check (only if OpenClaw or vault exists) ──────────

  const hasObsidian = existsSync(join(vaultPath, '.obsidian'));
  const pluginSchemaPath = join(OPENCLAW_HOME, 'extensions', 'engram', 'config', 'vault-schema.json');
  const hasEngramSchema = existsSync(pluginSchemaPath);

  let vaultNeedsMigration = false;
  if (hasObsidian && hasOpenClaw) {
    if (!hasEngramSchema) {
      vaultNeedsMigration = true;
    } else {
      try {
        const schema = JSON.parse(readFileSync(pluginSchemaPath, 'utf-8'));
        const paths = schema.paths || {};
        const expectedFolders = Object.values(paths).filter(p => !p.includes('.'));
        const topLevel = expectedFolders.filter(p => !p.includes('/'));
        const missingCount = topLevel.filter(f => !existsSync(join(vaultPath, f))).length;
        if (missingCount > topLevel.length / 2) {
          vaultNeedsMigration = true;
        }
      } catch { /* schema parse failed, skip */ }
    }
  }

  if (hasObsidian && vaultNeedsMigration) {
    log.warn('This vault exists but is not set up for Engram.');
    log.info(dim('Migration will back up your vault, create the Engram folder structure,'));
    log.info(dim('classify your existing notes by content, and move them into the right folders.'));

    const wantMigrate = handleCancel(await select({
      message: 'Migrate this vault to Engram?',
      options: [
        { value: 'dry-run', label: 'Preview migration (dry run)', hint: 'see what would change, no modifications' },
        { value: 'migrate', label: 'Migrate now (with backup)', hint: 'backs up vault first, then restructures' },
        { value: 'skip', label: 'Skip migration', hint: 'use the vault as-is, configure manually later' },
      ],
    }));

    if (wantMigrate === 'dry-run' || wantMigrate === 'migrate') {
      const migrateScript = join(OPENCLAW_HOME, 'extensions', 'engram', 'bin', 'engram-vault-migrate');
      const flags = wantMigrate === 'dry-run' ? '--dry-run' : '';

      log.info(`Running vault migration${wantMigrate === 'dry-run' ? ' (preview)' : ''}...`);
      try {
        await runCommandLive(`python3 "${migrateScript}" "${vaultPath}" ${flags}`);
        if (wantMigrate === 'dry-run') {
          const proceed = handleCancel(await confirm({
            message: 'Apply these changes?',
            initialValue: true,
          }));
          if (proceed) {
            log.info('Applying migration...');
            await runCommandLive(`python3 "${migrateScript}" "${vaultPath}"`);
            log.success('Vault migrated');
          } else {
            log.info('Migration skipped — you can run it later: engram vault migrate');
          }
        } else {
          log.success('Vault migrated');
        }
      } catch (err) {
        log.warn(`Migration had issues: ${err.message}`);
        log.info('You can retry later: engram vault migrate');
      }
    } else {
      log.info('Skipped — run "engram vault migrate" later to restructure');
    }
  } else if (hasObsidian && !vaultNeedsMigration) {
    log.success('Vault already configured for Engram');
  }

  // ── Step 3: Safety Profile ──────────────────────────────────────────────

  log.step(bold('Safety Profile'));
  log.message(dim('Controls which execution hooks are active and how they behave.'));

  const safetyProfile = handleCancel(await select({
    message: 'Profile',
    options: [
      { value: 'autonomous', label: 'autonomous', hint: 'all hooks, warn-only (agents keep working, escalate when needed)' },
      { value: 'balanced', label: 'balanced', hint: 'session context + quality gate (recommended for interactive use)' },
      { value: 'context-only', label: 'context-only', hint: 'just git context injection, no safety gates' },
      { value: 'guard-rail', label: 'guard-rail', hint: 'safety gates only, no context injection' },
      { value: 'minimal-stop', label: 'minimal-stop', hint: 'quality gate only (lightweight)' },
      { value: 'hardened-exec', label: 'hardened-exec', hint: 'all 4 hooks, blocks dangerous ops' },
      { value: 'full-audit', label: 'full-audit', hint: 'all hooks, strict mode, verbose logging' },
    ],
  }));

  log.success(`Safety profile: ${green(safetyProfile)}`);

  // ── Step 4: Guard Level ─────────────────────────────────────────────────

  let guardLevel = 'block';

  const wantGuardConfig = handleCancel(await confirm({
    message: 'Configure guard rules? (default: block dangerous commands)',
    initialValue: false,
  }));

  if (wantGuardConfig) {
    log.step(bold('Guard Configuration'));
    log.message(dim('Controls how the pretool guard handles dangerous commands.'));

    guardLevel = handleCancel(await select({
      message: 'Default guard block level',
      options: [
        { value: 'block', label: 'block', hint: 'block dangerous commands (ask user first)' },
        { value: 'warn', label: 'warn', hint: 'warn but allow execution (log to guard-blocks.jsonl)' },
        { value: 'log', label: 'log', hint: 'silently log matches (no interruption)' },
      ],
    }));
    log.success(`Guard block level: ${green(guardLevel)}`);
  }

  // ── OpenClaw-specific steps ─────────────────────────────────────────────

  let contextEngine = 'file-based';
  let contextEngineResolved = 'file-based';
  let operatingMode = 'standalone';
  let curatorUrl = '';
  let curatorToken = '';
  let policyTier = 'review';
  let codeGraph = false;
  let provenance = true;
  let localFirst = true;
  let disabledRules = [];
  let ruleOverrides = {};
  let selectedAgents = [];
  let agentWorkspaces = {};

  if (hasOpenClaw) {
    // ── Context Engine ────────────────────────────────────────────────

    log.step(bold('Context Engine'));
    log.message(dim('Controls how Engram stores and retrieves context facts.'));

    // Install required dependencies
    const required = [];
    if (!deps.qmd) required.push({ id: 'qmd', label: 'QMD', install: 'npm install -g @nicepkg/qmd', hint: 'semantic search and memory backend (required)' });
    if (!deps.pdftotext) required.push({ id: 'poppler', label: 'poppler (pdftotext)', install: deps.brew ? 'brew install poppler' : 'sudo apt-get install -y poppler-utils', hint: 'PDF text extraction (required)' });
    if (!deps.watchdog) required.push({ id: 'watchdog', label: 'watchdog', install: 'pip3 install watchdog', hint: 'real-time filesystem events for curator reactive loop (required)' });

    if (required.length > 0) {
      log.info(`Installing ${required.length} required dependenc${required.length === 1 ? 'y' : 'ies'}...`);
      for (const dep of required) {
        log.info(`${bold(dep.label)}: ${dim(dep.install)}`);
        try {
          await runCommandLive(dep.install);
          log.success(`${dep.label} installed`);
        } catch (err) {
          log.error(`${dep.label} failed: ${err.message}`);
          log.warn(`Install manually: ${dep.install}`);
        }
      }
      Object.assign(deps, detectDependencies());
    } else {
      log.success('Required dependencies found (QMD, poppler)');
    }

    // pipx for optional deps
    if (!deps.pipx) {
      try {
        const pipxCmd = deps.brew ? 'brew install pipx && pipx ensurepath' : 'pip3 install pipx && pipx ensurepath';
        await runCommandLive(pipxCmd);
        deps.pipx = true;
      } catch { /* non-critical */ }
    }

    // Optional deps
    const optional = [];
    if (!deps.ffmpeg) optional.push({ id: 'ffmpeg', label: 'ffmpeg', install: deps.brew ? 'brew install ffmpeg' : 'sudo apt-get install -y ffmpeg', hint: 'video/audio processing' });
    if (!deps.insanelyFastWhisper) optional.push({ id: 'whisper', label: 'insanely-fast-whisper', install: 'pipx install insanely-fast-whisper==0.0.15 --force --pip-args="--ignore-requires-python"', hint: 'video/audio transcription (via pipx)' });

    if (optional.length > 0) {
      const toInstall = handleCancel(await multiselect({
        message: 'Install optional dependencies?',
        options: optional.map(m => ({
          value: m.id,
          label: m.label,
          hint: `${m.hint} — ${dim(m.install)}`,
        })),
        required: false,
      })) || [];

      for (const depId of toInstall) {
        const dep = optional.find(m => m.id === depId);
        try {
          await runCommandLive(dep.install);
          log.success(`${dep.label} installed`);
        } catch (err) {
          log.warn(`${dep.label} failed: ${err.message}`);
        }
      }
      Object.assign(deps, detectDependencies());
    }

    // Context engine selection
    const contextStatus = [];
    if (deps.losslessClaw) contextStatus.push('lossless-claw extension detected');
    if (deps.lcmDb) contextStatus.push('LCM database found');
    if (contextStatus.length > 0) {
      log.info(contextStatus.map(s => green('+') + ' ' + s).join('\n'));
    }

    let contextEngineOptions;
    if (deps.losslessClaw) {
      contextEngineOptions = [
        { value: 'lossless-claw', label: 'lossless-claw', hint: 'native LCM database (recommended, already installed)' },
        { value: 'file-based', label: 'file-based', hint: 'JSON files on disk (simpler, no database)' },
      ];
    } else {
      contextEngineOptions = [
        { value: 'file-based', label: 'file-based', hint: 'JSON files on disk (no extra dependencies)' },
        { value: 'lossless-claw', label: 'lossless-claw', hint: 'install native LCM database for better performance' },
      ];
    }

    contextEngine = handleCancel(await select({
      message: 'Context engine',
      options: contextEngineOptions,
    }));
    contextEngineResolved = contextEngine;
    log.success(`Context engine: ${green(contextEngine)}`);

    // ── Operating Mode ────────────────────────────────────────────────

    log.step(bold('Operating Mode'));
    log.message(dim('Controls how this node participates in the knowledge network.'));

    operatingMode = handleCancel(await select({
      message: 'Mode',
      options: [
        { value: 'standalone', label: 'standalone', hint: 'local vault, all brain commands active (default)' },
        { value: 'connected', label: 'connected', hint: 'sync to shared vault, mutations delegated to curator' },
        { value: 'curator', label: 'curator', hint: 'server node: connectors, mycelium, git backup, invites' },
      ],
    }));
    log.success(`Operating mode: ${green(operatingMode)}`);

    if (operatingMode === 'connected') {
      curatorUrl = handleCancel(await text({
        message: 'Curator URL',
        placeholder: 'https://curator.example.com',
        validate: (val) => {
          if (!val) return 'Curator URL is required';
          try { new URL(val); } catch { return 'Must be a valid URL'; }
        },
      }));
      curatorToken = handleCancel(await text({
        message: 'Invite token',
        placeholder: 'paste your invite token here',
      }));
      if (!curatorToken) {
        log.warn('No invite token provided. Set it later via: engram connect join');
      }
    }

    if (operatingMode === 'connected' || operatingMode === 'curator') {
      if (!deps.obsidianHeadless) {
        const installOb = handleCancel(await confirm({
          message: 'obsidian-headless (ob) is required for this mode. Install it now?',
          initialValue: true,
        }));
        if (installOb) {
          try {
            await runCommand('npm install -g obsidian-headless');
            deps.obsidianHeadless = true;
            log.success('obsidian-headless installed');
          } catch {
            log.warn('Falling back to standalone mode.');
            operatingMode = 'standalone';
          }
        } else {
          operatingMode = 'standalone';
        }
      }
    }

    // ── Advanced Config ───────────────────────────────────────────────

    const wantAdvanced = handleCancel(await confirm({
      message: 'Configure advanced options? (policy tier, code intelligence, provenance)',
      initialValue: false,
    }));

    if (wantAdvanced) {
      log.step(bold('Advanced Configuration'));

      policyTier = handleCancel(await select({
        message: 'Default policy tier',
        options: [
          { value: 'review', label: 'review', hint: 'require review before execution' },
          { value: 'safe', label: 'safe', hint: 'auto-approve safe operations' },
          { value: 'critical', label: 'critical', hint: 'all operations require approval' },
        ],
      }));
      log.success(`Policy tier: ${green(policyTier)}`);

      const wantCodeIntel = handleCancel(await confirm({
        message: 'Enable code intelligence (AST analysis)?',
        initialValue: false,
      }));
      if (wantCodeIntel) {
        if (deps.gitnexus) {
          codeGraph = true;
          log.success(`Code intelligence enabled with GitNexus ${dim(`(${deps.gitnexusPath})`)}`);
        } else {
          const installGn = handleCancel(await confirm({
            message: 'GitNexus not found. Install it?',
            initialValue: true,
          }));
          if (installGn) {
            try {
              await runCommand('npm install -g gitnexus');
              codeGraph = true;
              log.success('GitNexus installed');
            } catch {
              log.warn('Code intelligence disabled. Install later: npm install -g gitnexus');
            }
          }
        }
      }

      log.info(dim('Provenance creates a tamper-proof audit trail of every agent session.'));
      provenance = handleCancel(await confirm({
        message: 'Enable provenance tracking?',
        initialValue: true,
      }));
      log.success(`Provenance: ${green(provenance ? 'enabled' : 'disabled')}`);

      localFirst = handleCancel(await confirm({
        message: 'Local-first mode (no external sync)?',
        initialValue: true,
      }));
      log.success(`Local-first: ${green(localFirst ? 'enabled' : 'disabled')}`);

      // Guard rule configuration
      const wantRuleConfig = handleCancel(await confirm({
        message: 'Configure individual guard rules?',
        initialValue: false,
      }));

      if (wantRuleConfig) {
        const guardData = loadGuardRules();
        if (guardData && guardData.rules && guardData.rules.length > 0) {
          const ruleOptions = guardData.rules.map((rule) => ({
            value: rule.id,
            label: rule.label || rule.id,
            hint: `[${rule.category}] ${rule.block_level}`,
          }));

          disabledRules = handleCancel(await multiselect({
            message: 'Select rules to DISABLE (all enabled by default)',
            options: ruleOptions,
            required: false,
          })) || [];

          if (disabledRules.length > 0) {
            log.info(`${disabledRules.length} rule(s) will be disabled: ${dim(disabledRules.join(', '))}`);
          }
        }
      }
    }

    // ── Agent Selection (OpenClaw only) ───────────────────────────────

    const gatewayPath = join(OPENCLAW_HOME, 'openclaw.json');
    let allAgents = [];

    if (existsSync(gatewayPath)) {
      try {
        const gatewayData = JSON.parse(readFileSync(gatewayPath, 'utf-8'));
        const agentList = gatewayData?.agents?.list || [];
        for (const agent of agentList) {
          if (agent.id && agent.name) {
            allAgents.push({
              id: agent.id,
              name: agent.name,
              workspace: agent.workspace || null,
              emoji: agent.identity?.emoji || '',
            });
          }
        }
      } catch { /* gateway parse failed */ }
    }

    if (allAgents.length > 0) {
      log.info(`Found ${bold(String(allAgents.length))} agent${allAgents.length === 1 ? '' : 's'} in OpenClaw config`);

      const agentChoices = allAgents.map((a) => ({
        value: a.id,
        label: `${a.emoji} ${a.name} (${a.id})`,
        hint: a.workspace ? dim(a.workspace) : dim('no workspace'),
      }));

      selectedAgents = handleCancel(await multiselect({
        message: 'Which agents should use Engram memory tools?',
        options: agentChoices,
        required: false,
      })) || [];

      if (selectedAgents.length > 0) {
        for (const agentId of selectedAgents) {
          const agent = allAgents.find(a => a.id === agentId);
          if (agent?.workspace) {
            agentWorkspaces[agentId] = agent.workspace;
          }
        }
        log.success(`${selectedAgents.length} agent(s) selected: ${selectedAgents.join(', ')}`);
      }
    }

    // lossless-claw resolution
    if (contextEngine === 'lossless-claw' && !deps.losslessClaw) {
      const installLc = handleCancel(await confirm({
        message: 'lossless-claw is not installed. Install it now?',
        initialValue: true,
      }));
      if (installLc) {
        try {
          await runCommand('openclaw plugins install @martian-engineering/lossless-claw');
          deps.losslessClaw = true;
          log.success('lossless-claw installed');
        } catch {
          log.warn('Falling back to file-based context engine.');
          contextEngineResolved = 'file-based';
        }
      } else {
        contextEngineResolved = 'file-based';
      }
    }
  }

  // ── Summary ─────────────────────────────────────────────────────────────

  const summaryLines = [
    `Platforms:         ${green(selectedPlatforms.join(', '))}`,
    `Obsidian vault:    ${green(vaultPath)}`,
    `Safety profile:    ${green(safetyProfile)}`,
    `Guard level:       ${green(guardLevel)}`,
  ];

  if (hasOpenClaw) {
    summaryLines.push(
      `Context engine:    ${green(contextEngineResolved)}`,
      `Operating mode:    ${green(operatingMode)}`,
      `Policy tier:       ${green(policyTier)}`,
      `Code graph:        ${green(String(codeGraph))}`,
      `Provenance:        ${green(String(provenance))}`,
      `Local-first:       ${green(String(localFirst))}`,
    );
    if (operatingMode === 'connected' && curatorUrl) {
      summaryLines.push(`Curator URL:       ${green(curatorUrl)}`);
    }
    if (selectedAgents.length > 0) {
      summaryLines.push(`Agents:            ${green(selectedAgents.join(', '))}`);
    }
  }

  if (disabledRules.length > 0) {
    summaryLines.push(`Disabled rules:    ${yellow(disabledRules.join(', '))}`);
  }

  summaryLines.push('');
  if (hasOpenClaw) {
    summaryLines.push(`Install path:      ${dim(join(OPENCLAW_HOME, 'extensions', 'engram'))}`);
  }
  if (hasClaudeCode) {
    summaryLines.push(`Claude MCP:        ${dim(join(HOME, '.claude.json'))}`);
    summaryLines.push(`Claude hooks:      ${dim(join(HOME, '.claude', 'settings.json'))}`);
  }

  note(summaryLines.join('\n'), 'Installation Summary');

  const confirmed = handleCancel(await confirm({
    message: 'Proceed with installation?',
    initialValue: true,
  }));

  if (!confirmed) {
    cancel('Installation cancelled.');
    process.exit(0);
  }

  // ── Install ─────────────────────────────────────────────────────────────

  // Write config for INSTALL.sh (OpenClaw path)
  const config = {
    version: '1.0.0',
    timestamp: new Date().toISOString(),
    vault_path: vaultPath,
    context_engine: contextEngineResolved,
    profile: safetyProfile,
    mode: operatingMode,
    curator_url: curatorUrl || null,
    curator_token: curatorToken || null,
    policy_tier: policyTier,
    code_graph: codeGraph,
    provenance,
    local_first: localFirst,
    guard_level: guardLevel,
    disabled_rules: disabledRules,
    rule_overrides: ruleOverrides,
    dependencies: {
      qmd: deps.qmd,
      obsidianCli: deps.obsidianCli,
      obsidianHeadless: deps.obsidianHeadless,
      losslessClaw: deps.losslessClaw,
      gitnexus: deps.gitnexus,
    },
    agents: {
      selected: selectedAgents,
      workspaces: agentWorkspaces,
    },
    platforms: selectedPlatforms,
  };

  try {
    writeFileSync(CONFIG_OUTPUT, JSON.stringify(config, null, 2), 'utf-8');
    log.success(`Config written to ${dim(CONFIG_OUTPUT)}`);

    const engramConfigPath = writeEngramConfig({
      profile: safetyProfile,
      vaultPath: vaultPath,
      mode: operatingMode,
      curatorUrl: curatorUrl || null,
      curatorToken: curatorToken || null,
      policyTier: policyTier,
      codeGraphEnabled: codeGraph,
      provenanceEnabled: provenance,
      localFirst: localFirst,
      contextEngine: contextEngineResolved,
    });
    note(green(`Wrote ${engramConfigPath}`));
  } catch (err) {
    log.error(`Failed to write config: ${err.message}`);
    process.exit(1);
  }

  // Direct install for Claude Code and Codex (no INSTALL.sh needed)
  if (hasClaudeCode) {
    await installClaudeCode(vaultPath, safetyProfile, guardLevel);
  }

  if (hasCodex) {
    await installCodex(vaultPath);
  }

  // For OpenClaw, hand off to INSTALL.sh
  if (hasOpenClaw) {
    outro(bold('Configuration complete. Starting OpenClaw installation...'));
    // INSTALL.sh will be invoked by the caller (engram CLI)
  } else {
    // No OpenClaw — we're done
    log.success('Installation complete!');
    log.info('');
    if (hasClaudeCode) {
      log.info('Claude Code: restart Claude Code to activate Engram.');
      log.info(dim('  MCP server registered in ~/.claude.json'));
      log.info(dim('  Hooks registered in ~/.claude/settings.json'));
      log.info(dim('  10 memory tools available: engram_memory_query, engram_promote_fact, etc.'));
      log.info(dim('  4 hooks active: session start, pretool guard, write validate, stop gate'));
    }
    if (hasCodex) {
      log.info('Codex: copy the MCP config to .codex/mcp.json in your project.');
    }
    outro(bold('Done!'));
  }
}

// ── Entry Point ─────────────────────────────────────────────────────────────

main().catch((err) => {
  if (err.message?.includes('User force closed')) {
    cancel('Installation cancelled.');
    process.exit(0);
  }
  console.error(red(`\nFatal error: ${err.message}`));
  if (process.env.DEBUG) {
    console.error(err.stack);
  }
  process.exit(1);
});
