import os, time, json
from jinja2 import Template

TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>{{name}} – SmartUI-AI Report</title>
<style>
:root{
  --bg:#f6f7fb; --card:#ffffff; --text:#0f1222; --muted:#6b7280;
  --border:#e5e7eb; --pass:#10b981; --fail:#ef4444; --chip:#eef2ff; --brand:#4f46e5;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Arial;background:var(--bg);color:var(--text)}
.container{max-width:1080px;margin:0 auto;padding:24px}
.header{background:linear-gradient(135deg, #6366f1 0%, #22c55e 100%);color:white;border-radius:16px;padding:20px 24px;box-shadow:0 10px 30px rgba(79,70,229,0.25)}
.header h1{margin:0 0 6px 0;font-size:28px}
.meta{display:flex;flex-wrap:wrap;gap:12px;color:#eef2ff}
.meta span{opacity:.95}
.summary{display:flex;gap:10px;margin-top:12px;flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;gap:8px;padding:6px 10px;background:rgba(255,255,255,.15);border-radius:999px;font-weight:600}
.chip.pass{background:rgba(16,185,129,.15)}
.chip.fail{background:rgba(239,68,68,.15)}

.section{margin-top:22px}
.section h2{margin:6px 0 12px 0;font-size:20px;color:#111827}
.grid{display:grid;grid-template-columns:1fr;gap:12px}
@media(min-width:860px){.grid{grid-template-columns:1fr}}

.card{background:var(--card);border:1px solid var(--border);border-radius:14px;overflow:hidden;box-shadow:0 4px 14px rgba(0,0,0,0.06)}
.card-head{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid var(--border)}
.card-title{font-weight:700}
.badge{padding:4px 9px;border-radius:999px;font-size:12px;background:var(--chip);color:#4338ca}
.status{font-weight:700}
.status-pass{color:var(--pass)}
.status-fail{color:var(--fail)}
.card-body{padding:16px;display:grid;gap:12px}
img.sshot{max-width:100%;border:1px solid var(--border);border-radius:10px}
pre{white-space:pre-wrap;background:#0b1220;color:#e5e7eb;padding:12px;border-radius:10px;overflow:auto}
.details{border:1px dashed var(--border);border-radius:10px;padding:8px}
.details summary{cursor:pointer;font-weight:600}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
.toolbar a{color:white;text-decoration:none;border:1px solid rgba(255,255,255,.35);padding:6px 10px;border-radius:8px}
.small{color:var(--muted);font-size:13px}
.a-muted{color:#374151}
</style>
<script>
function toggleAll(open){
  document.querySelectorAll('details').forEach(d=>{d.open = open});
}
</script>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>{{name}}</h1>
      <div class="meta">
        <span>URL: <a class="a-muted" style="color:#eef2ff;text-decoration:underline;" href="{{url}}" target="_blank">{{url}}</a></span>
        <span>Started: {{start_ts}}</span>
        <span>Duration: {{duration_sec}}s</span>
      </div>
      {% set pass_count = steps|selectattr('status','equalto','pass')|list|length %}
      {% set fail_count = steps|selectattr('status','equalto','fail')|list|length %}
      <div class="summary">
        <div class="chip">Steps: {{steps|length}}</div>
        <div class="chip pass">Pass: {{pass_count}}</div>
        <div class="chip fail">Fail: {{fail_count}}</div>
        <div class="toolbar">
          <a href="trace.zip">Download trace.zip</a>
          <a href="#" onclick="toggleAll(true);return false;">Expand all</a>
          <a href="#" onclick="toggleAll(false);return false;">Collapse all</a>
        </div>
      </div>
    </div>

    <div class="section">
      <h2>Steps</h2>
      <div class="grid">
        {% for s in steps %}
        <div id="step-{{loop.index}}" class="card">
          <div class="card-head">
            <div class="card-title">{{loop.index}}) {{s.description}}</div>
            <div class="badge">{{s.elapsed_ms}} ms</div>
          </div>
          <div class="card-body">
            <div>Status: {% if s.status == 'pass' %}<span class="status status-pass">PASS</span>{% else %}<span class="status status-fail">FAIL</span>{% endif %}</div>
            {% if s.error %}
            <details class="details" open>
              <summary>Error</summary>
              <pre>{{s.error}}</pre>
            </details>
            {% endif %}
            {% if s.notes %}
            <details class="details">
              <summary>Plan & Notes</summary>
              <pre>{{s.notes}}</pre>
            </details>
            {% endif %}
            {% if s.screenshot %}
            <div>
              <a href="{{s.screenshot}}" target="_blank"><img class="sshot" src="{{s.screenshot}}" alt="Step {{loop.index}} screenshot"/></a>
              <div class="small">Click image to open full-size</div>
            </div>
            {% endif %}
          </div>
        </div>
        {% endfor %}
      </div>
    </div>

    <div class="section">
      <h2>Assertions</h2>
      <div class="grid">
        {% for a in assertions %}
        <div class="card">
          <div class="card-head">
            <div class="card-title">{{loop.index}}) {{a.text}}</div>
            <div class="badge">{{a.elapsed_ms}} ms</div>
          </div>
          <div class="card-body">
            <div>Result: {% if a.passed %}<span class="status status-pass">PASS</span>{% else %}<span class="status status-fail">FAIL</span>{% endif %}</div>
            {% if a.explanation %}<details class="details" open><summary>Explanation</summary><pre>{{a.explanation}}</pre></details>{% endif %}
          </div>
        </div>
        {% endfor %}
      </div>
    </div>

    <div class="section small">Tip: Open <code>trace.zip</code> in Playwright Trace Viewer for a deep dive.</div>
  </div>
</body>
</html>"""

def write_report(out_dir, name, url, start_ts, steps, assertions):
    html = Template(TEMPLATE).render(
        name=name,
        url=url,
        start_ts=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(start_ts)),
        duration_sec=round(time.time()-start_ts,2),
        steps=steps,
        assertions=assertions
    )
    path = os.path.join(out_dir, "report.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump({"name":name,"url":url,"steps":steps,"assertions":assertions}, f, ensure_ascii=False, indent=2)
    return path
