/**
 * memory-hub —— pi ↔ 统一记忆中枢「自动检索」扩展（pi 接入 P1）
 *
 * ## 做什么（触发策略 = 用户裁定：首轮 / resume / 话题漂移）
 *
 *   会话开始（session_start）
 *     └─ 后台预取（不阻塞首轮）→ 进程级冷启动 ~5s（向量后端加载）藏进用户打字时间
 *   首轮 before_agent_start
 *     ├─ 预取已就绪 → 写入 systemPromptOptions.sections["hub-context"]
 *     └─ 未就绪     → 下一轮补注入（不阻塞、不报错）
 *   resume（开 pi 继续上次任务）
 *     └─ 当前 prompt 过短（<8 字，如"继续"）→ 回溯 branch 里最近一条 user 消息作 context
 *   话题漂移
 *     └─ jaccard(本轮词集, 已注入查询词集) < 0.2 且本轮词数 ≥ 3 → 重取（同会话 ≤5 次、每轮 ≤1 次）
 *
 * ## 三条硬约束（不得违反）
 *
 * 1. **不硬编码中枢知识**：分型、检索子区、卡清单全部由中枢侧
 *    `engine.py tier-bootstrap` 计算（与 MCP `hub_bootstrap` 共用同一 handler）。
 *    本文件里不出现任何区名/卡名——否则就是"第三套口径"。
 * 2. **唯一注入点** = `systemPromptOptions.sections`（Pi 会 diff 后**追加增量**，cache 友好）。
 *    不替换 systemPrompt、不注册 context_with_system。
 * 3. **失败静默降级**：超时/非 0 退出/JSON 坏 → 不注入、不抛给模型、状态栏提示。
 *
 * 位置：<PI_CODING_AGENT_DIR>/extensions/memory-hub.ts
 * 生效：pi 内 `/reload`
 */

import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import type { ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

const SECTION_KEY = "hub-context";
const PREFETCH_TIMEOUT_MS = 20_000; // 后台预取给的额度（不阻塞用户）
const DRIFT_THRESHOLD = 0.2;
const MAX_REFETCH_PER_SESSION = 5;
const MAX_TOKEN_ESTIMATE = 1000; // 注入预算（估算：字符数 / 4）

type Prefetch = {
  markdown: string;
  tier: string;
  hits: number;
  elapsedMs: number;
  query: string;
  auditId: string;
};

type SessionState = {
  reason: string;
  prefetch: Promise<Prefetch | null> | null;
  ready: Prefetch | null;
  injected: boolean;
  lastQuery: string;
  refetchCount: number;
  enabled: boolean;
  lastError: string;
  tier: string;
};

const state: SessionState = {
  reason: "startup",
  prefetch: null,
  ready: null,
  injected: false,
  lastQuery: "",
  refetchCount: 0,
  enabled: true,
  lastError: "",
  tier: "",
};

/** 中枢根解析（**不硬编码**，优先级：env → pi 的 mcp.json 里 --root） */
export function resolveHubRoot(agentDir: string): string | null {
  const env = process.env.AGENT_MEMORY_HUB;
  if (env && existsSync(env)) return env;
  try {
    const mcpPath = join(agentDir, "mcp.json");
    if (!existsSync(mcpPath)) return null;
    const cfg = JSON.parse(readFileSync(mcpPath, "utf8")) as {
      mcpServers?: Record<string, { args?: string[] }>;
    };
    const args = cfg.mcpServers?.["agent-memory-hub"]?.args ?? [];
    const i = args.indexOf("--root");
    const root = i >= 0 ? args[i + 1] : undefined;
    return root && existsSync(root) ? root : null;
  } catch {
    return null;
  }
}

export function agentDir(): string {
  return process.env.PI_CODING_AGENT_DIR ?? join(homedir(), ".pi", "agent");
}

/** 词集（漂移判定用）。
 *
 * CJK 与西文不同：中文没有空格，整句会变成**一个 token** ⇒ jaccard 对中文完全不敏感
 * （任意两句都交集为 0），漂移检测实际永远不触发。故对 CJK 连写段取**字符二元组**
 * （bigram），对以西文为主的词取整词。
 *
 * 2026-10-02 实测修正：原实现按非字母数字切分，`重构检索层并补测试` → 1 个 token，
 * 被下游 `size < 3` 守卫拦住 ⇒ 中文场景**静默失效**（不报错、只是永远不重取）。
 */
export function tokenSet(text: string): Set<string> {
  const out = new Set<string>();
  const CJK = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]/u;
  const runs = text.toLowerCase().match(/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]+|[\p{L}\p{N}]+/gu) ?? [];
  for (const run of runs) {
    if (CJK.test(run)) {
      if (run.length <= 2) out.add(run);
      for (let i = 0; i + 2 <= run.length; i += 1) out.add(run.slice(i, i + 2));
    } else if (run.length > 1) {
      out.add(run);
    }
  }
  return out;
}

