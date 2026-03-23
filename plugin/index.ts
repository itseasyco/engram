/**
 * openclaw-lacp-fusion — gateway entry point
 *
 * Registers lifecycle hooks (Python scripts) and agent tools (CLI wrappers)
 * with the OpenClaw gateway.
 */
import { execFileSync, execFile } from "node:child_process";
import { join } from "node:path";
import { Type } from "@sinclair/typebox";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk";

const pluginDir = new URL(".", import.meta.url).pathname;
const binDir = join(pluginDir, "bin");

// ─── Hook handler runner ─────────────────────────────────────────────────────

type HandlerResult = {
  stdout: string | null;
  exitCode: number;
  blocked: boolean;
  error?: string;
};

function runHandler(script: string, eventJson: string, logger?: { warn: (msg: string) => void }): HandlerResult {
  const scriptPath = join(pluginDir, "hooks", "handlers", script);
  try {
    const result = execFileSync("python3", [scriptPath], {
      input: eventJson,
      encoding: "utf-8",
      timeout: 10_000,
      env: { ...process.env, OPENCLAW_PLUGIN_DIR: pluginDir },
    });
    return { stdout: result.trim() || null, exitCode: 0, blocked: false };
  } catch (err: any) {
    const exitCode = err.status ?? 1;
    const stderr = err.stderr?.toString().trim() ?? "";
    const stdout = err.stdout?.toString().trim() ?? "";
    if (exitCode !== 0 && logger) {
      logger.warn(`[lacp] ${script} exited ${exitCode}: ${stderr || stdout || "unknown error"}`);
    }
    return {
      stdout: stdout || null,
      exitCode,
      blocked: exitCode === 1,
      error: stderr || undefined,
    };
  }
}

// ─── CLI tool runner (async, for agent tools) ────────────────────────────────

import { appendFileSync, mkdirSync } from "node:fs";

const toolLogPath = join(pluginDir, "logs", "tool-calls.jsonl");
try { mkdirSync(join(pluginDir, "logs"), { recursive: true }); } catch {}

function logToolCall(entry: Record<string, unknown>) {
  try {
    const line = JSON.stringify({ timestamp: new Date().toISOString(), ...entry });
    appendFileSync(toolLogPath, line + "\n");
  } catch {}
}

function runCli(cmd: string, args: string[], timeout = 30_000): Promise<{ stdout: string; stderr: string; exitCode: number }> {
  const cmdPath = join(binDir, cmd);
  const startMs = Date.now();
  return new Promise((resolve) => {
    execFile(cmdPath, args, {
      encoding: "utf-8",
      timeout,
      env: { ...process.env, OPENCLAW_PLUGIN_DIR: pluginDir },
    }, (err, stdout, stderr) => {
      const result = {
        stdout: (stdout ?? "").trim(),
        stderr: (stderr ?? "").trim(),
        exitCode: err ? (err as any).status ?? (err as any).code ?? 1 : 0,
      };
      logToolCall({
        tool: cmd,
        args,
        exitCode: result.exitCode,
        durationMs: Date.now() - startMs,
        stdoutLen: result.stdout.length,
        stderrLen: result.stderr.length,
        stdoutPreview: result.stdout.substring(0, 500),
        stderrPreview: result.stderr.substring(0, 500),
        error: err ? String(err.message ?? err) : null,
      });
      resolve(result);
    });
  });
}

function textResult(text: string) {
  return { content: [{ type: "text" as const, text }] };
}

// ─── Plugin ──────────────────────────────────────────────────────────────────

