#!/usr/bin/env python3
"""
知识图谱生成器 — 从记忆文件的 [[link]] + 元数据生成交互式网络图。
使用纯 SVG/JS，无外部依赖。

用法: python3 generate_graph.py
输出: ~/桌面/memory-graph.html
"""

import json
import os
import re
import datetime
from pathlib import Path
from collections import Counter

MEMORY_DIR = os.path.expanduser("~/.claude/projects/-home-lxk/memory")
OUTPUT_PATH = os.path.expanduser("~/桌面/memory-graph.html")


def read_memory_graph() -> dict:
    """读取记忆网络：节点和边"""
    nodes = []
    edges = set()
    edge_data = {}

    for fpath in sorted(Path(MEMORY_DIR).glob("*.md")):
        if fpath.name == "MEMORY.md":
            continue
        content = fpath.read_text(encoding="utf-8")
        if not content.startswith("---"):
            continue

        def g(p, d=""):
            m = re.search(p, content)
            return m.group(1).strip() if m else d

        def gf(p, d=0):
            m = re.search(p, content)
            return float(m.group(1)) if m else d

        name = g(r'name:\s*(.+)', fpath.stem)
        desc = g(r'description:\s*(.+)', "")
        mtype = g(r'type:\s*(.+)', "memory")
        consolidation = gf(r'consolidation_level:\s*(.+)', 0.3)
        retention = gf(r'retention_strength:\s*(.+)', 0.5)

        # 从 body 提取 links
        body_parts = content.split("---", 2)
        body = body_parts[2] if len(body_parts) >= 3 else ""
        links = re.findall(r'\[\[(.+?)\]\]', body)
        for target in links:
            ekey = tuple(sorted([name, target]))
            if ekey not in edge_data:
                edge_data[ekey] = {"count": 0, "bidirectional": False}
            edge_data[ekey]["count"] += 1

        nodes.append(dict(
            id=name, desc=desc[:60], type=mtype,
            consolidation=round(consolidation, 2),
            retention=round(retention, 2),
            body_words_count=len(set(re.findall(r'[一-鿿]{3,6}|[a-zA-Z]{3,}', body.lower()))),
        ))

    # 构建边
    name_set = {n["id"] for n in nodes}
    for (s, t), data in edge_data.items():
        if s in name_set and t in name_set:
            edges.add(json.dumps({"source": s, "target": t, "count": data["count"]}))

    return {"nodes": nodes, "edges": [json.loads(e) for e in edges]}


def generate_html(graph: dict) -> str:
    """生成交互式 HTML 知识图谱"""
    nodes = json.dumps(graph["nodes"], ensure_ascii=False)
    edges = json.dumps(graph["edges"], ensure_ascii=False)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>记忆系统知识图谱</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0f1117;color:#e1e2e8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;overflow:hidden;height:100vh}}
