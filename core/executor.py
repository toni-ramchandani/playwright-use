import os, time, traceback, json, re
from playwright.sync_api import sync_playwright, expect
from .planner import plan_step
from .healer import find_in_frames, combo_select, date_set, file_upload, find_input, find_clickable
from .oracle import assert_url_contains, fuzzy_page_assertion

def _safe_filename(prefix, idx):
    return f"{prefix}_{idx:03d}.png"

def _mklog(out_dir):
    log_path = os.path.join(out_dir, "events.log")
    def log(msg):
        ts = time.strftime("%H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    return log

def _safe(s: str, limit: int = 800):
    s = str(s).replace("\r", "").replace("\x00", "")
    return s if len(s) <= limit else s[:limit] + "…"

def _highlight(el):
    try:
        el.evaluate("e => { e.__old_outline = e.style.outline; e.style.outline='3px solid magenta' }")
        time.sleep(0.05)
        el.evaluate("e => { if(e.__old_outline!==undefined) e.style.outline=e.__old_outline }")
    except:
        pass

def _dismiss_noise(page):
    selectors = [
        "#onetrust-accept-btn-handler",
        "button#onetrust-accept-btn-handler",
        "button:has-text('Accept All')",
        "button:has-text('I Accept')",
        "text=/Accept All/i",
        "[data-testid=close-toast]",
        "button:has-text('Got it')",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click()
                page.wait_for_timeout(150)
        except:
            pass

def _find_checkbox(page, hint: str):
    rx = re.compile(hint or "", re.I)
    try:
        loc = page.get_by_role("checkbox", name=rx)
        if loc.count() > 0:
            return loc.first
    except:
        pass
    # Prefer direct input matches by name/aria-label
    try:
        loc = page.locator(
            f"input[type='checkbox'][name*='{hint}' i], input[type='checkbox'][aria-label*='{hint}' i]"
        ).first
        if loc and loc.count() > 0:
            return loc
    except:
        pass
    try:
        # Descendant input inside a matching label
        loc = page.locator(
            "xpath=(//label[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), "
            + f"'{(hint or '').lower()}')]//input[@type='checkbox'])[1]"
        ).first
        if loc and loc.count() > 0:
            return loc
    except:
        pass
    try:
        # Nearby input before/after a matching label
        loc = page.locator(
            "xpath=(//label[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), "
            + f"'{(hint or '').lower()}')]/following::input[@type='checkbox'] | "
            "//label[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), "
            + f"'{(hint or '').lower()}')]/preceding::input[@type='checkbox'])[1]"
        ).first
        if loc and loc.count() > 0:
            return loc
    except:
        pass
    try:
        node = page.get_by_text(rx, exact=False).first
        if node and node.count() > 0:
            container = node.locator("xpath=ancestor-or-self::*[self::label or self::div or self::section or self::form][1]").first
            if container and container.count() > 0:
                cb = container.locator("input[type='checkbox']").first
                if cb and cb.count() > 0:
                    return cb
    except:
        pass
    return None

def _after_fill_settle(page, el):
    """Trigger validations that require blur/change."""
    try:
        el.dispatch_event("input")
    except: pass
    try:
        el.dispatch_event("change")
    except: pass
    try:
        el.blur()
    except:
        try:
            page.keyboard.press("Tab")
        except:
            pass

def _run_action(page, atype, target, value):
    if atype == "navigate":
        page.goto(value or target, wait_until="networkidle")

    elif atype == "click":
        hint = (target or value or "")
        el = _find_checkbox(page, hint) or find_clickable(page, hint)
        if not el or (hasattr(el, "count") and el.count() == 0):
            el = find_in_frames(page, hint)
        if not el:
            raise RuntimeError(f"Target not found for click: {target}")

        try: el.scroll_into_view_if_needed()
        except: pass
        _highlight(el)
        try: el.wait_for(state="visible", timeout=5000)
        except: pass

        # Normalize and harden checkbox/switch interactions
        try:
            itype = (el.get_attribute("type") or "").lower()
            role = (el.get_attribute("role") or "").lower()
            has_aria_checked = (el.get_attribute("aria-checked") is not None)

            # If we didn't land on the <input type=checkbox>, try to find it near the element
            if itype != "checkbox":
                try:
                    container = el.locator("xpath=ancestor-or-self::*[self::label or self::div or self::section][1]").first
                    if container and container.count() > 0:
                        cb = container.locator("input[type='checkbox']").first
                        if cb and cb.count() > 0:
                            el = cb
                            itype = "checkbox"
                except:
                    pass

            if itype == "checkbox":
                try:
                    el.check()
                    try:
                        # Verify state stuck
                        if hasattr(el, "is_checked") and not el.is_checked():
                            el.check(force=True)
                    except:
                        pass
                    return None
                except:
                    # Fallback to clicking the associated label/container
                    try:
                        anc_label = el.locator("xpath=ancestor::label[1]").first
                        if anc_label and anc_label.count() > 0:
                            anc_label.click()
                            return None
                    except:
                        pass
            elif role in ("checkbox", "switch") or has_aria_checked:
                # ARIA widgets that toggle via click
                el.click()
                return None
        except:
            pass

        try:
            el.click(timeout=8000)
        except Exception as e:
            try:
                el.click(timeout=8000, force=True)
            except:
                try:
                    el.evaluate("e => e.click()")
                except:
                    raise e

    elif atype == "fill":
        el = find_input(page, target or "")
        if not el:
            el = find_in_frames(page, target or "")
        if not el:
            raise RuntimeError(f"Target not found for fill: {target}")

        # Ensure the element is in view before interacting (stabilizes floating-label inputs)
        try: el.scroll_into_view_if_needed()
        except: pass

        _highlight(el)
        try: el.wait_for(state="visible", timeout=5000)
        except: pass
        try: el.click(timeout=2000)
        except: pass
        time.sleep(0.25)
        try:
            el.fill(value or "")
        except Exception:
            try:
                el.click()
                try: page.keyboard.press("Control+A")
                except:
                    try: page.keyboard.press("Meta+A")
                    except: pass
            except:
                pass
            page.keyboard.type(value or "", delay=20)

        # Verify the value actually stuck; some widgets ignore fill() without key events
        try:
            current_val = el.evaluate("e => e.value")
            if (value or "") != (current_val or ""):
                try:
                    el.click()
                    try: page.keyboard.press("Control+A")
                    except:
                        try: page.keyboard.press("Meta+A")
                        except: pass
                except:
                    pass
                page.keyboard.type(value or "", delay=20)
        except:
            # Ignore evaluation issues and proceed
            pass

        _after_fill_settle(page, el)  # ← ensure validation sees the value

    elif atype == "press":
        page.keyboard.press(value or "Enter")

    elif atype == "select":
        el = find_in_frames(page, target or "")
        if not el: raise RuntimeError(f"Target not found for select: {target}")
        el.select_option(value)

    elif atype == "wait_for":
        page.wait_for_timeout(int(value) if str(value).isdigit() else 300)

    elif atype == "wait_for_selector":
        hint = (value or target or "").strip()
        if not hint:
            page.wait_for_timeout(300)
        else:
            # Interpret human hint using robust resolvers first
            el = None
            try:
                el = find_input(page, hint)
            except:
                pass
            if not el:
                try:
                    el = _find_checkbox(page, hint)
                except:
                    pass
            if not el:
                try:
                    el = find_in_frames(page, hint)
                except:
                    pass
            if el is not None:
                try:
                    # Normalize to a single locator and wait for visibility
                    try:
                        if hasattr(el, "count") and el.count() > 0:
                            el = el.first
                    except:
                        pass
                    try: el.scroll_into_view_if_needed()
                    except: pass
                    el.wait_for(state="visible")
                except:
                    # As a last resort, fall back to raw selector-based wait
                    page.wait_for_selector(hint, state="visible")
            else:
                # No element resolved via heuristics; fall back to raw selector/text
                try:
                    import re as _re
                    node = page.get_by_text(_re.compile(hint, _re.I)).first
                    node.wait_for(state="visible")
                except:
                    page.wait_for_selector(hint, state="visible")

    elif atype == "assert_url_contains":
        ok, _ = assert_url_contains(page, value or target)
        if not ok: raise AssertionError(f"URL does not contain {value or target}")

    elif atype == "assert_text":
        el = find_in_frames(page, target or "")
        if not el: raise RuntimeError(f"Target not found for assert_text: {target}")
        try: el = el.first
        except: pass
        expect(el).to_be_visible()

    elif atype == "combo_select":
        combo_select(page, target or "", value or "")

    elif atype == "date_set":
        date_set(page, target or "", value or "")

    elif atype == "file_upload":
        file_upload(page, target or "upload", value)

    elif atype == "hover":
        el = find_in_frames(page, target or "")
        _highlight(el)
        el.hover()

    elif atype == "scroll_into_view":
        el = find_in_frames(page, target or "")
        _highlight(el)
        el.scroll_into_view_if_needed()

    elif atype == "drag_and_drop":
        src = find_in_frames(page, target or "")
        dst = find_in_frames(page, value or "")
        _highlight(src); _highlight(dst)
        src.drag_to(dst)

    else:
        return f"Unknown action type: {atype}; skipped."

    return None

def run_goal(name, url, steps, assertions, headless=True):
    session_ts = int(time.time())
    out_dir = os.path.join("runs", f"{name.replace(' ','_')}_{session_ts}")
    os.makedirs(out_dir, exist_ok=True)

    log = _mklog(out_dir)
    step_records = []
    assertion_records = []

    with sync_playwright() as p:
        launch_args = {}
        if not headless:
            launch_args["args"] = ["--start-maximized", "--window-size=1920,1080"]
        browser = p.chromium.launch(headless=headless, **launch_args)

        # In headed mode, inherit the OS window size for maximum fidelity (viewport=None)
        # In headless, keep a fixed viewport for deterministic layout
        if not headless:
            context = browser.new_context(record_video_dir=out_dir, viewport=None)
        else:
            context = browser.new_context(record_video_dir=out_dir, viewport={"width":1280, "height":800})
        context.tracing.start(screenshots=True, snapshots=True, sources=True)

        page = context.new_page()
        page.on("console", lambda m: log(f"CONSOLE[{m.type}] {m.text}"))
        page.on("request", lambda r: log(f"REQ {r.method} {r.url}"))
        page.on("response", lambda r: log(f"RES {r.status} {r.url}"))

        page.set_default_timeout(10_000)
        page.set_default_navigation_timeout(20_000)
        # Only enforce a viewport in headless; headed inherits maximized window size
        if headless:
            page.set_viewport_size({"width":1280,"height":800})

        if url:
            log(f"INIT navigate -> {url}")
            page.goto(url, wait_until="domcontentloaded")

        for i, s in enumerate(steps, start=1):
            desc = s["description"]
            started = time.time()
            screenshot_path = None
            status = "pass"
            error = None
            notes = None

            try:
                _dismiss_noise(page)
                log(f"STEP {i}: {desc}")

                actions = plan_step(page.content(), desc, url or page.url)
                plan_json = json.dumps(actions, ensure_ascii=False)
                log(f"PLAN {i}: {plan_json}")
                notes = f"AI plan: {plan_json}"

                # Safeguard: if the step asks to "check" but no click is planned, inject a click
                try:
                    dl = (desc or "").lower()
                    needs_check = ("check" in dl)
                    has_click = any((a.get("type") or "").lower() == "click" for a in (actions or []))
                    if needs_check and not has_click:
                        import re as _re
                        m = _re.search(r"'([^']+)'|\"([^\"]+)\"", desc or "")
                        target_label = (m.group(1) or m.group(2)) if m else "privacy"
                        actions = ([{"type":"click","target":target_label}] + (actions or []))[:10]
                        log(f"PLAN {i} UPDATED: injected click for check -> {target_label}")
                except:
                    pass

                for act in actions:
                    atype = (act.get("type") or "").strip()
                    target = (act.get("target") or "").strip()
                    value = act.get("value")
                    log(f"EXEC {i}: type={atype} target={target} value={value}")

                    if not atype:
                        log(f"SKIP {i}: missing action type"); continue
                    if atype not in {
                        "navigate","click","fill","press","wait_for","wait_for_selector",
                        "assert_text","assert_url_contains","select","combo_select",
                        "date_set","file_upload","hover","scroll_into_view","drag_and_drop"
                    }:
                        log(f"SKIP {i}: unknown action type: {atype}"); continue
                    if atype not in {"press","wait_for"} and not target and not value:
                        log(f"SKIP {i}: empty target/value"); continue

                    err = _run_action(page, atype, target, value)
                    if err:
                        log(f"WARN {i}: {_safe(err)}")
                        notes = (notes + "\n" + err) if notes else err

                screenshot_path = os.path.join(out_dir, _safe_filename("step", i))
                page.screenshot(path=screenshot_path, full_page=False)

            except Exception as e:
                status = "fail"
                tb = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
                log(f"FAIL {i}: {_safe(tb)}")
                error = tb
                screenshot_path = os.path.join(out_dir, _safe_filename("step_fail", i))
                try: page.screenshot(path=screenshot_path, full_page=False)
                except: pass
            finally:
                step_records.append({
                    "index": i,
                    "description": desc,
                    "status": status,
                    "error": error,
                    "screenshot": os.path.relpath(screenshot_path, out_dir) if screenshot_path else None,
                    "elapsed_ms": int((time.time()-started)*1000),
                    "notes": notes
                })

        for j, a in enumerate(assertions, start=1):
            started = time.time()
            text = a
            passed = True
            explain = ""
            try:
                if text.lower().startswith("url contains"):
                    frag = text.split("contains",1)[1].strip(" '\"")
                    passed, explain = assert_url_contains(page, frag)
                else:
                    passed, explain = fuzzy_page_assertion(page, text)
            except Exception as e:
                passed = False
                explain = f"{type(e).__name__}: {e}"
            assertion_records.append({
                "index": j,
                "text": text,
                "passed": bool(passed),
                "explanation": explain,
                "elapsed_ms": int((time.time()-started)*1000)
            })

        trace_zip = os.path.join(out_dir, "trace.zip")
        context.tracing.stop(path=trace_zip)
        context.close()
        browser.close()

    return out_dir, step_records, assertion_records
