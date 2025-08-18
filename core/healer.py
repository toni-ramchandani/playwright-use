import re
from datetime import datetime
from playwright.sync_api import Page
from .util import load_aliases, update_aliases

# -------- basic strategies --------
def _by_accessibility(page: Page, hint: str):
    try:
        return page.get_by_role("button", name=re.compile(hint, re.I))
    except: pass
    try:
        return page.get_by_role("link", name=re.compile(hint, re.I))
    except: pass
    try:
        return page.get_by_role("textbox", name=re.compile(hint, re.I))
    except: pass
    return None

def _by_text(page: Page, hint: str):
    try:
        return page.get_by_text(re.compile(hint, re.I), exact=False).first
    except:
        return None

def _by_testid(page: Page, hint: str):
    try:
        return page.locator(f"[data-testid*='{hint}'],[data-test*='{hint}']").first
    except:
        return None

def _by_placeholder(page: Page, hint: str):
    try:
        return page.get_by_placeholder(re.compile(hint, re.I))
    except:
        return None

def _by_label(page: Page, hint: str):
    try:
        return page.get_by_label(re.compile(hint, re.I))
    except:
        return None

def _fallback_xpath(page: Page, hint: str):
    try:
        return page.locator(
            f"xpath=//*[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), '{hint.lower()}')]"
        ).first
    except:
        return None

# -------- high-level finders --------
def find_target(page: Page, hint: str):
    """Prefer structured signals first, generic text LAST."""
    strategies = (
        _by_accessibility,
        _by_label,
        _by_placeholder,
        _by_testid,
        _by_text,
        _fallback_xpath,
    )
    for strat in strategies:
        el = strat(page, hint)
        if el and el.count() > 0:
            return el
    return None

def find_in_frames(page: Page, hint: str):
    el = find_target(page, hint)
    if el and el.count() > 0:
        return el
    for fr in page.frames:
        try:
            el = (_by_accessibility(fr, hint) or _by_label(fr, hint) or _by_placeholder(fr, hint) or
                  _by_testid(fr, hint) or _by_text(fr, hint) or _fallback_xpath(fr, hint))
            if el and el.count() > 0:
                return el
        except:
            pass
    return None

# -------- input-specific resolution for fill() --------
def _input_guessers(page: Page, hint: str):
    h = hint.lower()
    cands = []
    if "username" in h or "user name" in h or "email" in h:
        cands += [
            page.locator("#user-name"),
            page.locator("[data-test='username']"),
            page.locator("input[name*='user'], input[name*='email']"),
        ]
    if "password" in h:
        cands += [
            page.locator("#password"),
            page.locator("[data-test='password']"),
            page.locator("input[type='password']"),
        ]
    if "zip" in h or "postal" in h:
        cands += [
            page.locator("#postal-code"),
            page.locator("[data-test='postalCode']"),
            page.locator("input[name*='zip'], input[id*='zip']"),
            page.locator("input[name*='postal'], input[id*='postal']"),
        ]
    if "address" in h:
        cands += [
            page.locator("textarea[ng-model*='Adress' i]"),
            page.locator("#address, #Address"),
            page.locator("textarea[name*='address' i], textarea[id*='address' i]"),
        ]
    for loc in cands:
        try:
            if loc and loc.count() > 0:
                return loc.first
        except:
            pass
    return None

def _by_aria_input(page: Page, hint: str):
    """Direct match on aria-label / aria-placeholder for input/textarea."""
    try:
        loc = page.locator(
            f"input[aria-label*='{hint}' i], textarea[aria-label*='{hint}' i], "
            f"input[aria-placeholder*='{hint}' i], textarea[aria-placeholder*='{hint}' i]"
        ).first
        if loc and loc.count() > 0:
            return loc
    except:
        pass
    return None

def _first_visible_textarea(page: Page):
    """Safe fallback: pick the first visible textarea if nothing else matched."""
    try:
        loc = page.locator("textarea")
        count = loc.count()
        if count == 1 and loc.first.is_visible():
            return loc.first
        # otherwise, pick first visible among a few
        for i in range(min(count, 6)):
            item = loc.nth(i)
            if item.is_visible():
                return item
    except:
        pass
    return None