#header{{position:fixed;top:0;left:0;right:0;z-index:100;padding:16px 24px;background:rgba(15,17,23,0.85);backdrop-filter:blur(8px);display:flex;align-items:center;gap:12px;border-bottom:1px solid #2a2b35}}
#header h1{{font-size:18px}}
#header small{{color:#7a7b85;font-size:13px}}
#header .counts{{margin-left:auto;color:#7a7b85;font-size:13px}}
#legend{{position:fixed;bottom:24px;right:24px;z-index:100;background:#1a1b23;border:1px solid #2a2b35;border-radius:12px;padding:16px;font-size:12px;min-width:160px}}
#legend h3{{color:#7a7b85;margin-bottom:8px;text-transform:uppercase;letter-spacing:.5px;font-size:11px}}
.legend-item{{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:12px}}
.legend-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
svg{{position:fixed;top:0;left:0;width:100%;height:100%}}
.tooltip{{position:fixed;z-index:200;background:#1a1b23;border:1px solid #555;border-radius:8px;padding:12px;font-size:13px;max-width:300px;display:none;pointer-events:none}}
.tooltip .name{{font-weight:600;font-size:15px;margin-bottom:4px}}
.tooltip .detail{{color:#7a7b85;font-size:11px;margin:2px 0}}
.tooltip .desc{{color:#aaa;font-size:12px;margin-top:4px}}
</style>
</head>
<body>

<div id="header">
  <h1>&#x1F9E0; 知识图谱</h1>
  <small>记忆系统关联网络</small>
  <div class="counts">
    <span id="node-count">0</span> 节点 &#x2022; <span id="edge-count">0</span> 连接 &#x2022; {now}
  </div>
</div>

<div id="legend">
  <h3>图例</h3>
  <div class="legend-item"><span class="legend-dot" style="background:#5b8def"></span> memory (reference)</div>
  <div class="legend-item"><span class="legend-dot" style="background:#f59e0b"></span> project</div>
  <div class="legend-item"><span class="legend-dot" style="background:#22d3ee"></span> user</div>
  <div class="legend-item"><span class="legend-dot" style="background:#10b981"></span> feedback</div>
  <div style="margin-top:8px;color:#7a7b85;font-size:11px">节点大小 = 巩固度</div>
</div>

<div id="tooltip" class="tooltip"></div>

<svg id="graph"></svg>

<script>
const NODES = {nodes};
const EDGES = {edges};

// 布局
const W = window.innerWidth, H = window.innerHeight;
const CX = W / 2, CY = H / 2;

// 颜色映射
const TYPE_COLORS = {{
  'memory': '#5b8def', 'reference': '#5b8def',
  'project': '#f59e0b',
  'user': '#22d3ee',
  'feedback': '#10b981',
}};

function getColor(type) {{
  return TYPE_COLORS[type] || '#7a7b85';
}}

// 力布局
function forceLayout(nodes, edges) {{
  const n = nodes.length;
  // 位置初始化：圆形
  nodes.forEach((d, i) => {{
    const angle = (i / n) * 2 * Math.PI - Math.PI / 2;
    const radius = Math.min(W, H) * 0.3;
    d.x = CX + radius * Math.cos(angle) + (Math.random() - 0.5) * 50;
    d.y = CY + radius * Math.sin(angle) + (Math.random() - 0.5) * 50;
    d.vx = 0; d.vy = 0;
  }});

  // 构建邻接表
  const adj = {{}};
  edges.forEach(e => {{
    if (!adj[e.source]) adj[e.source] = new Set();
    if (!adj[e.target]) adj[e.target] = new Set();
    adj[e.source].add(e.target);
    adj[e.target].add(e.source);
  }});

  // 迭代
  const REPEL = 8000, ATTRACT = 0.005, CENTER = 0.01, DAMPING = 0.85;
  for (let iter = 0; iter < 120; iter++) {{
    // 排斥力
    for (let i = 0; i < n; i++) {{
      for (let j = i + 1; j < n; j++) {{
        let dx = nodes[j].x - nodes[i].x;
        let dy = nodes[j].y - nodes[i].y;
        let dist = Math.sqrt(dx * dx + dy * dy) || 1;
        let force = REPEL / (dist * dist + 10);
        let fx = force * dx / dist;
        let fy = force * dy / dist;
        nodes[i].vx -= fx; nodes[i].vy -= fy;
        nodes[j].vx += fx; nodes[j].vy += fy;
      }}
    }}

    // 吸引力（有边连接）
    edges.forEach(e => {{
      let s = nodes.findIndex(d => d.id === e.source);
      let t = nodes.findIndex(d => d.id === e.target);
      if (s === -1 || t === -1) return;
      let dx = nodes[t].x - nodes[s].x;
      let dy = nodes[t].y - nodes[s].y;
      let dist = Math.sqrt(dx * dx + dy * dy) || 1;
      let force = ATTRACT * dist;
      nodes[s].vx += force * dx / dist;
      nodes[s].vy += force * dy / dist;
      nodes[t].vx -= force * dx / dist;
      nodes[t].vy -= force * dy / dist;
    }});

    // 向心力
    nodes.forEach(d => {{
      d.vx += (CX - d.x) * CENTER;
      d.vy += (CY - d.y) * CENTER;
    }});

    // 阻尼
    nodes.forEach(d => {{
      d.vx *= DAMPING;
      d.vy *= DAMPING;
      d.x += d.vx;
      d.y += d.vy;
    }});
  }}

  return nodes;
}}

// 渲染
function render() {{
  forceLayout(NODES, EDGES);

  const svg = document.getElementById('graph');
  const ns = 'http://www.w3.org/2000/svg';

  document.getElementById('node-count').textContent = NODES.length;
  document.getElementById('edge-count').textContent = EDGES.length;

  // 边
  EDGES.forEach(e => {{
    const s = NODES.find(d => d.id === e.source);
    const t = NODES.find(d => d.id === e.target);
    if (!s || !t) return;
    const line = document.createElementNS(ns, 'line');
    line.setAttribute('x1', s.x);
    line.setAttribute('y1', s.y);
    line.setAttribute('x2', t.x);
    line.setAttribute('y2', t.y);
    line.setAttribute('stroke', '#2a2b35');
    line.setAttribute('stroke-width', Math.min(3, 0.5 + e.count * 0.5));
    svg.appendChild(line);
  }});

  // 节点
  NODES.forEach(d => {{
    const size = 8 + d.consolidation * 22;
    const g = document.createElementNS(ns, 'g');
    g.style.cursor = 'pointer';

    const circle = document.createElementNS(ns, 'circle');
    circle.setAttribute('cx', d.x);
    circle.setAttribute('cy', d.y);
    circle.setAttribute('r', size);
    circle.setAttribute('fill', getColor(d.type));
    circle.setAttribute('stroke', '#0f1117');
    circle.setAttribute('stroke-width', '2');
    circle.style.transition = 'r 0.2s';
    g.appendChild(circle);

    const text = document.createElementNS(ns, 'text');
    text.setAttribute('x', d.x);
    text.setAttribute('y', d.y + 4);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('fill', '#e1e2e8');
    text.setAttribute('font-size', '11');
    text.setAttribute('font-weight', '500');
    text.setAttribute('pointer-events', 'none');
    text.textContent = d.id.length > 12 ? d.id.slice(0, 12) + '…' : d.id;
    g.appendChild(text);

    // hover
    const tt = document.getElementById('tooltip');
    g.addEventListener('mouseenter', (e) => {{
      const rect = circle.getBoundingClientRect();
      circle.setAttribute('stroke', '#fff');
      tt.style.display = 'block';
      tt.style.left = Math.min(e.clientX + 16, W - 310) + 'px';
      tt.style.top = Math.min(e.clientY - 10, H - 160) + 'px';
      const typeColor = getColor(d.type);
      const clBar = '█'.repeat(Math.round(d.consolidation * 10)) + '░'.repeat(10 - Math.round(d.consolidation * 10));
      tt.innerHTML = '<div class="name" style="color:' + typeColor + '">' + d.id + '</div>' +
        '<div class="detail">类型: ' + d.type + '</div>' +
        '<div class="detail">巩固度: ' + clBar + ' ' + d.consolidation.toFixed(2) + '</div>' +
        '<div class="detail">保留: ' + (d.retention * 100).toFixed(0) + '%</div>' +
        '<div class="desc">' + d.desc + '</div>';
    }});
    g.addEventListener('mouseleave', () => {{
      circle.setAttribute('stroke', '#0f1117');
      tt.style.display = 'none';
    }});

    svg.appendChild(g);
  }});
}}

render();
</script>
</body>
</html>
'''

def main():
    graph = read_memory_graph()
    html = generate_html(graph)

    out = Path(OUTPUT_PATH)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    print(f"✅ 知识图谱: {OUTPUT_PATH}")
    print(f"📊 {len(graph['nodes'])} 节点 / {len(graph['edges'])} 连接")


if __name__ == "__main__":
    main()
