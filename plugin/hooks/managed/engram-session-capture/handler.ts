/**
 * Engram Session Capture Hook
 *
 * Fires on command:new and command:reset to automatically capture
 * session memory into the Engram vault's daily folder structure.
 *
 * Extracts: summary, decisions, tasks, files modified from the transcript.
 * Writes: vault/memory/YYYY-MM-DD/<agent>-session-<time>.md
 */

import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const PLUGIN_DIR =
  process.env.OPENCLAW_PLUGIN_DIR ||
  join(process.env.HOME ?? "", ".openclaw", "extensions", "engram");

function extractAgentName(sessionKey: string): string {
  // Session keys look like "agent:main:main" or "agent:wren:webchat"
  if (!sessionKey) return "unknown";
  const parts = sessionKey.split(":");
  if (parts.length >= 2) {
    return parts[1] || "main";
  }
  return "main";
}

function extractSessionContent(event: any): {
  messages: string[];
  agentName: string;
  sessionId: string;
  channel: string;
} {
  const ctx = event.context || {};
  const sessionKey = event.sessionKey || "";
  const agentName = extractAgentName(sessionKey);
  const channel = ctx.commandSource || "";

  // Try to get the session entry (pre-reset version for reset events)
  const entry = ctx.previousSessionEntry || ctx.sessionEntry;
  let messages: string[] = [];

  if (entry?.messages) {
    // Extract the last 30 user/assistant messages
    const relevant = entry.messages
      .filter((m: any) => m.role === "user" || m.role === "assistant")
      .slice(-30);

    messages = relevant.map((m: any) => {
      const role = m.role === "user" ? "user" : "assistant";
      const content =
        typeof m.content === "string"
          ? m.content
          : Array.isArray(m.content)
            ? m.content
                .filter((c: any) => c.type === "text")
                .map((c: any) => c.text)
                .join("\n")
            : "";
      // Truncate very long messages
      const trimmed = content.length > 500 ? content.substring(0, 500) + "..." : content;
      return `${role}: ${trimmed}`;
    });
  }

  return {
    messages,
    agentName,
    sessionId: entry?.sessionId || "",
    channel,
  };
}

function analyzeTranscript(messages: string[]): {
  summary: string;
  keyDecisions: string[];
  tasksCompleted: string[];
  tasksPending: string[];
  filesModified: string[];
} {
  const summary_parts: string[] = [];
  const decisions: string[] = [];
  const completed: string[] = [];
  const pending: string[] = [];
  const files: string[] = [];

  // Simple heuristic extraction from the transcript
  const fullText = messages.join("\n");

  // Extract decisions (lines with "decided", "decision", "agreed", "chose", "will use")
  const decisionPatterns = /(?:decided|decision|agreed|chose|will use|going with|settled on|approach:)\s*(.{10,100})/gi;
  let match;
  while ((match = decisionPatterns.exec(fullText)) !== null) {
    const d = match[1].trim().replace(/[.\n].*/, "");
    if (d.length > 10) decisions.push(d);
  }

  // Extract completed tasks (lines with ✅, "done", "completed", "finished", "shipped", "merged")
  const completedPatterns = /(?:✅|done|completed|finished|shipped|merged|fixed|built|created|added)[\s:]+(.{10,100})/gi;
  while ((match = completedPatterns.exec(fullText)) !== null) {
    const t = match[1].trim().replace(/[.\n].*/, "");
    if (t.length > 10) completed.push(t);
  }

  // Extract pending tasks (lines with "TODO", "still need", "next:", "pending", "remaining")
  const pendingPatterns = /(?:TODO|still need|next:|pending|remaining|blocked on|waiting for)[\s:]+(.{10,100})/gi;
  while ((match = pendingPatterns.exec(fullText)) !== null) {
    const t = match[1].trim().replace(/[.\n].*/, "");
    if (t.length > 10) pending.push(t);
  }

  // Extract file paths mentioned
  const filePatterns = /(?:created|modified|edited|wrote|updated|deleted)\s+[`"]?([\/~][\w\/.@-]+\.\w+)[`"]?/gi;
  while ((match = filePatterns.exec(fullText)) !== null) {
    files.push(match[1]);
  }

  // Build summary from last few assistant messages
  const assistantMsgs = messages
    .filter((m) => m.startsWith("assistant:"))
    .slice(-3)
    .map((m) => m.replace("assistant: ", "").substring(0, 150));

  const summaryText = assistantMsgs.length > 0
    ? assistantMsgs.join(" ").substring(0, 300)
    : "Session ended with no extractable summary.";

  return {
    summary: summaryText,
    keyDecisions: [...new Set(decisions)].slice(0, 5),
    tasksCompleted: [...new Set(completed)].slice(0, 10),
    tasksPending: [...new Set(pending)].slice(0, 5),
    filesModified: [...new Set(files)].slice(0, 15),
  };
}

const handler = async (event: any) => {
  // Only trigger on new/reset commands
  if (event.type !== "command") return;
  if (event.action !== "new" && event.action !== "reset") return;

  try {
    const { messages, agentName, sessionId, channel } = extractSessionContent(event);

    if (messages.length === 0) {
      // No transcript to capture
      return;
    }

    const analysis = analyzeTranscript(messages);

    // Call the Python session writer
    const payload = JSON.stringify({
      agent_name: agentName,
      session_id: sessionId,
      summary: analysis.summary,
      key_decisions: analysis.keyDecisions,
      tasks_completed: analysis.tasksCompleted,
      tasks_pending: analysis.tasksPending,
      files_modified: analysis.filesModified,
      channel: channel,
      conversation_excerpt: messages.slice(-5).join("\n"),
    });

    const result = execFileSync(
      "python3",
      [
        "-c",
        `
import json, sys, os
sys.path.insert(0, os.path.join("${PLUGIN_DIR}", "lib"))
from session_writer import write_session_memory
params = json.loads(sys.stdin.read())
result = write_session_memory(**params)
print(json.dumps(result))
`,
      ],
      {
        input: payload,
        encoding: "utf-8",
        timeout: 10_000,
        env: { ...process.env, OPENCLAW_PLUGIN_DIR: PLUGIN_DIR },
      },
    );

    const parsed = JSON.parse(result.trim());
    console.log(
      `[engram] Session captured: ${parsed.session_path} (${parsed.agent})`
    );

    // Notify the user
    event.messages.push(
      `🧠 Session memory saved to ${parsed.session_path}`
    );
  } catch (err: any) {
    console.error(`[engram] Session capture failed: ${err.message}`);
    // Don't block the command on failure
  }
};

export default handler;