const lacpPlugin = {
  name: "OpenClaw LACP Fusion",
  description:
    "LACP integration — hooks, policy gates, gated execution, memory scaffolding, and evidence verification",

  register(api: OpenClawPluginApi) {

    // ── Lifecycle hooks ────────────────────────────────────────────────────

    api.on("session_start", async (event, ctx) => {
      const result = runHandler("session-start.py", JSON.stringify({ event, ctx }), api.logger);
      if (result.stdout) {
        try {
          const parsed = JSON.parse(result.stdout);
          if (parsed.systemMessage) return parsed;
        } catch { /* not JSON */ }
      }
    });

    api.on("before_tool_call", async (event, ctx) => {
      const result = runHandler("pretool-guard.py", JSON.stringify({ event, ctx }), api.logger);
      if (result.blocked) {
        throw new Error(result.error || result.stdout || "Blocked by pretool-guard");
      }
    });

    api.on("agent_end", async (event, ctx) => {
      const result = runHandler("stop-quality-gate.py", JSON.stringify({ event, ctx }), api.logger);
      if (result.blocked) {
        try {
          const parsed = JSON.parse(result.stdout ?? "{}");
          if (parsed.decision === "block") {
            throw new Error(parsed.reason || "Quality gate blocked stop");
          }
        } catch (e) {
          if (e instanceof Error && e.message !== "Quality gate blocked stop") {
            throw new Error(result.error || "Quality gate blocked stop");
          }
          throw e;
        }
      }
    });

    api.on("before_message_write", async (event, ctx) => {
      const result = runHandler("write-validate.py", JSON.stringify({ event, ctx }), api.logger);
      if (result.exitCode === 2) {
        throw new Error(result.error || "Write validation failed");
      }
    });

    // ── Agent tools ────────────────────────────────────────────────────────

    // Memory query: search LACP persistent memory for relevant facts
    api.registerTool({
      name: "lacp_memory_query",
      description:
        "Search LACP persistent memory for relevant facts about a project or topic. " +
        "Returns previously learned knowledge, decisions, patterns, and context " +
        "that was promoted from past sessions. Use this when you need institutional " +
        "knowledge or want to check if something was already decided/discovered.",
      parameters: Type.Object({
        query: Type.String({ description: "Search query — topic, concept, or question to look up" }),
        project: Type.Optional(Type.String({ description: "Project name to scope the search (default: current project)" })),
        min_score: Type.Optional(Type.Number({ description: "Minimum relevance score 0-100 (default: 50)" })),
      }),
      async execute(_id, params: any) {
        const args = ["query", "--topic", params.query];
        if (params.project) args.push("--project", params.project);
        if (params.min_score) args.push("--min-score", String(params.min_score));
        args.push("--format", "text");
        const result = await runCli("openclaw-lacp-context", args);
        return textResult(result.stdout || "No matching facts found.");
      },
    });

    // Ingest: add files, URLs, or transcripts to the knowledge graph
    api.registerTool({
      name: "lacp_ingest",
      description:
        "Ingest a file, URL, or transcript into the LACP knowledge graph (Obsidian vault). " +
        "Use this to permanently store useful information — meeting notes, documentation, " +
        "research findings, or any content that should be available in future sessions.",
      parameters: Type.Object({
        type: Type.String({
          description: 'Content type: "file" (markdown/text), "transcript" (meeting/conversation), "url" (web page), "pdf"',
          enum: ["file", "transcript", "url", "pdf"],
        }),
        source: Type.String({ description: "File path or URL to ingest" }),
        title: Type.Optional(Type.String({ description: "Title for the ingested content" })),
        speaker: Type.Optional(Type.String({ description: "Speaker name (for transcripts)" })),
      }),
      async execute(_id, params: any) {
        const vaultPath = process.env.LACP_OBSIDIAN_VAULT || join(process.env.HOME ?? "", ".openclaw", "data", "knowledge");
        const args = [params.type, vaultPath, params.source];
        if (params.title) args.push("--title", params.title);
        if (params.speaker) args.push("--speaker", params.speaker);
        const result = await runCli("openclaw-brain-ingest", args, 60_000);
        if (result.exitCode !== 0) {
          return textResult(`Ingestion failed: ${result.stderr || result.stdout}`);
        }
        return textResult(result.stdout || "Content ingested successfully.");
      },
    });

    // Guard status: check current guard rules, recent blocks, and allowlist
    api.registerTool({
      name: "lacp_guard_status",
      description:
        "Check the current state of the pretool guard — active rules, recent blocks, " +
        "and allowlisted commands. Use this to understand what safety rules are in place " +
        "and what has been blocked recently.",
      parameters: Type.Object({
        show: Type.Optional(Type.String({
          description: 'What to show: "rules" (all rules), "blocks" (recent block log), "all" (both). Default: "all"',
          enum: ["rules", "blocks", "all"],
        })),
        tail: Type.Optional(Type.Number({ description: "Number of recent blocks to show (default: 10)" })),
      }),
      async execute(_id, params: any) {
        const show = params.show ?? "all";
        const parts: string[] = [];

        if (show === "rules" || show === "all") {
          const rules = await runCli("openclaw-guard", ["rules"]);
          parts.push("## Guard Rules\n" + rules.stdout);
        }
        if (show === "blocks" || show === "all") {
          const tail = params.tail ? String(params.tail) : "10";
          const blocks = await runCli("openclaw-guard", ["blocks", "--tail", tail]);
          parts.push("## Recent Blocks\n" + (blocks.stdout || "No recent blocks."));
        }

        return textResult(parts.join("\n\n"));
      },
    });

    // Promote: promote a fact from session memory to persistent LACP memory
    api.registerTool({
      name: "lacp_promote_fact",
      description:
        "Promote an important fact, decision, or learning to LACP persistent memory. " +
        "Use this when you discover something that should be remembered across sessions — " +
        "architectural decisions, bug patterns, team preferences, or project context. " +
        "Promoted facts are injected into future sessions via the session-start hook.",
      parameters: Type.Object({
        fact: Type.String({ description: "The fact or learning to promote to persistent memory" }),
        reasoning: Type.String({ description: "Why this fact is worth remembering across sessions" }),
        category: Type.Optional(Type.String({
          description: 'Category: "decision", "pattern", "context", "preference", "bug". Default: "context"',
        })),
      }),
      async execute(_id, params: any) {
        const args = [
          "manual",
          "--summary", "agent-promoted",
          "--fact", params.fact,
          "--reasoning", params.reasoning,
        ];
        if (params.category) args.push("--category", params.category);
        const result = await runCli("openclaw-lacp-promote", args);
        if (result.exitCode !== 0) {
          return textResult(`Promotion failed: ${result.stderr || result.stdout}`);
        }
        return textResult(result.stdout || "Fact promoted to persistent memory.");
      },
    });

    // Vault status: check Obsidian vault health and statistics
    api.registerTool(
      {
        name: "lacp_vault_status",
        description:
          "Check the health and statistics of the Obsidian knowledge vault — " +
          "total notes, broken links, orphan notes, and vault size. " +
          "Use this to monitor the knowledge graph.",
        parameters: Type.Object({
          audit: Type.Optional(Type.Boolean({
            description: "Run a full audit (check broken links, orphans). Default: false",
          })),
        }),
        async execute(_id, params: any) {
          const cmd = params.audit ? "audit" : "status";
          const result = await runCli("openclaw-obsidian", [cmd]);
          return textResult(result.stdout || "Could not retrieve vault status.");
        },
      },
      { optional: true },
    );

    // Knowledge graph: index session memory into the knowledge graph
    api.registerTool(
      {
        name: "lacp_graph_index",
        description:
          "Index session memory into the knowledge graph and optionally update " +
          "QMD vector embeddings. Use this after a productive session to ensure " +
          "learnings are captured in the knowledge graph for future retrieval.",
        parameters: Type.Object({
          session_dir: Type.Optional(Type.String({ description: "Session directory to index (default: current session)" })),
          update_qmd: Type.Optional(Type.Boolean({ description: "Also update QMD vector embeddings. Default: false" })),
        }),
        async execute(_id, params: any) {
          const vaultPath = process.env.LACP_OBSIDIAN_VAULT || join(process.env.HOME ?? "", ".openclaw", "data", "knowledge");
          const args = ["index", vaultPath];
          if (params.session_dir) args.splice(1, 0, params.session_dir);
          if (params.update_qmd) args.push("--update-qmd");
          const result = await runCli("openclaw-brain-graph", args, 60_000);
          return textResult(result.stdout || "Knowledge graph indexed.");
        },
      },
      { optional: true },
    );

    // Brain resolve: resolve contradictions/supersessions in knowledge notes
    api.registerTool({
      name: "lacp_brain_resolve",
      description:
        "Resolve contradiction or supersession state for a canonical memory note. " +
        "Use this when you find conflicting information in the knowledge vault — " +
        "mark notes as superseded, validated, stale, or archived with a reason.",
      parameters: Type.Object({
        id: Type.String({ description: "Canonical note ID to resolve" }),
        resolution: Type.String({
          description: 'Resolution: "superseded", "contradiction_resolved", "validated", "stale", "archived"',
          enum: ["superseded", "contradiction_resolved", "validated", "stale", "archived"],
        }),
        reason: Type.String({ description: "Why this resolution was applied" }),
        superseded_by: Type.Optional(Type.String({ description: "ID of replacement note (for superseded resolution)" })),
        dry_run: Type.Optional(Type.Boolean({ description: "Preview changes without writing. Default: false" })),
      }),
      async execute(_id, params: any) {
        const args = [
          "--id", params.id,
          "--resolution", params.resolution,
          "--reason", params.reason,
          "--json",
        ];
        if (params.superseded_by) args.push("--superseded-by", params.superseded_by);
        if (params.dry_run) args.push("--dry-run");
        const result = await runCli("openclaw-brain-resolve", args);
        return textResult(result.stdout || `brain-resolve failed: ${result.stderr}`);
      },
    });

    // Memory KPI: vault quality metrics
    api.registerTool({
      name: "lacp_memory_kpi",
      description:
        "Report memory-quality KPIs for the Obsidian knowledge vault — " +
        "total notes, canonical notes, schema coverage, source backing, " +
        "contradiction count, and staleness. Use this to assess vault health.",
      parameters: Type.Object({
        vault: Type.Optional(Type.String({ description: "Vault path (default: from config)" })),
      }),
      async execute(_id, params: any) {
        const args = ["--json"];
        if (params.vault) args.push("--vault", params.vault);
        const result = await runCli("openclaw-memory-kpi", args);
        return textResult(result.stdout || `memory-kpi failed: ${result.stderr}`);
      },
    });

    // Vault optimize: apply memory-centric Obsidian graph defaults
    api.registerTool({
      name: "lacp_vault_optimize",
      description:
        "Apply memory-centric graph physics defaults to the Obsidian vault — " +
        "tune link distance, repel strength, node sizing, and color groups " +
        "for optimal knowledge graph visualization. Hides archive/trash paths.",
      parameters: Type.Object({
        vault: Type.Optional(Type.String({ description: "Vault path (default: from config)" })),
        dry_run: Type.Optional(Type.Boolean({ description: "Preview changes without writing. Default: false" })),
      }),
      async execute(_id, params: any) {
        const args = ["--json"];
        if (params.vault) args.push("--vault", params.vault);
        if (params.dry_run) args.push("--dry-run");
        const result = await runCli("openclaw-obsidian-optimize", args);
        return textResult(result.stdout || `vault-optimize failed: ${result.stderr}`);
      },
    });

    const toolCount = 9;
    api.logger.info(
      `[lacp] Plugin loaded (version=${process.env.npm_package_version ?? "2.2.0"}, hooks=4, tools=${toolCount})`,
    );
  },
};

export default lacpPlugin;