def find_input(page: Page, hint: str):
    """Resolve an INPUT/TEXTAREA for fill() reliably."""
    # -1) Aliases
    try:
        aliases = load_aliases(page.url)
        key = (hint or "").lower()
        if key in aliases:
            sel = aliases[key]
            sels = sel if isinstance(sel, list) else [sel]
            for s in sels:
                loc = page.locator(s).first
                if loc and loc.count() > 0:
                    return loc
    except:
        pass
    # 0) ARIA label/placeholder (covers floating-label + placeholder=' ' cases)
    el = _by_aria_input(page, hint)
    if el:
        return el

    # 1) Placeholder & Label first
    for strat in (_by_placeholder, _by_label):
        el = strat(page, hint)
        if el and el.count() > 0:
            return el.first

    # 2) Common heuristics
    el = _input_guessers(page, hint)
    if el:
        return el

    # 3) ARIA textbox by name
    try:
        el = page.get_by_role("textbox", name=re.compile(hint, re.I))
        if el and el.count() > 0:
            return el.first
    except:
        pass

    # 4) data-testid/test
    try:
        sel = f"[data-testid*='{hint}'],[data-test*='{hint}']"
        el = page.locator(sel).first
        if el and el.count() > 0:
            try: update_aliases(page.url, hint, sel)
            except: pass
            return el
    except:
        pass

    # 5) Label → following input
    try:
        el = page.locator(
            f"xpath=(//label[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), '{hint.lower()}')]/following::input)[1]"
        ).first
        if el and el.count() > 0:
            return el
    except:
        pass

    # 5b) Label → following textarea
    try:
        el = page.locator(
            f"xpath=(//label[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), '{hint.lower()}')]/following::textarea)[1]"
        ).first
        if el and el.count() > 0:
            return el
    except:
        pass

    # 6) FINAL fallback: first visible textarea (handles generic 'Message')
    ta = _first_visible_textarea(page)
    if ta:
        return ta

    return None

# -------- adapters: combobox / date / file upload --------
def combo_select(page: Page, hint: str, value: str):
    rx = re.compile(hint, re.I)
    # 1) Native <select> by label/name/id
    sel = page.get_by_label(rx)
    if sel and sel.count() > 0 and sel.first.evaluate("e => e.tagName.toLowerCase()") == "select":
        try:
            sel.first.select_option(label=value)
            return
        except:
            pass
    # 1.1) Fallback to locating select by id/name containing hint
    try:
        sel2 = page.locator(f"select[id*='{hint}' i], select[name*='{hint}' i]").first
        if sel2 and sel2.count() > 0:
            sel2.select_option(label=value)
            return
    except:
        pass
    # 1.2) Fallback to locating select by placeholder
    try:
        sel3 = page.locator(f"select[placeholder*='{hint}' i]").first
        if sel3 and sel3.count() > 0:
            sel3.select_option(label=value)
            return
    except:
        pass

    # 2) Custom widgets (select2/msdd): click trigger, type, choose option
    use_custom = ("language" in hint.lower()) or ("select country" in hint.lower())
    trigger = None
    if use_custom:
        trigger = (
            page.locator("#msdd").first or
            page.locator(".select2-selection").first or
            page.get_by_role("combobox", name=rx).first
        )
    if trigger and trigger.count() > 0:
        trigger.click()
        try:
            typebox = page.locator(".select2-search__field, input[type='search']").first
            if typebox and typebox.count() > 0:
                typebox.fill(value)
            else:
                page.keyboard.type(value)
        except:
            page.keyboard.type(value)
        opts = page.get_by_role("option", name=re.compile(value, re.I))
        if opts.count() == 0:
            opts = page.get_by_text(re.compile(f"^{re.escape(value)}$", re.I))
        if opts.count() == 0:
            # select2 results list
            opts = page.locator(
                f".select2-results__option:has-text('{value}'), .select2-results li:has-text('{value}')"
            )
        if opts.count() == 0:
            # try open dropdown options container and search text nodes
            opts = page.locator(f".ui-autocomplete li:has-text('{value}')").first
            if opts and opts.count() > 0:
                opts.click()
                # Attempt to close dropdown after selection
                try:
                    page.keyboard.press("Escape")
                except:
                    pass
                return
        if opts.count() == 0:
            # Press Enter to confirm the first suggestion
            try:
                page.keyboard.press("Enter")
                page.keyboard.press("Escape")
                return
            except:
                pass
            raise RuntimeError(f"Option not found in combobox: {value}")
        opts.first.click()
        # Attempt to close dropdown after selection
        try:
            page.keyboard.press("Escape")
        except:
            pass
        # Fallback: click outside if still open
        try:
            page.mouse.click(5, 5)
        except:
            pass
        return

    # 3) Last resort: previous behavior on role option lists
    cb = page.get_by_role("combobox", name=rx)
    if cb.count() == 0:
        cb = find_in_frames(page, hint)
    if cb is None or cb.count() == 0:
        raise RuntimeError(f"Combobox not found: {hint}")
    cb.first.click()
    try:
        inner_input = cb.locator("input").first
        if inner_input.count() > 0:
            inner_input.fill(value)
        else:
            page.keyboard.type(value)
    except:
        page.keyboard.type(value)
    options = page.get_by_role("option", name=re.compile(value, re.I))
    if options.count() == 0:
        options = page.get_by_text(re.compile(f"^{re.escape(value)}$", re.I))
    if options.count() == 0:
        page.keyboard.press("End"); page.wait_for_timeout(80)
        page.keyboard.press("Home"); page.wait_for_timeout(80)
        options = page.get_by_role("option", name=re.compile(value, re.I))
    if options.count() == 0:
        raise RuntimeError(f"Option not found in combobox: {value}")
    options.first.click()

