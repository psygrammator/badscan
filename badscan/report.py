# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from html import escape


def render_report(sites: list[dict], demand: list[dict], generated_at: str) -> str:
    site_json = json.dumps(sites, ensure_ascii=False).replace("<", "\\u003c")
    demand_json = json.dumps(demand, ensure_ascii=False).replace("<", "\\u003c")
    hot = sum(1 for row in sites if int(row.get("bad_score") or 0) >= 50)
    buckets: dict[str, int] = {}
    for row in sites:
        title = str(row.get("category_title") or "").strip()
        if not title:
            continue
        buckets[title] = buckets.get(title, 0) + 1
    bucket_line = " · ".join(f"{escape(title)} {count}" for title, count in sorted(buckets.items()))
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CoreWeb leads</title>
<style>
  :root {{
    color-scheme: dark;
    --bg: #10110f;
    --card: #191b17;
    --line: #2c2e28;
    --text: #f3f1e8;
    --muted: #a3a396;
    --accent: #d6ff4a;
    --hot: #ffb020;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font: 15px/1.45 "Segoe UI", sans-serif;
    background: var(--bg);
    color: var(--text);
  }}
  header, main {{ width: min(1180px, calc(100% - 32px)); margin: 0 auto; }}
  header {{ padding: 28px 0 8px; }}
  h1 {{ font-size: 28px; margin: 0 0 6px; letter-spacing: -0.03em; }}
  h2 {{ font-size: 18px; margin: 28px 0 10px; }}
  .meta {{ color: var(--muted); }}
  .stats {{ display: flex; gap: 18px; margin: 14px 0; color: var(--muted); }}
  .stats b {{ color: var(--accent); font-weight: 650; }}
  .bar {{ display: flex; flex-wrap: wrap; gap: 10px; align-items: end; margin: 12px 0 18px; }}
  label {{ display: flex; flex-direction: column; gap: 4px; color: var(--muted); font-size: 12px; }}
  input, select {{
    background: var(--card);
    color: var(--text);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 8px 10px;
    min-width: 160px;
  }}
  table {{ width: 100%; border-collapse: collapse; background: var(--card); }}
  th, td {{
    text-align: left;
    vertical-align: top;
    padding: 10px 8px;
    border-bottom: 1px solid var(--line);
  }}
  th {{ color: var(--muted); font-weight: 600; font-size: 12px; }}
  tr.hot td:first-child {{ color: var(--hot); }}
  a {{ color: var(--accent); }}
  button {{
    background: transparent;
    color: var(--text);
    border: 1px solid var(--line);
    border-radius: 8px;
    padding: 6px 8px;
    cursor: pointer;
  }}
  .pitch {{ max-width: 420px; color: #dddacb; }}
  .empty {{ color: var(--muted); padding: 12px 0 28px; }}
</style>
</head>
<body>
<header>
  <h1>Лиды CoreWeb</h1>
  <div class="meta">Снято {escape(generated_at)}. Офферы сами никуда не уходят — это список, с кем писать.</div>
  <div class="meta">{bucket_line}</div>
  <div class="stats">
    <span>сайтов <b id="site-count">{len(sites)}</b></span>
    <span>score ≥ 50 <b>{hot}</b></span>
    <span>заявок <b id="demand-count">{len(demand)}</b></span>
  </div>
</header>
<main>
  <h2>Слабые сайты</h2>
  <div class="bar">
    <label>поиск<input id="q" placeholder="домен, cms, город"></label>
    <label>ниша<select id="cat"><option value="all">все ниши</option></select></label>
    <label>min score<input id="min" type="number" min="0" max="100" value="0"></label>
    <label>только .ua / UA-сигнал<select id="ua">
      <option value="all">все</option>
      <option value="ua">ukraine ≥ 40</option>
    </select></label>
  </div>
  <table>
    <thead>
      <tr>
        <th>score</th><th>ниша</th><th>домен</th><th>контакт</th><th>проблема</th><th></th>
      </tr>
    </thead>
    <tbody id="sites"></tbody>
  </table>
  <div id="sites-empty" class="empty" hidden>Под фильтр никто не попал.</div>

  <h2>Кто ищет сайт</h2>
  <div class="bar">
    <label>поиск<input id="dq" placeholder="лендинг, бюджет, канал"></label>
    <label>источник<select id="src">
      <option value="all">все</option>
      <option value="freelancehunt">freelancehunt</option>
      <option value="telegram">telegram</option>
      <option value="rss">rss</option>
    </select></label>
  </div>
  <table>
    <thead>
      <tr><th>когда</th><th>источник</th><th>заявка</th><th>бюджет</th></tr>
    </thead>
    <tbody id="demand"></tbody>
  </table>
  <div id="demand-empty" class="empty" hidden>Заявок нет. Запусти demand и проверь токен Freelancehunt.</div>
</main>
<script id="site-data" type="application/json">{site_json}</script>
<script id="demand-data" type="application/json">{demand_json}</script>
<script>
const sites = JSON.parse(document.getElementById("site-data").textContent);
const demand = JSON.parse(document.getElementById("demand-data").textContent);

function esc(value) {{
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({{
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }}[ch]));
}}

const catSelect = document.getElementById("cat");
[...new Set(sites.map((row) => row.category_title).filter(Boolean))].sort().forEach((title) => {{
  const option = document.createElement("option");
  option.value = title;
  option.textContent = title;
  catSelect.appendChild(option);
}});

function renderSites() {{
  const q = document.getElementById("q").value.trim().toLowerCase();
  const min = Number(document.getElementById("min").value || 0);
  const ua = document.getElementById("ua").value;
  const cat = catSelect.value;
  const body = document.getElementById("sites");
  const rows = sites.filter((row) => {{
    if (Number(row.bad_score || 0) < min) return false;
    if (ua === "ua" && Number(row.ukraine || 0) < 40) return false;
    if (cat !== "all" && row.category_title !== cat) return false;
    if (!q) return true;
    const blob = [row.domain, row.category_title, row.city, row.cms, row.title, row.issues, row.phones, row.emails, row.pitch].join(" ").toLowerCase();
    return blob.includes(q);
  }});
  body.innerHTML = rows.map((row) => {{
    const contact = [row.phones, row.emails].filter(Boolean).map(esc).join("<br>") || "—";
    const cls = Number(row.bad_score) >= 50 ? "hot" : "";
    return `<tr class="${{cls}}">
      <td>${{esc(row.bad_score)}}</td>
      <td>${{esc(row.category_title || "—")}}<br><span class="meta">${{esc(row.city || "")}}</span></td>
      <td><a href="${{esc(row.final_url || row.url)}}" target="_blank" rel="noreferrer">${{esc(row.domain)}}</a><br><span class="meta">${{esc(row.cms || "")}} ${{esc(row.cms_version || "")}}</span></td>
      <td>${{contact}}</td>
      <td class="pitch">${{esc(row.pitch || row.issues || row.error || "")}}</td>
      <td><button type="button" data-pitch="${{esc(row.pitch || "")}}">копировать</button></td>
    </tr>`;
  }}).join("");
  document.getElementById("sites-empty").hidden = rows.length !== 0;
}}

function renderDemand() {{
  const q = document.getElementById("dq").value.trim().toLowerCase();
  const src = document.getElementById("src").value;
  const body = document.getElementById("demand");
  const rows = demand.filter((row) => {{
    if (src !== "all" && row.source !== src) return false;
    if (!q) return true;
    const blob = [row.title, row.body, row.budget, row.author, row.url, row.matched].join(" ").toLowerCase();
    return blob.includes(q);
  }});
  body.innerHTML = rows.map((row) => `<tr>
    <td>${{esc((row.published_at || row.fetched_at || "").slice(0, 16))}}</td>
    <td>${{esc(row.source)}}<br><span class="meta">${{esc(row.author || "")}}</span></td>
    <td><a href="${{esc(row.url)}}" target="_blank" rel="noreferrer">${{esc(row.title)}}</a><br><span class="meta">${{esc((row.body || "").slice(0, 220))}}</span></td>
    <td>${{esc(row.budget || "—")}}</td>
  </tr>`).join("");
  document.getElementById("demand-empty").hidden = rows.length !== 0;
}}

document.getElementById("sites").addEventListener("click", async (event) => {{
  const button = event.target.closest("button");
  if (!button) return;
  const text = button.dataset.pitch || "";
  try {{
    await navigator.clipboard.writeText(text);
    button.textContent = "ок";
  }} catch (err) {{
    button.textContent = "не вышло";
  }}
}});

["q", "min", "ua", "cat"].forEach((id) => document.getElementById(id).addEventListener("input", renderSites));
["dq", "src"].forEach((id) => document.getElementById(id).addEventListener("input", renderDemand));
renderSites();
renderDemand();
</script>
</body>
</html>
"""
