import os
from urllib.parse import urlparse

try:
    import yaml
except Exception:
    yaml = None

# ---- hint alias loader ----
_ALIASES_CACHE = {"path": None, "mtime": None, "data": {}}

def _read_yaml(path: str):
    if not os.path.exists(path):
        return {}
    if yaml is None:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data
    except Exception:
        return {}

def load_aliases(page_url: str):
    """Load hint→selector aliases from fixtures/aliases.yaml or aliases.yaml.
    Structure:
      global: { hint: selector | [selectors] }
      <host>: { hint: selector | [selectors] }
    Returns a dict with lowercased hints.
    """
    # Reuse cache if file unchanged
    candidate_paths = [
        os.path.join("fixtures", "aliases.yaml"),
        os.path.join("aliases.yaml"),
    ]
    alias_path = next((p for p in candidate_paths if os.path.exists(p)), None)
    cache_path = _ALIASES_CACHE.get("path")
    cache_mtime = _ALIASES_CACHE.get("mtime")
    current_mtime = None
    if alias_path and os.path.exists(alias_path):
        try:
            current_mtime = os.path.getmtime(alias_path)
        except Exception:
            current_mtime = None
    if alias_path != cache_path or (current_mtime is not None and current_mtime != cache_mtime):
        data = _read_yaml(alias_path) if alias_path else {}
        _ALIASES_CACHE["path"] = alias_path
        _ALIASES_CACHE["mtime"] = current_mtime
        _ALIASES_CACHE["data"] = data if isinstance(data, dict) else {}

    data = _ALIASES_CACHE.get("data") or {}
    host = ""
    try:
        host = urlparse(page_url or "").hostname or ""
    except Exception:
        host = ""

    def norm_map(d):
        if not isinstance(d, dict):
            return {}
        return {str(k).lower(): v for k, v in d.items()}

    global_map = norm_map(data.get("global") or data.get("default") or {})
    host_map = norm_map(data.get(host) or {})
    merged = {**global_map, **host_map}
    return merged

def update_aliases(page_url: str, hint: str, selector: str):
    """Persist a learned hint→selector mapping to fixtures/aliases.yaml.
    - Writes under host section keyed by URL hostname
    - Keeps existing entries; avoids duplicates
    - No-op if yaml is unavailable
    """
    if yaml is None:
        return False
    hint_lc = (hint or "").strip().lower()
    if not hint_lc or not selector:
        return False

    candidate_paths = [
        os.path.join("fixtures", "aliases.yaml"),
        os.path.join("aliases.yaml"),
    ]
    alias_path = next((p for p in candidate_paths if os.path.exists(p)), None)
    if alias_path is None:
        # prefer fixtures/aliases.yaml
        os.makedirs("fixtures", exist_ok=True)
        alias_path = os.path.join("fixtures", "aliases.yaml")

    data = _read_yaml(alias_path) if alias_path else {}
    if not isinstance(data, dict):
        data = {}

    try:
        host = urlparse(page_url or "").hostname or ""
    except Exception:
        host = ""
    if host not in data or not isinstance(data.get(host), dict):
        data[host] = {}

    existing = data[host].get(hint_lc)
    if existing is None:
        data[host][hint_lc] = selector
    else:
        if isinstance(existing, list):
            if selector not in existing:
                existing.append(selector)
        else:
            if existing != selector:
                data[host][hint_lc] = [existing, selector]

    try:
        with open(alias_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=True, allow_unicode=True)
        # refresh cache
        _ALIASES_CACHE["path"] = alias_path
        try:
            _ALIASES_CACHE["mtime"] = os.path.getmtime(alias_path)
        except Exception:
            _ALIASES_CACHE["mtime"] = None
        _ALIASES_CACHE["data"] = data
        return True
    except Exception:
        return False