def date_set(page: Page, hint: str, iso_value: str):
    el = find_in_frames(page, hint) or page.locator("input[type='date']").first
    try:
        if el and el.count() > 0 and el.evaluate("e => e.type") == "date":
            el.fill(iso_value)
            el.dispatch_event("change")
            return
    except:
        pass

    # open popover calendar
    tgt = find_in_frames(page, hint) or _by_placeholder(page, hint) or _by_label(page, hint)
    tgt = tgt.first if tgt and hasattr(tgt, "first") else tgt
    if tgt is None or (hasattr(tgt, "count") and tgt.count() == 0):
        raise RuntimeError(f"Date field not found: {hint}")
    tgt.click()

    dt = datetime.fromisoformat(iso_value)

    def click_if_visible(selectors):
        for sel in selectors:
            btn = page.locator(sel)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                return True
        return False

    month_label = f"{dt.strftime('%B')} {dt.year}"
    for _ in range(24):
        if page.get_by_text(re.compile(f"^{re.escape(month_label)}$", re.I)).count() > 0:
            break
        if not click_if_visible(["button[aria-label*='Next']", "button[title*='Next']", "button:has-text('›')"]):
            click_if_visible(["button[aria-label*='Previous']", "button[title*='Prev']", "button:has-text('‹')"])
        page.wait_for_timeout(80)

    day = str(dt.day)
    cand = page.get_by_role("gridcell", name=re.compile(f"^{day}$")).first
    if cand.count() == 0:
        cand = page.get_by_text(re.compile(f"^{day}$")).first
    if cand.count() == 0:
        raise RuntimeError(f"Day not found in calendar: {iso_value}")
    cand.click()

def file_upload(page: Page, hint: str, file_path: str):
    input_el = page.locator("input[type='file']").first
    if input_el.count() == 0:
        btn = find_in_frames(page, hint) or page.get_by_role("button", name=re.compile(hint, re.I)).first
        if btn and btn.count() > 0:
            btn.click()
            page.wait_for_timeout(150)
        input_el = page.locator("input[type='file']").first
    if input_el.count() == 0:
        raise RuntimeError("File input not found after attempting to open chooser.")
    input_el.set_input_files(file_path)

