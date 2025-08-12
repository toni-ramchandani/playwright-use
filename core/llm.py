import os
from dotenv import load_dotenv

load_dotenv()

_PROVIDER = os.getenv("LLM_PROVIDER", "azure-openai").strip().lower()
_DEFAULT_TEMP = float(os.getenv("LLM_TEMPERATURE", "0.2"))

# Common message format: list[{role: system|user|assistant, content: str}]

def chat(messages, temperature: float = None) -> str:
    temp = _DEFAULT_TEMP if temperature is None else temperature
    provider = _PROVIDER

    if provider in ("azure-openai", "azure"):
        return _chat_azure_openai(messages, temp)
    if provider in ("openai",):
        return _chat_openai(messages, temp)
    if provider in ("anthropic", "claude"):
        return _chat_anthropic(messages, temp)
    if provider in ("groq",):
        return _chat_groq(messages, temp)
    raise RuntimeError(f"Unsupported LLM_PROVIDER: {provider}")

# ---- Azure OpenAI ----

def _chat_azure_openai(messages, temperature: float) -> str:
    import openai
    openai.api_type = "azure"
    openai.api_key = os.getenv("AZURE_OPENAI_API_KEY")
    openai.api_base = os.getenv("AZURE_OPENAI_ENDPOINT")
    openai.api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
    if not (openai.api_key and openai.api_base and deployment):
        raise RuntimeError("Missing Azure OpenAI env: AZURE_OPENAI_API_KEY, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT")
    resp = openai.ChatCompletion.create(
        engine=deployment,
        messages=messages,
        temperature=temperature,
    )
    return resp["choices"][0]["message"]["content"].strip()

# ---- OpenAI (api.openai.com) ----

def _chat_openai(messages, temperature: float) -> str:
    import openai
    openai.api_type = "open_ai"
    openai.api_key = os.getenv("OPENAI_API_KEY")
    # Optional self-hosted proxy/base
    base = os.getenv("OPENAI_BASE")
    if base:
        openai.api_base = base
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if not openai.api_key:
        raise RuntimeError("Missing OPENAI_API_KEY")
    resp = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    return resp["choices"][0]["message"]["content"].strip()

# ---- Anthropic (Claude) ----

def _chat_anthropic(messages, temperature: float) -> str:
    try:
        import anthropic
    except Exception:
        raise RuntimeError("anthropic package not installed. Install with: pip install 'anthropic>=0.34' or `pip install .[anthropic]`")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")
    if not api_key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY")

    client = anthropic.Anthropic(api_key=api_key)
    sys_msg = ""
    conv = []
    for m in messages:
        role = (m.get("role") or "").lower()
        content = str(m.get("content") or "")
        if role == "system":
            sys_msg = content if not sys_msg else (sys_msg + "\n" + content)
        elif role in ("user", "assistant"):
            conv.append({"role": role, "content": [{"type": "text", "text": content}]})
    if not conv or conv[-1]["role"] != "user":
        # Ensure last is user per Claude API expectations
        conv.append({"role": "user", "content": [{"type": "text", "text": "Continue."}]})
    resp = client.messages.create(
        model=model,
        system=sys_msg or None,
        messages=conv,
        temperature=temperature,
        max_tokens=int(os.getenv("ANTHROPIC_MAX_TOKENS", "1024")),
    )
    # Concatenate text parts
    parts = []
    for b in resp.content:
        if getattr(b, "type", "") == "text":
            parts.append(getattr(b, "text", ""))
        elif isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text", ""))
    return "".join(parts).strip()

# ---- Groq (OpenAI-compatible) ----

def _chat_groq(messages, temperature: float) -> str:
    try:
        from groq import Groq
    except Exception:
        raise RuntimeError("groq package not installed. Install with: pip install 'groq>=0.8' or `pip install .[groq]`")
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv("GROQ_MODEL", "llama3-8b-8192")
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY")
    client = Groq(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content.strip()