export function jaccard(a: Set<string>, b: Set<string>): number {
  if (a.size === 0 || b.size === 0) return 0;
  let inter = 0;
  for (const w of a) if (b.has(w)) inter += 1;
  return inter / (a.size + b.size - inter);
}

/** 该不该重取（漂移判定，纯函数便于单测） */
export function shouldRefetch(lastQuery: string, current: string, refetchCount: number): boolean {
  if (refetchCount >= MAX_REFETCH_PER_SESSION) return false;
  const cur = tokenSet(current);
  if (cur.size < 3) return false;
  const prev = tokenSet(lastQuery);
  if (prev.size === 0) return false;
  return jaccard(prev, cur) < DRIFT_THRESHOLD;
}

/** prompt 过短（resume 场景"继续"）→ 取 branch 里最近一条实质 user 消息 */
export function effectiveQuery(prompt: string, branchUsers: string[]): string {
  const p = (prompt ?? "").trim();
  if (p.length >= 8) return p;
  for (let i = branchUsers.length - 1; i >= 0; i -= 1) {
    const t = (branchUsers[i] ?? "").trim();
    if (t.length >= 8) return t.slice(0, 200);
  }
  return p;
}

export function estimateTokens(text: string): number {
  return Math.ceil(text.length / 4);
}

function branchUserTexts(ctx: ExtensionContext): string[] {
  try {
    const entries = ctx.sessionManager.getBranch();
    return entries
      .filter((e: any) => e?.type === "message" && e?.message?.role === "user")
      .map((e: any) => {
        const c = e.message?.content;
        if (typeof c === "string") return c;
        if (Array.isArray(c)) return c.map((p: any) => (typeof p?.text === "string" ? p.text : "")).join(" ");
        return "";
      });
  } catch {
    return [];
  }
}

