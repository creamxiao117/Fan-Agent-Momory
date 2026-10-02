/**
 * memory-hub 扩展冒烟（无需模型调用、无需 pi 运行）
 *
 * 用 **pi 自带的 jiti** 加载扩展（与 pi 实际加载扩展同一路径），验证：
 *   1. 语法/类型擦除可通过（`import type` 被正确剥离）
 *   2. 6 个纯函数行为正确（漂移判定三态、resume 回溯、token 估算）
 *   3. 中枢根解析可用（env → `<agent-dir>/mcp.json` 的 `--root`），且 engine.py / python 存在
 *   4. 扩展里**不含**任何中枢知识字面量（口径单一性，R1 判据）
 *
 * 用法：node hub-engine/templates/pi-extensions/smoke.cjs
 * 退出码：0 = 全通过；1 = 有失败
 */

const fs = require("node:fs");
const path = require("node:path");

const PI_PKG = "D:/Program Files (x86)/PiAgent/node_modules/@earendil-works/pi-coding-agent";
const JITI = path.join(PI_PKG, "node_modules/jiti");
const TEMPLATE = path.join(__dirname, "memory-hub.ts");
const AGENT_DIR = process.env.PI_CODING_AGENT_DIR || path.join(process.env.USERPROFILE || "", ".pi", "agent");

const fails = [];
function check(label, cond, detail) {
  console.log(`[${cond ? "PASS" : "FAIL"}] ${label}${detail ? ` :: ${detail}` : ""}`);
  if (!cond) fails.push(label);
}

let mod;
try {
  const { createJiti } = require(JITI);
  mod = createJiti(__filename, { interopDefault: true })(TEMPLATE);
  check("jiti 加载扩展", typeof (mod.default || mod) === "function", TEMPLATE);
} catch (e) {
  check("jiti 加载扩展", false, String(e && e.message));
  console.log("\n=== 冒烟结果：FAIL（加载失败，后续检查跳过）===");
  process.exit(1);
}

// 2) 纯函数
const s1 = mod.tokenSet("重构检索层并补测试");
// CJK 取字符二元组：9 字句 → 8 个 bigram（若退回"整句一个 token"，中文漂移检测会静默失效）
check("tokenSet 切分（CJK bigram）", s1.size >= 3, `size=${s1.size} ${[...s1].slice(0, 3).join("/")}...`);
check("中文漂移可检出", mod.jaccard(s1, mod.tokenSet("画个CAD图层批量重命名")) < 0.2);
check("中文同题不误报", mod.jaccard(s1, mod.tokenSet("重构检索层并补测试用例")) >= 0.5);
check("jaccard 同集=1", mod.jaccard(s1, mod.tokenSet("重构检索层并补测试")) === 1);
check("jaccard 异集=0", mod.jaccard(s1, mod.tokenSet("画个CAD图层批量重命名")) === 0);
check("漂移→重取", mod.shouldRefetch("重构检索层并补测试", "画个 CAD 图层批量重命名", 0) === true);
check("同题→不重取", mod.shouldRefetch("重构检索层并补测试", "重构检索层补测试用例", 0) === false);
check("超上限→不重取", mod.shouldRefetch("a b c d e", "x y z w v", 5) === false);
check(
  "resume 短 prompt→回溯",
  mod.effectiveQuery("继续", ["", "把 memory hub 的检索层重构完"]) === "把 memory hub 的检索层重构完",
);
check("token 估算", mod.estimateTokens("x".repeat(400)) === 100);

// 3) 中枢根解析
const hub = mod.resolveHubRoot(AGENT_DIR);
check("中枢根可解析", !!hub, `agentDir=${AGENT_DIR} hub=${hub}`);
if (hub) {
  const repo = path.dirname(hub);
  check("engine.py 存在", fs.existsSync(path.join(repo, "hub-engine", "engine.py")));
  check("venv python 存在", fs.existsSync(path.join(repo, ".venv", "Scripts", "python.exe")));
}

// 4) 口径单一性：不得出现中枢知识字面量
const src = fs.readFileSync(TEMPLATE, "utf8");
const knowledge = ["\"rules\"", "\"methodology\"", "\"blueprints\"", "\"experience\"", "\"longterm\""];
const hit = knowledge.filter((k) => src.includes(k));
check("无中枢知识字面量（R1）", hit.length === 0, hit.join(","));

console.log(`\n=== 冒烟结果：${fails.length === 0 ? "PASS" : "FAIL"}（失败 ${fails.length} 项）===`);
process.exit(fails.length === 0 ? 0 : 1);
