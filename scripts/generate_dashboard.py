#!/usr/bin/env python3
"""
记忆系统仪表板生成器。
生成自包含 HTML，数据在生成时嵌入（无需网络请求）。
用法: python3 generate_dashboard.py
输出: ~/桌面/memory-dashboard.html
"""

import json, os, datetime, re
from pathlib import Path

MEMORY_DIR = os.path.expanduser("~/.claude/projects/-home-lxk/memory")
OUTPUT_PATH = os.path.expanduser("~/桌面/memory-dashboard.html")
HERE = Path(__file__).parent

TEMPLATE_PATH = HERE / "_dashboard_template.html"


def load_json(path):
    try: return json.loads(Path(path).read_text())
    except: return {}


def load_jsonl(path):
    try:
        lines = Path(path).read_text().strip().split("\n")
        return [json.loads(l) for l in lines if l.strip()]
    except: return []


def count_memories():
    import re as rx
    mem_dir = Path(MEMORY_DIR)
    total = active = dormant = critical = 0
    memories = []

    for fpath in sorted(mem_dir.glob("*.md")):
        if fpath.name == "MEMORY.md":
            continue
        content = fpath.read_text(encoding="utf-8")
        if not content.startswith("---"):
            continue
        total += 1

        def g(p, d=""):
            m = rx.search(p, content)
            return m.group(1).strip() if m else d

        def gf(p, d=0.5):
            m = rx.search(p, content)
            return float(m.group(1)) if m else d

        retention = gf(r'retention_strength:\s*([\d.]+)', 0.5)
        access = int(gf(r'access_count:\s*(\d+)', 0))
        consolidation = gf(r'consolidation_level:\s*([\d.]+)', 0.3)
        display_name = g(r'name:\s*(.+)', fpath.stem)
        mem_type = g(r'type:\s*(.+)', "unknown")
        desc = g(r'description:\s*(.+)', "")[:80]

        if retention >= 0.8:
            classification, active = "active", active + 1
        elif retention >= 0.4:
            classification, dormant = "dormant", dormant + 1
        else:
            classification, critical = "critical", critical + 1

        memories.append(dict(name=display_name, retention=round(retention, 3),
                             access=access, consolidation=consolidation,
                             type=mem_type, classification=classification, desc=desc))

    return dict(total=total, active=active, dormant=dormant,
                critical=critical, memories=memories)


def js_str(obj):
    """JSON with single quotes for JS safety"""
    return json.dumps(obj, ensure_ascii=False)


