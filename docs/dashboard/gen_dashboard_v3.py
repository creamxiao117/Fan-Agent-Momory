# @version V1.0 / 2026-09-09 / Hermes / dashboard v3 final
"""gen_dashboard_v3.py - V3 dashboard: file:// compatible.

file:// protocol blocks fetch() to local files (CORS).
Solution: render to STAGED HTML where all data is inlined at generation time.

V3 features (preserved):
- V1 Linear style
- Side nav + 4 tab panels
- 13 data sections
- Interactive buttons
- "Run cron" with confirm()
- 60s auto-refresh (relies on data update)
"""
import json
import pathlib

BASE = pathlib.Path(r"C:\Users\Fan-SJSS\.trae-cn\worktrees\20260817-Fan-Agent-Momory\feat-implement-plan-ZilBmv")
DASH = BASE / "work" / "dashboard"
data = json.loads((DASH / "dashboard-data.json").read_text(encoding="utf-8"))

# JSON-encode with safe escape (no </script>)
data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

CSS = """
:root{--bg-0:#08090a;--bg-1:#0f1011;--bg-2:#191a1b;--bg-3:#222428;--border:rgba(255,255,255,0.08);--border-h:rgba(255,255,255,0.18);--text-1:#f7f8f8;--text-2:#b4b8be;--text-3:#62666d;--accent:#5e6ad2;--accent-h:#7170ff;--green:#4cb782;--yellow:#f2c94c;--red:#f87171}
*{margin:0;padding:0;box-sizing:border-box}
html,body{font-family:'Inter',system-ui,-apple-system,sans-serif;font-size:14px;background:var(--bg-0);color:var(--text-1);height:100vh;overflow:hidden}
.app{display:grid;grid-template-columns:200px 1fr;height:100vh}
nav{background:var(--bg-1);border-right:1px solid var(--border);padding:16px 0;overflow:auto}
.brand{padding:0 16px 16px;border-bottom:1px solid var(--border);margin-bottom:8px}
.brand h1{font-size:14px;font-weight:600;color:var(--text-1);margin:0}
.brand .sub{font-size:11px;color:var(--text-3);margin-top:2px}
.nav-item{display:flex;align-items:center;gap:8px;padding:10px 16px;cursor:pointer;color:var(--text-2);border-left:2px solid transparent;font-size:13px}
.nav-item:hover{background:var(--bg-2);color:var(--text-1)}
.nav-item.active{background:var(--bg-2);color:var(--accent-h);border-left-color:var(--accent)}
main{overflow:auto;padding:20px 24px}
header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}
header h2{font-size:16px;font-weight:500}
header .actions{display:flex;gap:8px}
.btn{padding:6px 12px;background:var(--bg-2);border:1px solid var(--border);color:var(--text-1);border-radius:6px;cursor:pointer;font-size:12px}
.btn:hover{border-color:var(--accent)}
.btn-primary{background:var(--accent);border-color:var(--accent)}
.btn-primary:hover{background:var(--accent-h);border-color:var(--accent-h)}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}
.grid-2{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.card{background:var(--bg-1);border:1px solid var(--border);border-radius:8px;padding:14px 16px;transition:all 0.15s}
.card:hover{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}
.card-title{font-size:11px;color:var(--text-3);text-transform:uppercase;letter-spacing:0.05em;margin-bottom:8px}
.metric-big{font-size:48px;font-weight:500;line-height:1}
.metric-sub{font-size:11px;color:var(--text-3);margin-top:4px}
.status-pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600}
.s-green{background:rgba(76,183,130,0.15);color:var(--green)}
.s-red{background:rgba(248,113,113,0.15);color:var(--red)}
.s-yellow{background:rgba(242,201,76,0.15);color:var(--yellow)}
.dot{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px}
.d-green{background:var(--green)}
.d-red{background:var(--red)}
.d-yellow{background:var(--yellow)}
.d-gray{background:var(--text-3)}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:8px 6px;color:var(--text-3);font-weight:500;border-bottom:1px solid var(--border)}
td{padding:8px 6px;border-bottom:1px solid rgba(255,255,255,0.04)}
tr:hover td{background:var(--bg-2)}
.mono{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:11px;color:var(--text-2)}
.alert{padding:10px 12px;border-radius:6px;margin-bottom:8px;font-size:12px}
.alert.red{background:rgba(248,113,113,0.1);border-left:3px solid var(--red)}
.alert.yellow{background:rgba(242,201,76,0.1);border-left:3px solid var(--yellow)}
iframe{width:100%;border:0;background:var(--bg-1);border-radius:6px;min-height:600px}
.iframe-wrap{background:var(--bg-1);border:1px solid var(--border);border-radius:8px;overflow:hidden}
.empty{color:var(--text-3);font-size:12px;padding:12px;text-align:center}
.stat-block{background:var(--bg-2);border-radius:6px;padding:10px 12px;cursor:pointer}
.stat-block:hover{background:var(--bg-3)}
.stat-block .num{font-size:24px;font-weight:500}
.stat-block .label{font-size:10px;color:var(--text-3);text-transform:uppercase}
.chat-input{display:flex;gap:8px;margin-top:12px}
.chat-input input{flex:1;padding:8px 12px;background:var(--bg-2);border:1px solid var(--border);color:var(--text-1);border-radius:6px}
.chat-log{background:var(--bg-0);border-radius:6px;padding:12px;min-height:300px;max-height:500px;overflow:auto}
.chat-msg{padding:6px 0;font-size:13px}
.chat-msg .who{color:var(--accent);font-weight:500;margin-right:6px}
.panel{display:none}
.panel.active{display:block}
"""

