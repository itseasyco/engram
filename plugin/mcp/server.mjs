#!/usr/bin/env node
/**
 * engram MCP Server
 *
 * Exposes engram's memory tools over the Model Context Protocol (stdio).
 * Works with Claude Code, Codex, and any MCP-compatible client.
 *
 * Usage:
 *   node server.mjs                          # stdio mode (default)
 *   ENGRAM_DIR=/path/to/plugin node server.mjs
 *   LACP_OBSIDIAN_VAULT=/path/to/vault node server.mjs
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);

// ── Path resolution ──────────────────────────────────────────────────────────

const __dirname = dirname(fileURLToPath(import.meta.url));
const ENGRAM_DIR = process.env.ENGRAM_DIR || join(__dirname, "..");
const BIN_DIR = join(ENGRAM_DIR, "bin");

function resolveVaultPath() {
  if (process.env.LACP_OBSIDIAN_VAULT) return process.env.LACP_OBSIDIAN_VAULT;
  try {
    const envFile = join(ENGRAM_DIR, "config", ".engram.env");
    const content = readFileSync(envFile, "utf-8");
    const match = content.match(/^LACP_OBSIDIAN_VAULT=(.+)$/m);
    if (match) return match[1].trim();
  } catch {}
  return join(process.env.HOME ?? "", ".openclaw", "data", "knowledge");
}

const VAULT_PATH = resolveVaultPath();

const ENV = {
  ...process.env,
  OPENCLAW_PLUGIN_DIR: ENGRAM_DIR,
  LACP_OBSIDIAN_VAULT: VAULT_PATH,
};

// ── CLI runner ───────────────────────────────────────────────────────────────

async function runCli(cmd, args, timeoutMs = 30_000) {
  const cmdPath = join(BIN_DIR, cmd);
  try {
    const { stdout, stderr } = await execFileAsync(cmdPath, args, {
      encoding: "utf-8",
      timeout: timeoutMs,
      env: ENV,
    });
    return { stdout: (stdout ?? "").trim(), stderr: (stderr ?? "").trim(), exitCode: 0 };
  } catch (err) {
    return {
      stdout: (err.stdout ?? "").trim(),
      stderr: (err.stderr ?? err.message ?? "").trim(),
      exitCode: err.code ?? err.status ?? 1,
    };
  }
}

function textResult(text) {
  return { content: [{ type: "text", text }] };
}

function errorResult(text) {
  return { content: [{ type: "text", text }], isError: true };
}

// ── MCP Server ───────────────────────────────────────────────────────────────

const server = new McpServer({
  name: "engram",
  version: "3.2.0",
  description: "Engram — persistent memory, knowledge graph, and safety tools for AI agents",
});

// ── Memory Query ─────────────────────────────────────────────────────────────

server.tool(
  "engram_memory_query",
  "Search engram persistent memory for relevant facts about a project or topic. " +
  "Returns previously learned knowledge, decisions, patterns, and context " +
  "that was promoted from past sessions. Use this when you need institutional " +
  "knowledge or want to check if something was already decided/discovered.",
  {
    query: z.string().describe("Search query — topic, concept, or question to look up"),
    project: z.string().optional().describe("Project name to scope the search (default: current project)"),
    min_score: z.number().optional().describe("Minimum relevance score 0-100 (default: 50)"),
  },
  async ({ query, project, min_score }) => {
    const args = ["query", "--topic", query];
    if (project) args.push("--project", project);
    if (min_score != null) args.push("--min-score", String(min_score));
    args.push("--format", "text");
    const result = await runCli("engram-context", args);
    return textResult(result.stdout || "No matching facts found.");
  }
);

// ── Ingest ───────────────────────────────────────────────────────────────────

server.tool(
  "engram_ingest",
  "Ingest a file, URL, or transcript into the engram knowledge graph (Obsidian vault). " +
  "Use this to permanently store useful information — meeting notes, documentation, " +
  "research findings, or any content that should be available in future sessions.",
  {
    type: z.enum(["file", "transcript", "url", "pdf", "video", "video-batch"])
      .describe("Content type to ingest"),
    source: z.string().describe("File path, URL, or directory path (for video-batch) to ingest"),
    title: z.string().optional().describe("Title for the ingested content (or title prefix for video-batch)"),
    speaker: z.string().optional().describe("Speaker name (for transcripts and video)"),
    model: z.string().optional().describe("Whisper model for video: tiny, base, small, medium, large. Default: base"),
  },
  async ({ type, source, title, speaker, model }) => {
    const args = [type, VAULT_PATH, source];
    if (title) args.push(type === "video-batch" ? "--title-prefix" : "--title", title);
    if (speaker) args.push("--speaker", speaker);
    if (model) args.push("--model", model);
    const timeout = type.startsWith("video") ? 600_000 : 60_000;
    const result = await runCli("engram-brain-ingest", args, timeout);
    if (result.exitCode !== 0) {
      return errorResult(`Ingestion failed: ${result.stderr || result.stdout}`);
    }
    return textResult(result.stdout || "Content ingested successfully.");
  }
);

// ── Guard Status ─────────────────────────────────────────────────────────────

server.tool(
  "engram_guard_status",
  "Check the current state of the pretool guard — active rules, recent blocks, " +
  "and allowlisted commands. Use this to understand what safety rules are in place " +
  "and what has been blocked recently.",
  {
    show: z.enum(["rules", "blocks", "all"]).optional().describe("What to show (default: all)"),
    tail: z.number().optional().describe("Number of recent blocks to show (default: 10)"),
  },
  async ({ show, tail }) => {
    const mode = show ?? "all";
    const parts = [];
    if (mode === "rules" || mode === "all") {
      const rules = await runCli("engram-guard", ["rules"]);
      parts.push("## Guard Rules\n" + rules.stdout);
    }
    if (mode === "blocks" || mode === "all") {
      const t = tail ? String(tail) : "10";
      const blocks = await runCli("engram-guard", ["blocks", "--tail", t]);
      parts.push("## Recent Blocks\n" + (blocks.stdout || "No recent blocks."));
    }
    return textResult(parts.join("\n\n"));
  }
);

// ── Promote Fact ─────────────────────────────────────────────────────────────

server.tool(
  "engram_promote_fact",
  "Promote an important fact, decision, or learning to engram persistent memory. " +
  "Use this when you discover something that should be remembered across sessions — " +
  "architectural decisions, bug patterns, team preferences, or project context. " +
  "Promoted facts are injected into future sessions via the session-start hook.",
  {
    fact: z.string().describe("The fact or learning to promote to persistent memory"),
    reasoning: z.string().describe("Why this fact is worth remembering across sessions"),
    category: z.string().optional().describe('Category: decision, pattern, context, preference, bug. Default: context'),
  },
  async ({ fact, reasoning, category }) => {
    const args = ["manual", "--summary", "agent-promoted", "--fact", fact, "--reasoning", reasoning];
    if (category) args.push("--category", category);
    const result = await runCli("engram-promote", args);
    if (result.exitCode !== 0) {
      return errorResult(`Promotion failed: ${result.stderr || result.stdout}`);
    }
    return textResult(result.stdout || "Fact promoted to persistent memory.");
  }
);

// ── Vault Status ─────────────────────────────────────────────────────────────

server.tool(
  "engram_vault_status",
  "Check the health and statistics of the Obsidian knowledge vault — " +
  "total notes, broken links, orphan notes, and vault size.",
  {
    audit: z.boolean().optional().describe("Run a full audit (check broken links, orphans). Default: false"),
  },
  async ({ audit }) => {
    const cmd = audit ? "audit" : "status";
    const result = await runCli("engram-obsidian", [cmd]);
    return textResult(result.stdout || "Could not retrieve vault status.");
  }
);

// ── Vault Optimize ───────────────────────────────────────────────────────────

server.tool(
  "engram_vault_optimize",
  "Apply memory-centric graph physics defaults to the Obsidian vault — " +
  "tune link distance, repel strength, node sizing, and color groups.",
  {
    vault: z.string().optional().describe("Vault path (default: from config)"),
    dry_run: z.boolean().optional().describe("Preview changes without writing. Default: false"),
  },
  async ({ vault, dry_run }) => {
    const args = ["--json"];
    if (vault) args.push("--vault", vault);
    if (dry_run) args.push("--dry-run");
    const result = await runCli("engram-obsidian-optimize", args);
    return textResult(result.stdout || `vault-optimize failed: ${result.stderr}`);
  }
);

// ── Graph Index ──────────────────────────────────────────────────────────────

server.tool(
  "engram_graph_index",
  "Index session memory into the knowledge graph and optionally update " +
  "QMD vector embeddings. Use after a productive session to ensure " +
  "learnings are captured in the knowledge graph for future retrieval.",
  {
    session_dir: z.string().optional().describe("Session directory to index (default: current session)"),
    update_qmd: z.boolean().optional().describe("Also update QMD vector embeddings. Default: false"),
  },
  async ({ session_dir, update_qmd }) => {
    const args = ["index", VAULT_PATH];
    if (session_dir) args.splice(1, 0, session_dir);
    if (update_qmd) args.push("--update-qmd");
    const result = await runCli("engram-brain-graph", args, 60_000);
    return textResult(result.stdout || "Knowledge graph indexed.");
  }
);

// ── Brain Resolve ────────────────────────────────────────────────────────────

server.tool(
  "engram_brain_resolve",
  "Resolve contradiction or supersession state for a canonical memory note. " +
  "Use this when you find conflicting information in the knowledge vault.",
  {
    id: z.string().describe("Canonical note ID to resolve"),
    resolution: z.enum(["superseded", "contradiction_resolved", "validated", "stale", "archived"])
      .describe("Resolution type"),
    reason: z.string().describe("Why this resolution was applied"),
    superseded_by: z.string().optional().describe("ID of replacement note (for superseded resolution)"),
    dry_run: z.boolean().optional().describe("Preview changes without writing. Default: false"),
  },
  async ({ id, resolution, reason, superseded_by, dry_run }) => {
    const args = ["--id", id, "--resolution", resolution, "--reason", reason, "--json"];
    if (superseded_by) args.push("--superseded-by", superseded_by);
    if (dry_run) args.push("--dry-run");
    const result = await runCli("engram-brain-resolve", args);
    return textResult(result.stdout || `brain-resolve failed: ${result.stderr}`);
  }
);

// ── Memory KPI ───────────────────────────────────────────────────────────────

server.tool(
  "engram_memory_kpi",
  "Report memory-quality KPIs for the Obsidian knowledge vault — " +
  "total notes, canonical notes, schema coverage, source backing, " +
  "contradiction count, and staleness.",
  {
    vault: z.string().optional().describe("Vault path (default: from config)"),
  },
  async ({ vault }) => {
    const args = ["--json"];
    if (vault) args.push("--vault", vault);
    const result = await runCli("engram-memory-kpi", args);
    return textResult(result.stdout || `memory-kpi failed: ${result.stderr}`);
  }
);

// ── Save Session ─────────────────────────────────────────────────────────────

server.tool(
  "engram_save_session",
  "Save a session memory to the daily folder in the knowledge vault. " +
  "Call this at the end of a session to record what happened — summary, " +
  "key decisions, tasks completed/pending, and facts promoted.",
  {
    agent_name: z.string().describe("Your agent name (e.g., Wren, Zoe, Vijay)"),
    summary: z.string().describe("Brief summary of what happened in this session"),
    key_decisions: z.array(z.string()).optional().describe("Key decisions made"),
    tasks_completed: z.array(z.string()).optional().describe("Tasks completed"),
    tasks_pending: z.array(z.string()).optional().describe("Tasks still pending"),
    facts_promoted: z.array(z.string()).optional().describe("Facts promoted to Engram this session"),
    files_modified: z.array(z.string()).optional().describe("Files modified"),
  },
  async (params) => {
    const script = join(ENGRAM_DIR, "lib", "session_writer.py");
    const payload = JSON.stringify(params);
    try {
      const { stdout } = await execFileAsync("python3", ["-c",
        `import json, sys, os\n` +
        `sys.path.insert(0, os.path.join(os.environ["OPENCLAW_PLUGIN_DIR"], "lib"))\n` +
        `from session_writer import write_session_memory\n` +
        `params = json.load(sys.stdin)\n` +
        `result = write_session_memory(**params)\n` +
        `print(json.dumps(result, indent=2))`
      ], {
        input: payload,
        encoding: "utf-8",
        timeout: 10_000,
        env: ENV,
      });
      return textResult(stdout.trim());
    } catch (err) {
      return errorResult(`Session save failed: ${err.stderr || err.message}`);
    }
  }
);

// ── Start ────────────────────────────────────────────────────────────────────

const transport = new StdioServerTransport();
await server.connect(transport);
