/**
 * engram — gateway entry point
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
      env: { ...process.env, OPENCLAW_PLUGIN_DIR: pluginDir, LACP_OBSIDIAN_VAULT: vaultPath },
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

import { appendFileSync, mkdirSync, readFileSync as readFileSyncFs } from "node:fs";

// Resolve vault path from env or config file
function resolveVaultPath(): string {
  if (process.env.LACP_OBSIDIAN_VAULT) return process.env.LACP_OBSIDIAN_VAULT;
  try {
    const envFile = join(pluginDir, "config", ".engram.env");
    const content = readFileSyncFs(envFile, "utf-8");
    const match = content.match(/^LACP_OBSIDIAN_VAULT=(.+)$/m);
    if (match) return match[1].trim();
  } catch {}
  return join(process.env.HOME ?? "", ".openclaw", "data", "knowledge");
}
const vaultPath = resolveVaultPath();

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
      env: { ...process.env, OPENCLAW_PLUGIN_DIR: pluginDir, LACP_OBSIDIAN_VAULT: vaultPath },
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

const engramPlugin = {
  name: "Engram",
  description:
    "Persistent memory, knowledge graph, policy gates, and provenance chain for AI agents",

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
      const toolName = (event as any)?.toolName ?? (event as any)?.name ?? (event as any)?.tool_name ?? "";
      const toolInput = (event as any)?.params ?? (event as any)?.input ?? (event as any)?.tool_input ?? {};
      const hasCommand = typeof toolInput.command === "string";
      const hasFilePath = typeof (toolInput.file_path ?? toolInput.path) === "string";

      if (!hasCommand && !hasFilePath) return;

      // Normalize: gateway uses "path" but our guard expects "file_path"
      const normalizedInput = { ...toolInput };
      if (!normalizedInput.file_path && normalizedInput.path) {
        normalizedInput.file_path = normalizedInput.path;
      }

      const payload = JSON.stringify({ tool_input: normalizedInput, tool_name: toolName });
      const scriptPath = join(pluginDir, "hooks", "handlers", "pretool-guard.py");

      logToolCall({
        hook: "before_tool_call",
        toolName,
        guardMode: hasCommand ? "command" : "file",
        commandPreview: (toolInput.command || toolInput.file_path || "").substring(0, 200),
      });

      try {
        const stdout = execFileSync("python3", [scriptPath, "structured"], {
          input: payload,
          encoding: "utf-8",
          timeout: 10_000,
          env: { ...process.env, OPENCLAW_PLUGIN_DIR: pluginDir, LACP_OBSIDIAN_VAULT: vaultPath },
        });

        const verdict = JSON.parse(stdout.trim());

        logToolCall({
          hook: "before_tool_call_result",
          verdict: verdict.verdict,
          ruleId: verdict.rule_id,
          blocked: verdict.verdict === "block",
        });

        if (verdict.verdict === "block") {
          return {
            block: true,
            blockReason: verdict.message || `Blocked by guard rule: ${verdict.rule_id}`,
          };
        }

        if (verdict.verdict === "warn") {
          return {
            requireApproval: {
              title: `Guard: ${verdict.label || verdict.rule_id}`,
              description: verdict.message,
              severity: verdict.category === "exfiltration" ? "critical" as const : "warning" as const,
              timeoutMs: 120_000,
              timeoutBehavior: "deny" as const,
            },
          };
        }

        // "allow" and "log" — let the tool call proceed
      } catch (err: any) {
        // Script crashed or timed out — fail closed
        const stderr = err.stderr?.toString().trim() ?? "";
        logToolCall({
          hook: "before_tool_call_result",
          error: stderr.substring(0, 300),
          blocked: true,
        });
        return {
          block: true,
          blockReason: stderr || "pretool-guard failed unexpectedly — blocking for safety",
        };
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
      name: "engram_memory_query",
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
        const result = await runCli("engram-context", args);
        return textResult(result.stdout || "No matching facts found.");
      },
    });

    // Ingest: add files, URLs, or transcripts to the knowledge graph
    api.registerTool({
      name: "engram_ingest",
      description:
        "Ingest a file, URL, or transcript into the LACP knowledge graph (Obsidian vault). " +
        "Use this to permanently store useful information — meeting notes, documentation, " +
        "research findings, or any content that should be available in future sessions.",
      parameters: Type.Object({
        type: Type.String({
          description: 'Content type: "file" (markdown/text), "transcript" (meeting/conversation), "url" (web page), "pdf", "video" (mp4/mov/audio, auto-transcribes with Whisper), "video-batch" (all media in a directory)',
          enum: ["file", "transcript", "url", "pdf", "video", "video-batch"],
        }),
        source: Type.String({ description: "File path, URL, or directory path (for video-batch) to ingest" }),
        title: Type.Optional(Type.String({ description: "Title for the ingested content (or title prefix for video-batch)" })),
        speaker: Type.Optional(Type.String({ description: "Speaker name (for transcripts and video)" })),
        model: Type.Optional(Type.String({ description: "Whisper model for video: tiny, base, small, medium, large. Default: base" })),
      }),
      async execute(_id, params: any) {
        const args = [params.type, vaultPath, params.source];
        if (params.title) {
          args.push(params.type === "video-batch" ? "--title-prefix" : "--title", params.title);
        }
        if (params.speaker) args.push("--speaker", params.speaker);
        if (params.model) args.push("--model", params.model);
        // Video transcription can take a long time
        const timeout = params.type.startsWith("video") ? 600_000 : 60_000;
        const result = await runCli("engram-brain-ingest", args, timeout);
        if (result.exitCode !== 0) {
          return textResult(`Ingestion failed: ${result.stderr || result.stdout}`);
        }
        return textResult(result.stdout || "Content ingested successfully.");
      },
    });

    // Guard status: check current guard rules, recent blocks, and allowlist
    api.registerTool({
      name: "engram_guard_status",
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
          const rules = await runCli("engram-guard", ["rules"]);
          parts.push("## Guard Rules\n" + rules.stdout);
        }
        if (show === "blocks" || show === "all") {
          const tail = params.tail ? String(params.tail) : "10";
          const blocks = await runCli("engram-guard", ["blocks", "--tail", tail]);
          parts.push("## Recent Blocks\n" + (blocks.stdout || "No recent blocks."));
        }

        return textResult(parts.join("\n\n"));
      },
    });

    // Promote: promote a fact from session memory to persistent LACP memory
    api.registerTool({
      name: "engram_promote_fact",
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
        const result = await runCli("engram-promote", args);
        if (result.exitCode !== 0) {
          return textResult(`Promotion failed: ${result.stderr || result.stdout}`);
        }
        return textResult(result.stdout || "Fact promoted to persistent memory.");
      },
    });

    // Vault status: check Obsidian vault health and statistics
    api.registerTool(
      {
        name: "engram_vault_status",
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
          const result = await runCli("engram-obsidian", [cmd]);
          return textResult(result.stdout || "Could not retrieve vault status.");
        },
      },
      { optional: true },
    );

    // Knowledge graph: index session memory into the knowledge graph
    api.registerTool(
      {
        name: "engram_graph_index",
        description:
          "Index session memory into the knowledge graph and optionally update " +
          "QMD vector embeddings. Use this after a productive session to ensure " +
          "learnings are captured in the knowledge graph for future retrieval.",
        parameters: Type.Object({
          session_dir: Type.Optional(Type.String({ description: "Session directory to index (default: current session)" })),
          update_qmd: Type.Optional(Type.Boolean({ description: "Also update QMD vector embeddings. Default: false" })),
        }),
        async execute(_id, params: any) {
          const args = ["index", vaultPath];
          if (params.session_dir) args.splice(1, 0, params.session_dir);
          if (params.update_qmd) args.push("--update-qmd");
          const result = await runCli("engram-brain-graph", args, 60_000);
          return textResult(result.stdout || "Knowledge graph indexed.");
        },
      },
      { optional: true },
    );

    // Brain resolve: resolve contradictions/supersessions in knowledge notes
    api.registerTool({
      name: "engram_brain_resolve",
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
        const result = await runCli("engram-brain-resolve", args);
        return textResult(result.stdout || `brain-resolve failed: ${result.stderr}`);
      },
    });

    // Memory KPI: vault quality metrics
    api.registerTool({
      name: "engram_memory_kpi",
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
        const result = await runCli("engram-memory-kpi", args);
        return textResult(result.stdout || `memory-kpi failed: ${result.stderr}`);
      },
    });

    // Vault optimize: apply memory-centric Obsidian graph defaults
    api.registerTool({
      name: "engram_vault_optimize",
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
        const result = await runCli("engram-obsidian-optimize", args);
        return textResult(result.stdout || `vault-optimize failed: ${result.stderr}`);
      },
    });

    // Save session memory to daily folder structure
    api.registerTool({
      name: "engram_save_session",
      description:
        "Save a session memory to the daily folder in the knowledge vault. " +
        "Call this at the end of a session to record what happened — summary, " +
        "key decisions, tasks completed/pending, and facts promoted. " +
        "Creates a per-agent session file linked in the daily index.",
      parameters: Type.Object({
        agent_name: Type.String({ description: "Your agent name (e.g., Wren, Zoe, Vijay)" }),
        summary: Type.String({ description: "Brief summary of what happened in this session" }),
        key_decisions: Type.Optional(Type.Array(Type.String(), { description: "Key decisions made" })),
        tasks_completed: Type.Optional(Type.Array(Type.String(), { description: "Tasks completed" })),
        tasks_pending: Type.Optional(Type.Array(Type.String(), { description: "Tasks still pending" })),
        facts_promoted: Type.Optional(Type.Array(Type.String(), { description: "Facts promoted to Engram this session" })),
        files_modified: Type.Optional(Type.Array(Type.String(), { description: "Files modified" })),
      }),
      async execute(_id, params: any) {
        const payload = JSON.stringify(params);
        try {
          // Pass params via stdin to avoid code injection through python3 -c templating
          const result = execFileSync("python3", ["-c",
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
            env: { ...process.env, OPENCLAW_PLUGIN_DIR: pluginDir, LACP_OBSIDIAN_VAULT: vaultPath },
          });
          return textResult(result.trim());
        } catch (err: any) {
          return textResult(`Session save failed: ${err.stderr || err.message}`);
        }
      },
    });

    // engram_meeting_briefing — generate pre-meeting dossier
    api.registerTool({
      name: "engram_meeting_briefing",
      description:
        "Generate a pre-meeting intelligence dossier. Queries the knowledge graph " +
        "for each attendee: past meetings, relationships, network connections, " +
        "web search for recent news, and LLM-generated talking points. " +
        "Writes briefing to meetings/briefings/.",
      parameters: Type.Object({
        attendee_slugs: Type.Array(Type.String(), {
          description: "Slugs of attendees to research (e.g., ['kate-levchuk', 'marc-andreessen'])",
        }),
        meeting_title: Type.String({ description: "Meeting title" }),
        meeting_date: Type.String({ description: "Meeting date (YYYY-MM-DD)" }),
        dry_run: Type.Optional(Type.Boolean({ description: "Preview without writing. Default: false" })),
      }),
      async execute(_id, params: any) {
        const args = [
          "--vault", vaultPath,
          "--title", params.meeting_title,
          "--date", params.meeting_date,
          "--attendees", params.attendee_slugs.join(","),
        ];
        if (params.dry_run) args.push("--dry-run");
        const result = await runCli("engram-meeting-briefing", args);
        return textResult(result.stdout || `meeting-briefing failed: ${result.stderr}`);
      },
    });

    // engram_relationship_query — query the relationship graph
    api.registerTool({
      name: "engram_relationship_query",
      description:
        "Query the knowledge graph for relationships. Examples: " +
        "'Who do we know at A16Z?', 'How are Kate and Andrew connected?', " +
        "'Find paths between Person X and Goal Y within 3 hops.'",
      parameters: Type.Object({
        query: Type.String({ description: "Natural language relationship query" }),
        max_hops: Type.Optional(Type.Number({ description: "Maximum traversal depth (default: 3)" })),
      }),
      async execute(_id, params: any) {
        const args = [
          "--vault", vaultPath,
          "--query", params.query,
        ];
        if (params.max_hops) args.push("--max-hops", String(params.max_hops));
        const result = await runCli("engram-relationship-query", args);
        return textResult(result.stdout || `relationship-query failed: ${result.stderr}`);
      },
    });

    // engram_deal_pipeline — view deal stages, overdue actions
    api.registerTool({
      name: "engram_deal_pipeline",
      description:
        "View the deal pipeline: relationships grouped by stage, stale deals, " +
        "overdue follow-ups, and opportunity scores.",
      parameters: Type.Object({
        stage: Type.Optional(Type.String({ description: "Filter by stage (e.g., 'active-conversation')" })),
      }),
      async execute(_id, params: any) {
        const args = ["--vault", vaultPath];
        if (params.stage) args.push("--stage", params.stage);
        const result = await runCli("engram-deal-pipeline", args);
        return textResult(result.stdout || "No pipeline data available.");
      },
    });

    // engram_objective_status — score a goal against all signals
    api.registerTool({
      name: "engram_objective_status",
      description:
        "Score the current state of a goal against all relationship signals, " +
        "meeting history, and network connections.",
      parameters: Type.Object({
        goal_slug: Type.String({ description: "Slug of the goal to score" }),
      }),
      async execute(_id, params: any) {
        const args = ["--vault", vaultPath, "--goal", params.goal_slug];
        const result = await runCli("engram-objective-status", args);
        return textResult(result.stdout || "No objective data available.");
      },
    });

    const toolCount = 14;
    api.logger.info(
      `[lacp] Plugin loaded (version=${process.env.npm_package_version ?? "2.2.0"}, hooks=4, tools=${toolCount})`,
    );
  },
};

export default engramPlugin;