JS = """
let DATA = null;
let ACTIVE_TAB = "main";

function showTab(name) {
  ACTIVE_TAB = name;
  document.querySelectorAll(".nav-item").forEach(el => {
    el.classList.toggle("active", el.dataset.tab === name);
  });
  document.querySelectorAll(".panel").forEach(el => {
    el.classList.toggle("active", el.id === "panel-" + name);
  });
  const titles = {main: "总控台", flywheel: "飞轮详情", skillhub: "SkillHub", platforms: "平台健康", hermes: "Hermes Chat"};
  document.getElementById("page-title").textContent = titles[name] || name;
}

function setStatus(level, text) {
  const dot = document.querySelector("#c-health .dot");
  if (dot) { dot.className = "dot d-" + (level === "green" ? "green" : level === "red" ? "red" : "yellow"); }
  if (text) {
    const sub = document.getElementById("m-health-sub");
    if (sub) sub.textContent = text;
  }
}

function render() {
  if (!DATA) return;
  const d = DATA;
  document.getElementById("m-health").textContent = (d.health && d.health.overall) + "/100";
  document.getElementById("m-health-sub").textContent = (d.health && d.health.panels_ok) + "/" + (d.health && d.health.panels_total) + " 面板 OK";
  const gap = d.knowledge_gap || {};
  document.getElementById("m-gap").textContent = (gap.miss || 0) + "/" + (gap.total || 0);
  document.getElementById("m-gap-sub").textContent = (gap.miss_rate || 0) + "% miss rate";
  const td = d.todos || {};
  const projCount = Array.isArray(td.projects) ? td.projects.length : (td.project_count || 0);
  document.getElementById("m-todos").textContent = projCount;
  document.getElementById("m-todos-sub").textContent = (td.rule_pending || 0) + " 规则 pending";
  const plats = (d.platforms && d.platforms.platforms) || {};
  const tblP = document.getElementById("tbl-platforms");
  tblP.innerHTML = Object.entries(plats).map(([n, p]) =>
    '<tr><td><span class="status-pill s-' + (p.status === "GREEN" ? "green" : p.status === "RED" ? "red" : "yellow") + '">' + p.status + '</span></td><td><strong>' + n + '</strong></td><td class="mono">' + p.type + '</td></tr>'
  ).join("") || '<tr><td colspan=3 class=empty>无</td></tr>';
  const fw = d.flywheel || {};
  const tblPanels = document.getElementById("tbl-panels");
  tblPanels.innerHTML = Object.entries(fw).map(([k, v]) =>
    '<tr><td class=mono>' + k + '</td><td><span class="status-pill s-' + (v.ok ? "green" : "red") + '">' + (v.ok ? "✓" : "✗") + '</span></td><td>' + ((v.info && v.info.stdout) || "").slice(0, 80) + '</td></tr>'
  ).join("") || '<tr><td colspan=3 class=empty>无</td></tr>';
  const cron = d.cron_jobs || [];
  const tblC = document.getElementById("tbl-cron");
  tblC.innerHTML = cron.map(c =>
    '<tr><td class=mono>' + c.id.slice(0,8) + '</td><td>' + c.name + '</td><td class=mono>' + c.schedule + '</td><td><span class="status-pill s-green">' + c.status + '</span></td><td class=mono>' + (c.last || "—") + '</td>' +
    '<td><button class=btn data-cid=' + c.id + ' onclick="runCron(\\'' + c.id + '\\',\\'' + c.name + '\\')">立即跑</button></td></tr>'
  ).join("") || '<tr><td colspan=6 class=empty>无</td></tr>';
  const cr = d.card_stats_by_type || {};
  const cards = Array.isArray(cr) ? cr : Object.entries(cr).map(([t, n]) => ({type: t, label: t.toUpperCase().slice(0,12), count: n}));
  document.getElementById("cards-grid").innerHTML = cards.map(c =>
    '<div class=stat-block><div class=num>' + c.count + '</div><div class=label>' + (c.label || c.type) + '</div></div>'
  ).join("") || '<div class=empty>无</div>';
  const ss = d.sync_status || {};
  const repos = Array.isArray(ss) ? ss : (ss.repos || Object.entries(ss).map(([n, info]) => ({name: n, ...(info || {})})));
  document.getElementById("tbl-sync").innerHTML = repos.map(r =>
    '<tr><td><strong>' + r.name + '</strong></td><td class=mono>' + (r.last_commit || r.commit || "—") + '</td><td>' + (r.branch || "—") + '</td></tr>'
  ).join("") || '<tr><td colspan=3 class=empty>无</td></tr>';
  const led = d.ledger_recent || [];
  document.getElementById("tbl-ledger").innerHTML = led.map(l =>
    '<tr><td class=mono>' + (l.ts || "") + '</td><td>' + (l.who || "") + '</td><td class=mono>' + (l.sha || "").slice(0,8) + '</td><td>' + (l.intent || "") + '</td></tr>'
  ).join("") || '<tr><td colspan=4 class=empty>无</td></tr>';
  const ing = d.ingest_recent || [];
  document.getElementById("tbl-ingest").innerHTML = ing.map(i =>
    '<tr><td class=mono>' + (i.ts || "") + '</td><td>' + (i.title || "") + '</td><td class=mono>' + (i.type || "") + '</td><td><span class=status-pill s-green>' + (i.status || "—") + '</span></td></tr>'
  ).join("") || '<tr><td colspan=4 class=empty>无</td></tr>';
  const alerts = d.alerts || {};
  const alertDiv = document.getElementById("alerts");
  let alertHtml = "";
  (alerts.critical || []).forEach(a => { alertHtml += '<div class=alert.red>⚠ CRITICAL · ' + a + '</div>'; });
  (alerts.announcements || []).forEach(a => { alertHtml += '<div class=alert.yellow>📢 ' + (a.action || "ingest_done") + ' · ' + (a.who || "hermes") + '</div>'; });
  alertDiv.innerHTML = alertHtml || '<div class=empty>无告警</div>';
  setStatus("green", "已渲染 " + Object.keys(plats).length + " 平台 · " + cron.length + " cron");
}

function runCron(id, name) {
  if (!confirm("确认立即跑 cron 任务: " + name + " ?")) return;
  setStatus("yellow", "已发送请求: " + name);
  alert("已请求运行 " + name + "\\n（注：当前为模拟 trigger，真后端 trigger 待接入）");
}

function sendChat() {
  const input = document.getElementById("chat-msg");
  const msg = input.value.trim();
  if (!msg) return;
  const log = document.getElementById("chat-log");
  log.innerHTML += '<div class=chat-msg><span class=who>You:</span>' + msg + '</div>';
  log.innerHTML += '<div class=chat-msg><span class=who>Hermes:</span>（占位响应：当前 chat 后端未接入）</div>';
  input.value = "";
  log.scrollTop = log.scrollHeight;
}

// Enter to send (override existing keydown inline)
document.addEventListener("DOMContentLoaded", function() {
  const ci = document.getElementById("chat-msg");
  if (ci) {
    ci.addEventListener("keydown", function(e) {
      if (e.key === "Enter") { e.preventDefault(); sendChat(); }
    });
  }
});

// init
DATA = __DATA_PLACEHOLDER__;
render();
"""