# -------- strong clickable resolver --------
def find_clickable(page: Page, hint: str):
    """
    Strong resolver for click targets by visible label.
    Priority:
      1) role=button/link with accessible name
      2) CSS :has-text(...) for <button>, <a>, [role=button]
      3) data-testid / data-test match
      3.6) intent-based selectors for common actions (cart/checkout/continue/finish)
      4) generic text node fallback, then nearest clickable ancestor
    """
    # -1) Aliases
    try:
        aliases = load_aliases(page.url)
        key = (hint or "").lower()
        if key in aliases:
            sel = aliases[key]
            sels = sel if isinstance(sel, list) else [sel]
            for s in sels:
                loc = page.locator(s).first
                if loc.count() > 0 and loc.is_visible():
                    return loc
    except:
        pass
    rx = re.compile(hint, re.I)

    # 1) ARIA roles by accessible name
    for role in ("button", "link"):
        try:
            loc = page.get_by_role(role, name=rx)
            if loc.count() > 0 and loc.first.is_visible():
                return loc.first
        except:
            pass

    # 2) :has-text selectors
    try:
        loc = page.locator(f"button:has-text('{hint}')").first
        if loc.count() > 0 and loc.is_visible():
            return loc
    except: pass
    try:
        loc = page.locator(f"a:has-text('{hint}')").first
        if loc.count() > 0 and loc.is_visible():
            return loc
    except: pass
    try:
        loc = page.locator(f"[role=button]:has-text('{hint}')").first
        if loc.count() > 0 and loc.is_visible():
            return loc
    except: pass

    # 3) data-test(id)
    try:
        loc = page.locator(f"[data-testid*='{hint}'],[data-test*='{hint}']").first
        if loc.count() > 0 and loc.is_visible():
            try: update_aliases(page.url, hint, sel)
            except: pass
            return loc
    except: pass

    # 3.25) Inputs by id/name/placeholder/value (e.g., datepicker1/2)
    try:
        loc = page.locator(
            f"input[id*='{hint}' i], input[name*='{hint}' i], input[placeholder*='{hint}' i], input[value*='{hint}' i]"
        ).first
        if loc.count() > 0 and loc.is_visible():
            return loc
    except: pass

    # 3.5) Attributes: id/name/title/class on common clickable elements
    try:
        loc = page.locator(
            f"a[id*='{hint}' i], a[name*='{hint}' i], a[title*='{hint}' i], a[class*='{hint}' i], "
            f"button[id*='{hint}' i], button[name*='{hint}' i], button[title*='{hint}' i], button[class*='{hint}' i], "
            f"[role=button][id*='{hint}' i], [data-testid*='{hint}'], [data-test*='{hint}'], [role=link][id*='{hint}' i]"
        ).first
        if loc.count() > 0 and loc.is_visible():
            try: update_aliases(page.url, hint, sel)
            except: pass
            return loc
    except: pass

    # 3.6) Intent-based quick selectors for common e-commerce actions
    try:
        h = (hint or "").lower()
        if any(t in h for t in ["cart", "basket"]):
            sel = "[data-test='shopping-cart-link'], .shopping_cart_link, #shopping_cart_container a, a[href*='cart' i], [aria-label*='cart' i]"
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                try: update_aliases(page.url, hint, sel)
                except: pass
                return loc
        if "checkout" in h:
            sel = "[data-test='checkout'], #checkout, button:has-text('Checkout'), a:has-text('Checkout')"
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                try: update_aliases(page.url, hint, sel)
                except: pass
                return loc
        if "continue" in h:
            sel = "[data-test='continue'], #continue, button:has-text('Continue'), a:has-text('Continue')"
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                try: update_aliases(page.url, hint, sel)
                except: pass
                return loc
        if "finish" in h or "complete" in h:
            sel = "[data-test='finish'], #finish, button:has-text('Finish'), a:has-text('Finish')"
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                try: update_aliases(page.url, hint, sel)
                except: pass
                return loc
    except:
        pass

    # 4) Text -> clickable ancestor
    try:
        node = page.get_by_text(rx, exact=False).first
        if node and node.count() > 0 and node.is_visible():
            anc = node.locator("xpath=ancestor-or-self::*[self::button or self::a or @role='button'][1]").first
            if anc and anc.count() > 0 and anc.is_visible():
                return anc
            return node
    except:
        pass

    # 5) Tokenized attribute fallback (handles 'Cart icon' → token 'cart')
    try:
        import re as _re
        tokens = [t for t in _re.findall(r"[a-z0-9]+", (hint or "").lower()) if len(t) >= 3]
        for t in tokens:
            sel = (
                f"a[id*='{t}' i], a[name*='{t}' i], a[title*='{t}' i], a[class*='{t}' i], "
                f"button[id*='{t}' i], button[name*='{t}' i], button[title*='{t}' i], button[class*='{t}' i], "
                f"[role=button][id*='{t}' i], [data-testid*='{t}'], [data-test*='{t}'], [role=link][id*='{t}' i], "
                f"a[href*='{t}' i]"
            )
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                try: update_aliases(page.url, hint, sel)
                except: pass
                return loc
    except:
        pass

    return None

