#!/usr/bin/env node

// Engram Interactive Configuration Wizard
// Replaces bash wizard prompts with @clack/prompts for arrow-key navigation.
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
import { existsSync, readdirSync, readFileSync, writeFileSync, statSync } from 'node:fs';
import { join, resolve, basename } from 'node:path';
import { homedir, platform } from 'node:os';

// ── Constants ───────────────────────────────────────────────────────────────

const HOME = homedir();
const OPENCLAW_HOME = process.env.OPENCLAW_HOME || join(HOME, '.openclaw');
const CONFIG_OUTPUT = '/tmp/engram-wizard-config.json';

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
  deps.brew = commandExists('brew');
  deps.apt = commandExists('apt-get');

  // PDF extraction
  deps.pdftotext = commandExists('pdftotext');

  // Media ingestion
  deps.ffmpeg = commandExists('ffmpeg');
  deps.insanelyFastWhisper = commandExists('insanely-fast-whisper');

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

// ── Main Wizard ─────────────────────────────────────────────────────────────

async function main() {
  showBanner();

  intro(bold('Engram Configuration Wizard'));

  log.info(dim('Arrow keys to navigate, Enter to select. Press Ctrl+C to cancel.'));

  // ── Step 1: Vault Selection ─────────────────────────────────────────────

  log.step(bold('Obsidian Vault'));
  log.message(dim('Your Obsidian vault stores knowledge graph data (Layer 2).'));

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
  vaultOptions.push({ value: '__browse__', label: 'Browse for a different folder' });
  vaultOptions.push({ value: '__custom__', label: 'Type a custom path' });
  vaultOptions.push({ value: '__skip__', label: 'Skip -- I don\'t use Obsidian', hint: 'uses default directory' });

  let vaultChoice = handleCancel(await select({
    message: 'Select your vault',
    options: vaultOptions,
  }));

  let vaultPath;
  if (vaultChoice === '__browse__') {
    const browsed = handleCancel(await text({
      message: 'Enter the path to your vault directory',
      placeholder: join(HOME, 'my-vault'),
      validate: (val) => {
        if (!val) return 'Path is required';
        const resolved = resolve(val.replace(/^~/, HOME));
        if (!existsSync(resolved)) return `Directory not found: ${resolved}`;
      },
    }));
    vaultPath = resolve(browsed.replace(/^~/, HOME));
  } else if (vaultChoice === '__custom__') {
    const custom = handleCancel(await text({
      message: 'Vault path',
      placeholder: join(HOME, 'my-vault'),
      validate: (val) => {
        if (!val) return 'Path is required';
      },
    }));
    vaultPath = resolve(custom.replace(/^~/, HOME));
  } else if (vaultChoice === '__skip__') {
    vaultPath = join(OPENCLAW_HOME, 'data', 'knowledge');
    log.info('No vault selected -- using default knowledge directory');
  } else {
    vaultPath = vaultChoice;
  }

  log.success(`Vault: ${green(vaultPath)}`);

  // ── Step 2: Context Engine ──────────────────────────────────────────────

  log.step(bold('Context Engine'));
  log.message(dim('Controls how LACP stores and retrieves context facts.'));

  const deps = detectDependencies();

  // ── Install required dependencies automatically ────────────────────────

  const required = [];
  if (!deps.qmd) required.push({ id: 'qmd', label: 'QMD', install: 'npm install -g @nicepkg/qmd', hint: 'semantic search and memory backend (required)' });
  if (!deps.pdftotext) required.push({ id: 'poppler', label: 'poppler (pdftotext)', install: deps.brew ? 'brew install poppler' : 'sudo apt-get install -y poppler-utils', hint: 'PDF text extraction (required)' });

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

  // ── Offer optional dependencies ──────────────────────────────────────

  const optional = [];
  if (!deps.ffmpeg) optional.push({ id: 'ffmpeg', label: 'ffmpeg', install: deps.brew ? 'brew install ffmpeg' : 'sudo apt-get install -y ffmpeg', hint: 'video/audio processing' });
  if (!deps.insanelyFastWhisper) optional.push({ id: 'whisper', label: 'insanely-fast-whisper', install: 'pip3 install insanely-fast-whisper', hint: 'audio transcription — large download (~2GB, includes PyTorch)' });

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

    if (toInstall.length > 0) {
      for (const depId of toInstall) {
        const dep = optional.find(m => m.id === depId);
        log.info(`${bold(dep.label)}: ${dim(dep.install)}`);
        try {
          await runCommandLive(dep.install);
          log.success(`${dep.label} installed`);
        } catch (err) {
          log.error(`${dep.label} failed: ${err.message}`);
          log.warn(`You can install manually: ${dep.install}`);
        }
      }
      Object.assign(deps, detectDependencies());
    }
  }

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

  const contextEngine = handleCancel(await select({
    message: 'Context engine',
    options: contextEngineOptions,
  }));

  log.success(`Context engine: ${green(contextEngine)}`);

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

  // ── Step 4: Operating Mode ──────────────────────────────────────────────

  log.step(bold('Operating Mode'));
  log.message(dim('Controls how this node participates in the knowledge network.'));

  let operatingMode = handleCancel(await select({
    message: 'Mode',
    options: [
      { value: 'standalone', label: 'standalone', hint: 'local vault, all brain commands active (default)' },
      { value: 'connected', label: 'connected', hint: 'sync to shared vault, mutations delegated to curator' },
      { value: 'curator', label: 'curator', hint: 'server node: connectors, mycelium, git backup, invites' },
    ],
  }));

  log.success(`Operating mode: ${green(operatingMode)}`);

  // Connected mode: collect curator details
  let curatorUrl = '';
  let curatorToken = '';

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
      log.warn('No invite token provided. Set it later via: openclaw-lacp-connect join');
    }
  }

  if (operatingMode === 'curator') {
    log.info('Curator mode flags will be written to config.\n' +
      dim('Full curator configuration (connectors, schedule, git backup, invites)\n') +
      dim('will be available in a future release.'));
  }

  // obsidian-headless check for connected/curator
  if (operatingMode === 'connected' || operatingMode === 'curator') {
    if (!deps.obsidianHeadless) {
      const installOb = handleCancel(await confirm({
        message: 'obsidian-headless (ob) is required for this mode. Install it now?',
        initialValue: true,
      }));

      if (installOb) {
        const s = spinner();
        s.start('Installing obsidian-headless...');
        try {
          await runCommand('npm install -g obsidian-headless');
          s.stop('obsidian-headless installed');
          deps.obsidianHeadless = true;
        } catch {
          s.stop(red('obsidian-headless installation failed'));
          log.warn(`Falling back to standalone mode. Install later:\n  npm install -g obsidian-headless`);
          operatingMode = 'standalone';
          curatorUrl = '';
          curatorToken = '';
        }
      } else {
        log.warn(`Cannot proceed with ${operatingMode} mode without obsidian-headless.\nFalling back to standalone mode.`);
        operatingMode = 'standalone';
        curatorUrl = '';
        curatorToken = '';
      }
    }
  }

  // ── Step 5: Dependencies Check ──────────────────────────────────────────

  log.step(bold('Dependencies'));

  // QMD
  if (deps.qmd) {
    log.success(`QMD found ${dim(`(${deps.qmdPath})`)}`);
  } else {
    const installQmd = handleCancel(await confirm({
      message: 'QMD not found. Install it? (semantic vector search for vault)',
      initialValue: true,
    }));

    if (installQmd) {
      const s = spinner();
      s.start('Installing QMD...');
      try {
        await runCommand('npm install -g @tobilu/qmd');
        s.stop('QMD installed');
        deps.qmd = true;
      } catch {
        s.stop(red('QMD installation failed'));
        log.warn('Skipped QMD. Install later: npm install -g @tobilu/qmd');
      }
    } else {
      log.info('Skipped QMD installation');
    }
  }

  // Obsidian CLI
  if (deps.obsidianCli) {
    log.success(`Obsidian CLI found ${dim(`(${deps.obsidianCliPath})`)}`);
  } else {
    const installObsCli = handleCancel(await confirm({
      message: 'Obsidian CLI not found. Install it? (manage vault from terminal)',
      initialValue: false,
    }));

    if (installObsCli) {
      const s = spinner();
      s.start('Installing Obsidian CLI...');
      try {
        await runCommand('npm install -g obsidian-cli');
        s.stop('Obsidian CLI installed');
        deps.obsidianCli = true;
      } catch {
        s.stop(red('Obsidian CLI installation failed'));
        log.warn('Skipped Obsidian CLI. Install later: npm install -g obsidian-cli');
      }
    } else {
      log.info('Skipped Obsidian CLI installation');
    }
  }

  // lossless-claw (if selected but not installed)
  let contextEngineResolved = contextEngine;
  if (contextEngine === 'lossless-claw' && !deps.losslessClaw) {
    const installLc = handleCancel(await confirm({
      message: 'lossless-claw is not installed. Install it now?',
      initialValue: true,
    }));

    if (installLc) {
      const s = spinner();
      s.start('Installing lossless-claw...');
      try {
        await runCommand('openclaw plugins install @martian-engineering/lossless-claw');
        s.stop('lossless-claw installed');
        deps.losslessClaw = true;
      } catch {
        s.stop(red('lossless-claw installation failed'));
        log.warn('Falling back to file-based context engine.\nInstall later: openclaw plugins install @martian-engineering/lossless-claw');
        contextEngineResolved = 'file-based';
      }
    } else {
      log.warn('lossless-claw not available. Falling back to file-based context engine.');
      contextEngineResolved = 'file-based';
    }
  }

  // ── Step 6: Advanced Config ─────────────────────────────────────────────

  let policyTier = 'review';
  let codeGraph = false;
  let provenance = true;
  let localFirst = true;
  let guardLevel = 'block';
  let disabledRules = [];
  let ruleOverrides = {};

  const wantAdvanced = handleCancel(await confirm({
    message: 'Configure advanced options?',
    initialValue: false,
  }));

  if (wantAdvanced) {
    log.step(bold('Advanced Configuration'));

    // Policy tier
    policyTier = handleCancel(await select({
      message: 'Default policy tier',
      options: [
        { value: 'review', label: 'review', hint: 'require review before execution' },
        { value: 'safe', label: 'safe', hint: 'auto-approve safe operations' },
        { value: 'critical', label: 'critical', hint: 'all operations require approval' },
      ],
    }));
    log.success(`Policy tier: ${green(policyTier)}`);

    // Code intelligence
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
          const s = spinner();
          s.start('Installing GitNexus...');
          try {
            await runCommand('npm install -g gitnexus');
            s.stop('GitNexus installed');
            codeGraph = true;
            deps.gitnexus = true;
          } catch {
            s.stop(red('GitNexus installation failed'));
            log.warn('Code intelligence disabled. Install later: npm install -g gitnexus');
          }
        } else {
          log.info('Skipped GitNexus. Code intelligence disabled.');
        }
      }
    }

    // Provenance
    provenance = handleCancel(await confirm({
      message: 'Enable provenance tracking?',
      initialValue: true,
    }));
    log.success(`Provenance: ${green(provenance ? 'enabled' : 'disabled')}`);

    // Local-first
    localFirst = handleCancel(await confirm({
      message: 'Local-first mode (no external sync)?',
      initialValue: true,
    }));
    log.success(`Local-first: ${green(localFirst ? 'enabled' : 'disabled')}`);

    // Guard configuration
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

    // Individual guard rules
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

        // Select which rules to DISABLE
        const rulesToDisable = handleCancel(await multiselect({
          message: 'Select rules to DISABLE (all enabled by default)',
          options: ruleOptions,
          required: false,
        }));

        disabledRules = rulesToDisable || [];

        if (disabledRules.length > 0) {
          log.info(`${disabledRules.length} rule${disabledRules.length === 1 ? '' : 's'} will be disabled: ${dim(disabledRules.join(', '))}`);
        } else {
          log.success('All guard rules remain enabled');
        }

        // Offer per-rule overrides for remaining enabled rules
        const enabledRules = guardData.rules.filter(r => !disabledRules.includes(r.id));
        if (enabledRules.length > 0) {
          const wantOverrides = handleCancel(await confirm({
            message: 'Override block level for specific rules?',
            initialValue: false,
          }));

          if (wantOverrides) {
            for (const rule of enabledRules) {
              const override = handleCancel(await select({
                message: `${rule.label || rule.id} [currently: ${rule.block_level}]`,
                options: [
                  { value: '__keep__', label: `Keep: ${rule.block_level}`, hint: 'no change' },
                  { value: 'block', label: 'block' },
                  { value: 'warn', label: 'warn' },
                  { value: 'log', label: 'log' },
                ],
              }));

              if (override !== '__keep__') {
                ruleOverrides[rule.id] = override;
              }
            }

            const overrideCount = Object.keys(ruleOverrides).length;
            if (overrideCount > 0) {
              log.info(`${overrideCount} rule override${overrideCount === 1 ? '' : 's'} configured`);
            }
          }
        }
      } else {
        log.warn('Guard rules config not found -- will use factory defaults');
      }
    }
  }

  // ── Step 7: Agent Selection ─────────────────────────────────────────────

  let selectedAgents = [];
  let agentWorkspaces = {};

  // Scan openclaw.json for configured agents
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
      // Build workspace map for selected agents
      for (const agentId of selectedAgents) {
        const agent = allAgents.find(a => a.id === agentId);
        if (agent?.workspace) {
          agentWorkspaces[agentId] = agent.workspace;
        }
      }

      log.success(`${selectedAgents.length} agent${selectedAgents.length === 1 ? '' : 's'} selected: ${selectedAgents.join(', ')}`);

      // Check which workspaces have TOOLS.md
      const toolsMdAgents = selectedAgents.filter(id => {
        const ws = agentWorkspaces[id];
        return ws && existsSync(join(ws, 'TOOLS.md'));
      });
      const noToolsMdAgents = selectedAgents.filter(id => {
        const ws = agentWorkspaces[id];
        return ws && !existsSync(join(ws, 'TOOLS.md'));
      });

      if (toolsMdAgents.length > 0) {
        log.info(`Will append Engram docs to TOOLS.md: ${toolsMdAgents.join(', ')}`);
      }
      if (noToolsMdAgents.length > 0) {
        log.info(`Will create TOOLS.md for: ${noToolsMdAgents.join(', ')}`);
      }
    } else {
      log.info('No agents selected — TOOLS.md will not be modified');
    }
  } else {
    log.info('No agents found in OpenClaw config — skipping agent selection');
  }

  // ── Step 8: Summary ─────────────────────────────────────────────────────

  const summaryLines = [
    `Obsidian vault:    ${green(vaultPath)}`,
    `Context engine:    ${green(contextEngineResolved)}`,
    `Safety profile:    ${green(safetyProfile)}`,
    `Operating mode:    ${green(operatingMode)}`,
    `Policy tier:       ${green(policyTier)}`,
    `Code graph:        ${green(String(codeGraph))}`,
    `Provenance:        ${green(String(provenance))}`,
    `Local-first:       ${green(String(localFirst))}`,
    `Guard level:       ${green(guardLevel)}`,
  ];

  if (operatingMode === 'connected' && curatorUrl) {
    summaryLines.push(`Curator URL:       ${green(curatorUrl)}`);
  }

  if (selectedAgents.length > 0) {
    summaryLines.push(`Agents:            ${green(selectedAgents.join(', '))}`);
  }

  if (disabledRules.length > 0) {
    summaryLines.push(`Disabled rules:    ${yellow(disabledRules.join(', '))}`);
  }

  const overrideCount = Object.keys(ruleOverrides).length;
  if (overrideCount > 0) {
    summaryLines.push(`Rule overrides:    ${yellow(`${overrideCount} rule${overrideCount === 1 ? '' : 's'}`)}`);
  }

  summaryLines.push('');
  summaryLines.push(`Install path:      ${dim(join(OPENCLAW_HOME, 'extensions', 'engram'))}`);

  note(summaryLines.join('\n'), 'Installation Summary');

  const confirmed = handleCancel(await confirm({
    message: 'Proceed with installation?',
    initialValue: true,
  }));

  if (!confirmed) {
    cancel('Installation cancelled.');
    process.exit(0);
  }

  // ── Step 8: Write Config ────────────────────────────────────────────────

  const config = {
    version: '1.0.0',
    timestamp: new Date().toISOString(),
    vault: vaultPath,
    contextEngine: contextEngineResolved,
    safetyProfile,
    operatingMode,
    curatorUrl: curatorUrl || null,
    curatorToken: curatorToken || null,
    policyTier,
    codeGraph,
    provenance,
    localFirst,
    guardLevel,
    disabledRules,
    ruleOverrides,
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
  };

  try {
    writeFileSync(CONFIG_OUTPUT, JSON.stringify(config, null, 2), 'utf-8');
    log.success(`Config written to ${dim(CONFIG_OUTPUT)}`);
  } catch (err) {
    log.error(`Failed to write config: ${err.message}`);
    process.exit(1);
  }

  outro(bold('Configuration complete. Starting installation...'));
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
