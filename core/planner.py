import json
from .llm import chat

PLAN_SYS = """You convert a single natural-language UI test step into a small JSON action plan.
Output ONLY JSON. Keys:
- "actions": list of ordered actions. Each action has:
  - "type": one of ["navigate","click","fill","press","wait_for","wait_for_selector",
                   "assert_text","assert_url_contains","select","combo_select",
                   "date_set","file_upload","hover","scroll_into_view",
                   "drag_and_drop"]
  - "target": a human hint (text on button, label, placeholder, role, test-id). Keep short.
  - "value": optional string (for fill/select/press).
  - "notes": optional brief hint.
Guidelines:
- Prefer robust selectors: getByRole (with name), getByText (exact:false), placeholder, label, [data-testid].
- For comboboxes use: {"type":"combo_select","target":"<label or name>","value":"<option text>"}.
- For date pickers use ISO date: {"type":"date_set","target":"Start Date","value":"2025-08-07"}.
- For upload use path: {"type":"file_upload","target":"Profile picture","value":"fixtures/sample.txt"}.
- Prefer "wait_for_selector" over generic waits when possible.
- Do NOT return code. JSON only.
"""

_ALLOWED = {
    "navigate","click","fill","press","wait_for","wait_for_selector",
    "assert_text","assert_url_contains","select","combo_select",
    "date_set","file_upload","hover","scroll_into_view","drag_and_drop"
}

def _sanitize(actions):
    """Keep only allowed actions; trim noise; cap length."""
    safe = []
    for a in (actions or [])[:10]:  # cap per-step actions
        t = (a.get("type") or "").strip()
        if t not in _ALLOWED:
            continue
        safe.append({
            "type": t,
            "target": (a.get("target") or "").strip(),
            "value": a.get("value"),
            "notes": (a.get("notes") or "").strip()
        })
    return safe

def plan_step(page_html, step_desc, base_url):
    snippet = page_html[:3500] if page_html else ""
    messages = [
        {"role":"system","content":PLAN_SYS},
        {"role":"user","content":f"Base URL: {base_url}\nPage (truncated): {snippet}\n\nMake a JSON action plan for: \"{step_desc}\""}
    ]
    out = chat(messages, temperature=0.0)  # clamp creativity
    try:
        data = json.loads(out)
        actions = _sanitize(data.get("actions", []))
        return actions or [{"type":"click","target":step_desc}]
    except Exception:
        # Fallback to something deterministic so we can still log/observe
        return [{"type":"click","target":step_desc}]