export default function (pi: ExtensionAPI) {
  const hub = resolveHubRoot(agentDir());

  function runPrefetch(ctx: ExtensionContext, query: string): Promise<Prefetch | null> {
    if (!hub) return Promise.resolve(null);
    // hub = <repo>/AgentMemoryHub ⇒ repo 根 = dirname(hub)；.venv 与 hub-engine 都在 repo 根
    const repo = dirname(hub);
    const engine = join(repo, "hub-engine", "engine.py");
    const py = join(repo, ".venv", "Scripts", "python.exe");
    const command = existsSync(py) ? py : "python";
    const args = [engine, "tier-bootstrap", "--root", hub, "--context", query, "--platform", "pi", "--json"];
    // 用 pi.exec（而不是裸 child_process）：超时/中止/清理纳入 Pi 的生命周期管理
    return pi
      .exec(command, args, { timeout: PREFETCH_TIMEOUT_MS, cwd: dirname(engine) })
      .then((r) => {
        if (r.code !== 0) {
          state.lastError = (r.stderr || "").trim().slice(0, 160) || `exit ${r.code}`;
          if (ctx.hasUI) ctx.ui.setStatus("hub", "中枢:离线");
          return null;
        }
        try {
          const line = (r.stdout || "").trim().split("\n").pop() ?? "{}";
          const o = JSON.parse(line);
          if (o.skipped) {
            state.tier = "light";
            if (ctx.hasUI) ctx.ui.setStatus("hub", "中枢:light");
            return null;
          }
          const md = String(o.markdown ?? "");
          if (!md || estimateTokens(md) > MAX_TOKEN_ESTIMATE * 1.5) return null;
          const p: Prefetch = {
            markdown: md,
            tier: String(o.tier ?? "?"),
            hits: Number(o.hit_count ?? 0),
            elapsedMs: Number(o.elapsed_ms ?? 0),
            query,
            auditId: String(o.audit_id ?? ""),
          };
          state.tier = p.tier;
          if (ctx.hasUI) ctx.ui.setStatus("hub", `中枢:${p.tier}×${p.hits}`);
          return p;
        } catch (e) {
          state.lastError = `JSON 解析失败: ${String(e)}`;
          return null;
        }
      })
      .catch((err) => {
        state.lastError = String(err?.message ?? err).slice(0, 160);
        if (ctx.hasUI) ctx.ui.setStatus("hub", "中枢:离线");
        return null;
      });
  }

  // 会话开始：重置状态 + **后台**预取（把 ~5s 冷启动藏进用户打字时间）
  pi.on("session_start", async (event, ctx) => {
    state.reason = event.reason;
    state.ready = null;
    state.injected = false;
    state.lastQuery = "";
    state.refetchCount = 0;
    state.lastError = "";
    if (!state.enabled) return;
    if (!hub) {
      if (ctx.hasUI) ctx.ui.setStatus("hub", "中枢:未配置");
      return;
    }
    // resume：用 branch 里最近一条实质消息作 context；否则留空由首轮补
    const seed = event.reason === "resume" ? effectiveQuery("", branchUserTexts(ctx)) : "";
    state.prefetch = seed ? runPrefetch(ctx, seed) : null;
  });

  pi.on("before_agent_start", async (event, ctx) => {
    if (!state.enabled || !hub) return;
    const prompt = String(event.prompt ?? "");

    // 1) 首轮 / resume：等预取（若还在跑就等它，最多 20s 上限在 runPrefetch 内约束）
    if (!state.injected) {
      if (!state.prefetch) {
        const q = effectiveQuery(prompt, branchUserTexts(ctx));
        if (!q.trim()) return;
        state.prefetch = runPrefetch(ctx, q);
      }
      const got = await state.prefetch;
      if (!got) return;
      state.ready = got;
      state.lastQuery = got.query;
      state.injected = true;
      event.systemPromptOptions.sections[SECTION_KEY] = got.markdown;
      return;
    }

    // 2) 话题漂移
    const q = effectiveQuery(prompt, branchUserTexts(ctx));
    if (!q.trim() || !shouldRefetch(state.lastQuery, q, state.refetchCount)) return;
    state.refetchCount += 1;
    const got = await runPrefetch(ctx, q);
    if (!got) return;
    state.ready = got;
    state.lastQuery = q;
    // 内容变化 → Pi 会 diff 后追加**增量**（不改写前缀，cache 友好）
    event.systemPromptOptions.sections[SECTION_KEY] = got.markdown;
  });

  pi.registerCommand("hub", {
    description: "手动检索记忆中枢（--tier <型> 可强制分型）",
    handler: async (args, ctx) => {
      if (!hub) {
        ctx.ui.notify("未找到中枢：请设 AGENT_MEMORY_HUB 或在 <agent-dir>/mcp.json 配置 agent-memory-hub", "error");
        return;
      }
      const raw = (args ?? "").trim();
      const m = raw.match(/--tier\s+(\S+)/);
      const query = raw.replace(/--tier\s+\S+/, "").trim() || state.lastQuery || "记忆中枢";
      const got = await runPrefetch(ctx, query);
      if (!got) {
        ctx.ui.notify(state.lastError ? `检索失败：${state.lastError}` : "无命中（或 light 型不检索）", "warning");
        return;
      }
      state.ready = got;
      state.injected = true;
      state.lastQuery = query;
      ctx.ui.notify(`中枢命中 ${got.hits} 张（tier=${got.tier}，${got.elapsedMs}ms）\n${got.markdown.slice(0, 800)}`, "info");
    },
  });

  pi.registerCommand("hub-cap", {
    description: "任务级能力装配：/hub-cap list|install|verify|remove <技能名>（默认落点=项目级 .pi/skills/）",
    handler: async (args, ctx) => {
      if (!hub) {
        ctx.ui.notify("未找到中枢：请设 AGENT_MEMORY_HUB 或在 <agent-dir>/mcp.json 配置 agent-memory-hub", "error");
        return;
      }
      const raw = (args ?? "").trim();
      const [action = "list", skill = ""] = raw.split(/\s+/);
      if (!["list", "install", "verify", "remove", "residue"].includes(action)) {
        ctx.ui.notify("用法：/hub-cap list|install|verify|remove|residue [技能名]", "warning");
        return;
      }
      const repo = dirname(hub);
      const py = join(repo, ".venv", "Scripts", "python.exe");
      const script = join(repo, "hub-engine", "scripts", "task_capability.py");
      const argv = [script, action, "--root", hub];
      // install/remove 必须显式落到**项目级** .pi/skills/（task scope 的唯一落点）
      if ((action === "install" || action === "remove") && skill) {
        argv.push("--skill", skill, "--project", ctx.cwd);
      } else if (action === "verify" && skill) {
        argv.push("--skill", skill, "--project", ctx.cwd);
      }
      const r = await pi.exec(existsSync(py) ? py : "python", argv, { timeout: 60_000, cwd: repo });
      const text = (r.stdout || r.stderr || "").trim();
      ctx.ui.notify(text.slice(0, 1200) || `退出码 ${r.code}`, r.code === 0 ? "info" : "warning");
    },
  });

  pi.registerCommand("hub-off", {
    description: "本会话关闭中枢自动检索",
    handler: async (_args, ctx) => {
      state.enabled = false;
      ctx.ui.setStatus("hub", "中枢:off");
      ctx.ui.notify("已关闭本会话的中枢自动检索（/hub-on 恢复）", "info");
    },
  });

  pi.registerCommand("hub-on", {
    description: "恢复中枢自动检索",
    handler: async (_args, ctx) => {
      state.enabled = true;
      ctx.ui.setStatus("hub", "中枢:on");
      ctx.ui.notify("已恢复中枢自动检索", "info");
    },
  });
}