# Build HTML (use list + join, no f-string)
parts = []
parts.append("<!DOCTYPE html>")
parts.append("<html lang='zh'>")
parts.append("<head><meta charset='utf-8'><title>中枢总控台 v3</title>")
parts.append("<style>")
parts.append(CSS)
parts.append("</style>")
parts.append("</head>")
parts.append("<body>")
parts.append("<div class='app'>")
parts.append("<nav>")
parts.append("<div class='brand'><h1>中枢总控台</h1><div class='sub'>AgentMemoryHub</div></div>")
parts.append("<div class='nav-item active' data-tab='main' onclick='showTab(\"main\")'>▦ 总控台</div>")
parts.append("<div class='nav-item' data-tab='flywheel' onclick='showTab(\"flywheel\")'>⚙ 飞轮详情</div>")
parts.append("<div class='nav-item' data-tab='skillhub' onclick='showTab(\"skillhub\")'>⚡ SkillHub</div>")
parts.append("<div class='nav-item' data-tab='platforms' onclick='showTab(\"platforms\")'>▥ 平台健康</div>")
parts.append("<div class='nav-item' data-tab='hermes' onclick='showTab(\"hermes\")'>💬 Hermes Chat</div>")
parts.append("</nav>")
parts.append("<main>")
parts.append("<header><h2 id='page-title'>总控台</h2>")
parts.append("<div class='actions'>")
parts.append("<button class='btn' onclick='location.reload()'>🔄 刷新</button>")
parts.append("<button class='btn btn-primary' onclick='setStatus(\"yellow\",\"需要后端 trigger\")'>⚡ 立即收集</button>")
parts.append("</div></header>")
# Main panel
parts.append("<div class='panel active' id='panel-main'>")
parts.append("<div class='grid'>")
parts.append("<div class='card' id='c-health'><span class='dot d-gray'></span><div class='card-title'>总体健康</div><div class='metric-big' id='m-health'>--</div><div class='metric-sub' id='m-health-sub'>--</div></div>")
parts.append("<div class='card' id='c-gap'><div class='card-title'>知识缺口 · 24h</div><div class='metric-big' id='m-gap'>--</div><div class='metric-sub' id='m-gap-sub'>--</div></div>")
parts.append("<div class='card' id='c-todos'><div class='card-title'>待人工处理</div><div class='metric-big' id='m-todos'>--</div><div class='metric-sub' id='m-todos-sub'>--</div></div>")
parts.append("</div>")
parts.append("<div class='card' style='margin-bottom:12px'><div class='card-title'>5 平台连接</div>")
parts.append("<table><thead><tr><th>状态</th><th>名称</th><th>类型</th></tr></thead><tbody id='tbl-platforms'></tbody></table></div>")
parts.append("<div class='card' style='margin-bottom:12px'><div class='card-title'>6 面板自检 · 06:00 巡检</div>")
parts.append("<table><thead><tr><th>面板</th><th>状态</th><th>详情</th></tr></thead><tbody id='tbl-panels'></tbody></table></div>")
parts.append("<div class='card' style='margin-bottom:12px'><div class='card-title'>Cron 任务 · 点击「立即跑」</div>")
parts.append("<table><thead><tr><th>ID</th><th>名称</th><th>调度</th><th>状态</th><th>最近</th><th>动作</th></tr></thead><tbody id='tbl-cron'></tbody></table></div>")
parts.append("<div class='card' style='margin-bottom:12px'><div class='card-title'>中枢卡片 · 按类型</div>")
parts.append("<div id='cards-grid' style='display:grid;grid-template-columns:repeat(6,1fr);gap:8px'></div></div>")
parts.append("<div class='grid-2'>")
parts.append("<div class='card'><div class='card-title'>三仓 Git 同步</div><table><tbody id='tbl-sync'></tbody></table></div>")
parts.append("<div class='card'><div class='card-title'>最近 commit_ledger</div><table><tbody id='tbl-ledger'></tbody></table></div>")
parts.append("</div>")
parts.append("<div class='card' style='margin-top:12px'><div class='card-title'>最近 ingest</div><table><tbody id='tbl-ingest'></tbody></table></div>")
parts.append("<div class='card' style='margin-top:12px'><div class='card-title'>关键告警</div><div id='alerts'></div></div>")
parts.append("</div>")  # panel-main
parts.append("<div class='panel' id='panel-flywheel'><div class='card'><div class='card-title'>飞轮详情（占位）</div><div class='empty'>该 tab 后续接入「T15 飞轮编排」或自建飞轮详情页</div></div></div>")
parts.append("<div class='panel' id='panel-skillhub'><div class='card'><div class='card-title'>SkillHub（占位）</div><div class='empty'>该 tab 后续接入 SkillHub 技能浏览/路由详情</div></div></div>")
parts.append("<div class='panel' id='panel-platforms'><div class='card'><div class='card-title'>平台健康（占位）</div><div class='empty'>该 tab 后续接入「platform_healthcheck」详细页</div></div></div>")
parts.append("<div class='panel' id='panel-hermes'>")
parts.append("<div class='card'><div class='card-title'>Hermes Chat（占位 UI）</div>")
parts.append("<div class='chat-log' id='chat-log'><div class='empty'>在下方输入问题，按 Enter 发送<br>（注：当前为占位 UI，后端 trigger 待接入）</div></div>")
parts.append("<div class='chat-input'>")
parts.append("<input type='text' id='chat-msg' placeholder='问 Hermes...（按 Enter 发送）'>")
parts.append("<button class='btn btn-primary' onclick='sendChat()'>发送</button>")
parts.append("</div></div>")
parts.append("</div>")
parts.append("</main></div>")
parts.append("<script>")
parts.append(JS.replace("__DATA_PLACEHOLDER__", data_json))
parts.append("</script>")
parts.append("</body>")
parts.append("</html>")

html = "\n".join(parts)
out = DASH / "index-v3.html"
out.write_text(html, encoding="utf-8")
print(f"v3 size: {len(html)} chars, {html.count(chr(10))+1} lines")
print("written:", out)