def generate(mem, config, pid_state, history):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>记忆系统控制面板</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f1117;color:#e1e2e8;padding:24px;max-width:1200px;margin:0 auto}
h1{font-size:24px;margin-bottom:4px;display:flex;align-items:center;gap:12px}
h1 small{font-size:14px;color:#7a7b85;font-weight:normal}
#sub{color:#7a7b85;font-size:13px;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin-bottom:20px}
.card{background:#1a1b23;border:1px solid #2a2b35;border-radius:12px;padding:20px}
.card h3{font-size:12px;color:#7a7b85;text-transform:uppercase;letter-spacing:.5px;margin-bottom:10px}
.stat-num{font-size:32px;font-weight:700}
.big{font-size:26px}
.row{display:flex;justify-content:space-between;padding:4px 0;font-size:14px}
.dim{color:#7a7b85}
code{font-family:'JetBrains Mono','SF Mono',monospace;font-size:13px;background:#2a2b35;padding:1px 6px;border-radius:4px}
.bar{display:flex;height:28px;border-radius:8px;overflow:hidden;margin-bottom:12px}
.ba{background:#4ade80;transition:width .5s}
.bd{background:#facc15;transition:width .5s}
.bc{background:#f87171;transition:width .5s}
.badge{display:inline-block;padding:1px 8px;border-radius:99px;font-size:11px;font-weight:600}
.ba-b{background:rgba(74,222,128,.15);color:#4ade80}
.bd-b{background:rgba(250,204,21,.15);color:#facc15}
.bc-b{background:rgba(248,113,113,.15);color:#f87171}
.chart-box{background:#1a1b23;border:1px solid #2a2b35;border-radius:12px;padding:20px;margin-bottom:16px}
.chart-box h3{font-size:12px;color:#7a7b85;text-transform:uppercase;letter-spacing:.5px;margin-bottom:12px}
svg{width:100%;height:auto;display:block}
.section-title{font-size:16px;font-weight:600;margin:20px 0 12px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #2a2b35;font-variant-numeric:tabular-nums}
th{color:#7a7b85;font-weight:500;font-size:11px;text-transform:uppercase;letter-spacing:.5px}
@media(max-width:600px){body{padding:12px}.grid{grid-template-columns:1fr}.stat-num{font-size:24px}}
</style></head><body>
<h1>&#x1F9E0; 记忆系统 <small>工程控制论 &middot; 自调节记忆</small></h1>
<div id="sub">生成本地时间: __NOW__ &middot; 遗忘控制器 + PID 调参器</div>

<div class="grid" id="cards"></div>
<div class="grid">
  <div class="card"><h3>&#x1F4CA; 记忆分布</h3><div class="bar" id="dist-bar"></div><div id="dist-text"></div></div>
  <div class="card"><h3>&#x2699;&#xFE0F; 控制参数</h3><div id="params"></div></div>
</div>

<div class="chart-box"><h3>&#x1F4C8; PID 参数历史</h3><svg id="pid-chart" viewBox="0 0 700 220"></svg></div>
<div class="chart-box"><h3>&#x1F4CA; 记忆分类历史</h3><svg id="class-chart" viewBox="0 0 700 220"></svg></div>

<div class="section-title">&#x1F4CB; 记忆清单</div>
<table><thead><tr><th>记忆</th><th>类型</th><th>保留</th><th>巩固</th><th>访问</th><th>状态</th></tr></thead><tbody id="mem-tbody"></tbody></table>

<div class="section-title">调节历史</div>
<table><thead><tr><th>#</th><th>遗忘率</th><th>活跃门限</th><th>访问脉冲</th><th>活跃%</th><th>休眠%</th></tr></thead><tbody id="hist-tbody"></tbody></table>

<script>
const MEM = __MEM__;
const CFG = __CFG__;
const PID = __PID__;
const HIST = __HIST__;

function render() {
  const t = MEM.total||1, a = MEM.active||0, d = MEM.dormant||0, c = MEM.critical||0;
  const ar = (a/t*100).toFixed(0), dr = (d/t*100).toFixed(0), cr = (c/t*100).toFixed(0);
  const hlth = PID.iteration>=5?'&#x2705; 稳定':PID.iteration>=3?'&#x1F504; 收敛中':PID.iteration>0?'&#x2699;&#xFE0F; 初始化':'&#x2B1C; 空';
  document.getElementById('cards').innerHTML =
    `<div class="card"><h3>记忆总数</h3><div class="stat-num">${t}</div></div>` +
    `<div class="card"><h3>系统健康</h3><div class="stat-num big">${hlth}</div></div>` +
    `<div class="card"><h3>PID 迭代</h3><div class="stat-num">${PID.iteration||0}</div></div>` +
    `<div class="card"><h3>遗忘率</h3><div class="stat-num big">${(CFG.base_forget_rate||0).toFixed(4)}</div></div>`;

  document.getElementById('dist-bar').innerHTML =
    `<div class="ba" style="width:${ar}%"></div><div class="bd" style="width:${dr}%"></div><div class="bc" style="width:${cr}%"></div>`;
  document.getElementById('dist-text').innerHTML =
    `<div class="row"><span><span class="badge ba-b">活跃</span> ${a}条</span><span>${ar}%</span></div>` +
    `<div class="row"><span><span class="badge bd-b">休眠</span> ${d}条</span><span>${dr}%</span></div>` +
    `<div class="row"><span><span class="badge bc-b">低价值</span> ${c}条</span><span>${cr}%</span></div>`;

  document.getElementById('params').innerHTML =
    ['base_forget_rate','theta_vital','theta_dormant','theta_purge','access_boost','recency_halflife_days'].map(k =>
      `<div class="row"><span class="dim">${k}</span><span><code>${CFG[k]!=null?CFG[k]:'&mdash;'}</code></span></div>`
    ).join('');

  document.getElementById('mem-tbody').innerHTML = (MEM.memories||[]).map(m =>
    `<tr><td><strong>${m.name}</strong><br><span class="dim" style="font-size:11px">${m.desc}</span></td>`+
    `<td><span class="dim">${m.type}</span></td>`+
    `<td><code>${m.retention.toFixed(3)}</code></td>`+
    `<td>${(m.consolidation*100).toFixed(0)}%</td>`+
    `<td>${m.access}</td>`+
    `<td><span class="badge ${m.classification}-b">${m.classification}</span></td></tr>`
  ).join('');

  pidChart(); classChart(); histTable();
}

function pidChart() {
  const pts = HIST.filter(e => e.action?.base_forget_rate?.new != null);
  if (pts.length<2) { document.getElementById('pid-chart').innerHTML='<text x="350" y="110" text-anchor="middle" fill="#7a7b85" font-size="14">等待至少 2 个数据点</text>'; return; }
  const W=700,H=220,PT=25,PR=20,PB=35,PL=55,CW=W-PL-PR,CH=H-PT-PB;
  const frLo = Math.min(...pts.map(e=>e.action.base_forget_rate.new))*0.8;
  const frHi = Math.max(...pts.map(e=>e.action.base_forget_rate.new))*1.2;
  const tvLo = Math.min(...pts.map(e=>e.action.theta_vital.new||0.8))*0.95;
  const tvHi = Math.max(...pts.map(e=>e.action.theta_vital.new||0.8))*1.05;
  const fx = i => PL+(i/(pts.length-1))*CW;
  const fy = (v,lo,hi) => PT+CH-((v-lo)/(hi-lo))*CH;
  const frD = pts.map((e,i)=>(i?'L':'M')+fx(i)+','+fy(e.action.base_forget_rate.new,frLo,frHi)).join(' ');
  const tvD = pts.map((e,i)=>(i?'L':'M')+fx(i)+','+fy(e.action.theta_vital.new||0.8,tvLo,tvHi)).join(' ');
  document.getElementById('pid-chart').innerHTML =
    '<line x1="'+PL+'" y1="'+PT+'" x2="'+PL+'" y2="'+(H-PB)+'" stroke="#2a2b35" stroke-width="1"/>'+
    '<line x1="'+PL+'" y1="'+(H-PB)+'" x2="'+(W-PR)+'" y2="'+(H-PB)+'" stroke="#2a2b35" stroke-width="1"/>'+
    [0.25,0.5,0.75].map(p=>'<line x1="'+PL+'" y1="'+(PT+CH*(1-p))+'" x2="'+(W-PR)+'" y2="'+(PT+CH*(1-p))+'" stroke="#1a1b23" stroke-width="1"/>').join('')+
    '<path d="'+frD+'" fill="none" stroke="#f87171" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>'+
    '<path d="'+tvD+'" fill="none" stroke="#22d3ee" stroke-width="2" stroke-linejoin="round" stroke-dasharray="6,3"/>'+
    pts.map((e,i)=>'<circle cx="'+fx(i)+'" cy="'+fy(e.action.base_forget_rate.new,frLo,frHi)+'" r="3.5" fill="#f87171" stroke="#0f1117" stroke-width="1.5"/>').join('')+
    pts.map((e,i)=>'<circle cx="'+fx(i)+'" cy="'+fy(e.action.theta_vital.new||0.8,tvLo,tvHi)+'" r="3.5" fill="#22d3ee" stroke="#0f1117" stroke-width="1.5"/>').join('')+
    '<text x="'+(W-PR-4)+'" y="'+fy(frLo+(frHi-frLo)*0.2,frLo,frHi)+'" fill="#f87171" font-size="12" text-anchor="end">遗忘率</text>'+
    '<text x="'+(W-PR-4)+'" y="'+fy(tvLo+(tvHi-tvLo)*0.8,tvLo,tvHi)+'" fill="#22d3ee" font-size="12" text-anchor="end">活跃门限</text>'+
    '<text x="'+PL+'" y="'+(H-5)+'" fill="#7a7b85" font-size="11">→ PID 迭代次数</text>';
}

function classChart() {
  const pts = HIST.filter(e => e.observed?.active_ratio != null);
  if (pts.length<2) { document.getElementById('class-chart').innerHTML='<text x="350" y="110" text-anchor="middle" fill="#7a7b85" font-size="14">等待至少 2 个数据点</text>'; return; }
  const W=700,H=220,PT=25,PR=20,PB=35,PL=55,CW=W-PL-PR,CH=H-pt-pb;
  const fx = i => PL+(i/(pts.length-1))*CW;
  function pathFor(getY) {
    const d = pts.map((e,i)=>(i?'L':'M')+fx(i)+','+(PT+CH*(1-getY(e)))).join(' ');
    return d+'L'+fx(pts.length-1)+','+(PT+CH)+'L'+fx(0)+','+(PT+CH)+'Z';
  }
  const actD = pathFor(e => e.observed.active_ratio);
  const dorD = pathFor(e => e.observed.active_ratio + e.observed.dormant_ratio);
  document.getElementById('class-chart').innerHTML =
    '<line x1="'+PL+'" y1="'+PT+'" x2="'+PL+'" y2="'+(H-PB)+'" stroke="#2a2b35" stroke-width="1"/>'+
    '<line x1="'+PL+'" y1="'+(H-PB)+'" x2="'+(W-PR)+'" y2="'+(H-PB)+'" stroke="#2a2b35" stroke-width="1"/>'+
    [0.25,0.5,0.75].map(p=>'<line x1="'+PL+'" y1="'+(PT+CH*(1-p))+'" x2="'+(W-PR)+'" y2="'+(PT+CH*(1-p))+'" stroke="#1a1b23" stroke-width="1"/>').join('')+
    '<path d="'+actD+'" fill="rgba(74,222,128,0.35)" stroke="#4ade80" stroke-width="1.5"/>'+
    '<path d="'+dorD+'" fill="rgba(250,204,21,0.25)" stroke="#facc15" stroke-width="1.5"/>'+
    '<text x="'+(W-PR-4)+'" y="'+(PT+8)+'" fill="#4ade80" font-size="12" text-anchor="end">活跃</text>'+
    '<text x="'+(W-PR-4)+'" y="'+(PT+24)+'" fill="#facc15" font-size="12" text-anchor="end">休眠</text>'+
    '<text x="'+PL+'" y="'+(H-5)+'" fill="#7a7b85" font-size="11">→ PID 迭代次数</text>';
}

function histTable() {
  document.getElementById('hist-tbody').innerHTML = HIST.slice().reverse().map(function(e) {
    const a = e.action||{}, o = e.observed||{};
    return '<tr><td>'+(e.iteration||'?')+'</td><td><code>'+(a.base_forget_rate?.new?.toFixed(4)||'&mdash;')+'</code></td><td><code>'+(a.theta_vital?.new?.toFixed(4)||'&mdash;')+'</code></td><td><code>'+(a.access_boost?.new?.toFixed(4)||'&mdash;')+'</code></td><td>'+((o.active_ratio*100).toFixed(0)||0)+'%</td><td>'+((o.dormant_ratio*100).toFixed(0)||0)+'%</td></tr>';
  }).join('');
}

render();
</script></body></html>
"""
    # 注入数据
    html = html.replace("__MEM__", js_str(mem))
    html = html.replace("__CFG__", js_str(config))
    html = html.replace("__PID__", js_str(pid_state))
    html = html.replace("__HIST__", js_str(history))
    html = html.replace("__NOW__", now)

    # Fix the classChart bug - PT vs pt
    html = html.replace("H-pt-pb", "H-PT-PB")
    html = html.replace("const CH=H-pt-pb;", "const CH=H-PT-PB;")
    # Actually the JS has a literal "pt" in the calculation. Let me fix:
    html = html.replace("PT+CH*(1-getY(", "PT+CH*(1-getY(")  # already correct

    return html


def main():
    mem = count_memories()
    config = load_json(os.path.join(MEMORY_DIR, "controller_config.json"))
    pid_state = load_json(os.path.join(MEMORY_DIR, "pid_state.json"))
    history = load_jsonl(os.path.join(MEMORY_DIR, "memory_history.jsonl"))

    html = generate(mem, config, pid_state, history)

    out = Path(OUTPUT_PATH)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"✅ {out}")
    print(f"📊 {mem['total']} 条 · 活跃{mem['active']} 休眠{mem['dormant']} 低价值{mem['critical']}")
    print(f"⚙️ PID {pid_state.get('iteration',0)} 轮 · 遗忘率 {config.get('base_forget_rate','?')}")


if __name__ == "__main__":
    main()
