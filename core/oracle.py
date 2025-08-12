from .llm import chat

def assert_url_contains(page, fragment: str):
    return fragment.lower() in page.url.lower(), f"URL was {page.url}"

def fuzzy_page_assertion(page, claim: str):
    html = page.content()
    needles = ["thank you","completed","order","success","confirmation"]
    if any(tok in html.lower() for tok in needles):
        return True, "Heuristic DOM check suggests confirmation present."

    snippet = html[:5000]
    msg = [
        {"role":"system","content":"You are a strict QA oracle. Answer STRICTLY: PASS or FAIL, then <=2 sentence reason."},
        {"role":"user","content":f"Assertion: {claim}\nPage DOM (truncated):\n{snippet}"}
    ]
    out = chat(msg, temperature=0.0)
    norm = out.strip().lower()
    passed = norm.startswith("pass")
    return passed, out