def _find_checkbox(page, hint: str):
    raw = (hint or "").strip()
    # Normalize common suffix words that are not part of the accessible name
    norm = re.sub(r"\b(checkbox|radio|button|option|select|multiselect)\b", "", raw, flags=re.I).strip()
    rx = re.compile(norm or raw or "", re.I)
    try:
        loc = page.get_by_role("checkbox", name=rx)
        if loc.count() > 0:
            return loc.first
    except:
        pass
    # Prefer direct input matches by name/aria-label first
    try:
        loc = page.locator(
            f"input[type='checkbox'][name*='{norm}' i], input[type='checkbox'][aria-label*='{norm}' i], input[type='checkbox'][value*='{norm}' i], input[type='checkbox'][title*='{norm}' i]"
        ).first
        if loc and loc.count() > 0:
            return loc
    except:
        pass
    # Handle label-wrapped checkbox: select descendant input within label containing the hint
    try:
        loc = page.locator(
            "xpath=(//label[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), "
            + f"'{(norm or '').lower()}')]//input[@type='checkbox'])[1]"
        ).first
        if loc and loc.count() > 0:
            return loc
    except:
        pass
    try:
        loc = page.locator(
            "xpath=(//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), "
            + f"'{(norm or '').lower()}')]/following::input[@type='checkbox'] | "
            "//label[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), "
            + f"'{(norm or '').lower()}')]/preceding::input[@type='checkbox'])[1]"
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

def _find_radio(page, hint: str):
    raw = (hint or "").strip()
    norm = re.sub(r"\b(checkbox|radio|button|option|select|multiselect)\b", "", raw, flags=re.I).strip()
    rx = re.compile(norm or raw or "", re.I)
    try:
        loc = page.get_by_role("radio", name=rx)
        if loc.count() > 0:
            return loc.first
    except:
        pass
    try:
        loc = page.locator(
            f"input[type='radio'][name*='{norm}' i], input[type='radio'][aria-label*='{norm}' i], input[type='radio'][value*='{norm}' i], input[type='radio'][title*='{norm}' i]"
        ).first
        if loc and loc.count() > 0:
            return loc
    except:
        pass
    try:
        loc = page.locator(
            "xpath=(//label[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'), "
            + f"'{(norm or '').lower()}')]//input[@type='radio'])[1]"
        ).first
        if loc and loc.count() > 0:
            return loc
    except:
        pass
    # Token fallback: try individual words like 'male'/'female'
    try:
        tokens = [t for t in re.findall(r"[a-zA-Z]+", norm or raw) if len(t) >= 3]
        for t in tokens:
            loc = page.get_by_role("radio", name=re.compile(t, re.I))
            if loc.count() > 0:
                return loc.first
            loc = page.locator(
                f"input[type='radio'][value*='{t}' i], input[type='radio'][aria-label*='{t}' i]"
            ).first
            if loc and loc.count() > 0:
                return loc
    except:
        pass
    return None
