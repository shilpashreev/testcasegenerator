"""Streamlit UI for the Test Case Generator.

Thin presentation layer: it builds a ProviderConfig from sidebar input, asks the
factory for a provider, and delegates all work to GeneratorService. No business
logic lives here.
"""

import os

import pandas as pd
import streamlit as st

from testcasegen import (
    DEFAULT_BASE_URLS,
    GeneratorService,
    MODEL_SUGGESTIONS,
    ProviderConfig,
    ProviderType,
)
from testcasegen.domain import (
    ACTION_ERROR,
    ACTION_GENERATED,
    ACTION_UNCHANGED,
    ACTION_UPDATED,
    TEST_CASE_FIELDS,
)
from testcasegen.providers import LLMError, create_provider
from testcasegen.storage import ExcelRepository
from testcasegen.samples import load_sample_text

st.set_page_config(page_title="Test Case Generator", page_icon="🧪", layout="wide")

st.markdown(
    """
<style>
.app-header{background:linear-gradient(135deg,#0d2c4e 0%,#1565c0 100%);color:#fff;padding:22px 28px;border-radius:12px;margin-bottom:20px;}
.app-header h1{margin:0 0 4px;font-size:1.85rem;}
.app-header p{margin:0;opacity:.85;font-size:.92rem;}
.metric-row{display:flex;gap:10px;margin:12px 0;}
.mtile{flex:1;background:#fff;border:1px solid #dde3ea;border-radius:10px;padding:12px 16px;text-align:center;}
.mtile .val{font-size:1.9rem;font-weight:700;color:#1565c0;}
.mtile .lbl{font-size:.75rem;color:#5a6474;margin-top:2px;}
.badge{display:inline-block;padding:3px 12px;border-radius:20px;font-size:.8rem;font-weight:600;margin-bottom:8px;}
.badge-gen{background:#d4f1d4;color:#1a6b1a;}.badge-upd{background:#fff3cc;color:#7a5500;}
.badge-same{background:#ddeeff;color:#0d4080;}.badge-err{background:#fde8e8;color:#9b1c1c;}
div[data-testid="stTextArea"] textarea{font-family:monospace;font-size:.82rem;}
</style>
""",
    unsafe_allow_html=True,
)

_DEFAULTS = {"json_text": "", "last_result": None, "last_jira_id": "", "models_cache": {}}
for k, v in _DEFAULTS.items():
    st.session_state.setdefault(k, v)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def badge_html(action: str) -> str:
    mapping = {
        ACTION_GENERATED: ("Generated", "badge-gen"),
        ACTION_UPDATED: ("Updated", "badge-upd"),
        ACTION_UNCHANGED: ("Unchanged", "badge-same"),
        ACTION_ERROR: ("Error", "badge-err"),
    }
    label, cls = mapping.get(action, ("Done", "badge-gen"))
    return f'<span class="badge {cls}">{label}</span>'


def to_df(test_cases) -> pd.DataFrame:
    headers = ["Test ID", "Jira ID", "Test Title", "Description", "Steps", "Data", "Expected Result"]
    rows = [tc.to_dict() if hasattr(tc, "to_dict") else tc for tc in test_cases]
    df = pd.DataFrame(rows)
    for c in TEST_CASE_FIELDS:
        if c not in df.columns:
            df[c] = ""
    df = df[TEST_CASE_FIELDS]
    df.columns = headers
    return df


def provider_picker() -> tuple[ProviderConfig, ExcelRepository, str]:
    """Render sidebar provider controls and return (config, repo, output_dir)."""
    st.header("⚙️ Model & Settings")

    type_labels = {p: p.label for p in ProviderType}
    selected = st.selectbox(
        "LLM Provider",
        list(ProviderType),
        format_func=lambda p: type_labels[p],
        help="Anthropic (cloud) or a local open-source model via Ollama / OpenAI-compatible server.",
    )

    api_key, base_url = "", ""
    if selected == ProviderType.ANTHROPIC:
        api_key = st.text_input(
            "Anthropic API Key", type="password",
            value=os.environ.get("ANTHROPIC_API_KEY", ""), help="Starts with sk-ant-…",
        )
    else:
        base_url = st.text_input("Server Base URL", value=DEFAULT_BASE_URLS.get(selected, ""))
        if selected == ProviderType.OPENAI_COMPATIBLE:
            api_key = st.text_input(
                "API Key (optional)", type="password",
                help="Leave blank for LM Studio / llama.cpp; required by some vLLM setups.",
            )

    # Model selection: prefer live list from the server, fall back to suggestions.
    live_models = []
    if selected != ProviderType.ANTHROPIC and base_url:
        if st.button("🔄 Refresh model list", use_container_width=True):
            try:
                probe = create_provider(
                    ProviderConfig(type=selected, model="", api_key=api_key, base_url=base_url)
                )
                live_models = probe.list_models()
                st.session_state.models_cache[selected.value] = live_models
            except LLMError as exc:
                st.warning(str(exc))
        live_models = st.session_state.models_cache.get(selected.value, live_models)

    options = live_models or MODEL_SUGGESTIONS.get(selected, [])
    if options:
        model = st.selectbox("Model", options)
    else:
        model = st.text_input("Model", placeholder="e.g. gemma2 / llama3.1")

    with st.expander("Advanced"):
        max_tokens = st.slider("Max output tokens", 1024, 8192, 4096, step=512)
        temperature = st.slider("Temperature", 0.0, 1.0, 0.2, step=0.1)
        output_dir = st.text_input("Output directory", value="./test_cases")

    config = ProviderConfig(
        type=selected, model=model, api_key=api_key, base_url=base_url,
        max_tokens=max_tokens, temperature=temperature,
    )

    # Connection status (cheap health check for local servers).
    if selected != ProviderType.ANTHROPIC and base_url:
        try:
            ok, detail = create_provider(config).health()
            st.success(detail) if ok else st.error(detail)
        except LLMError as exc:
            st.error(str(exc))

    return config, ExcelRepository(output_dir), output_dir


# ──────────────────────────────────────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
<div class="app-header">
  <h1>🧪 Test Case Generator</h1>
  <p>Requirement-based test cases from Jira JSON · pluggable LLM (Claude / Gemma / Llama) · per-ticket Excel</p>
</div>
""",
    unsafe_allow_html=True,
)

with st.sidebar:
    config, repo, output_dir = provider_picker()
    st.divider()
    existing_ids = repo.list_jira_ids()
    if existing_ids:
        st.markdown("**Processed Tickets**")
        for jid in existing_ids:
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"`{jid}`")
            if c2.button("Load", key=f"load_{jid}"):
                tcs, _ = repo.load(jid)
                st.session_state.last_result = {"test_cases": tcs, "action": ACTION_UNCHANGED,
                                                "message": f"Loaded {len(tcs)} test cases.", "from_disk": True}
                st.session_state.last_jira_id = jid
                st.rerun()


# ──────────────────────────────────────────────────────────────────────────────
# Main layout
# ──────────────────────────────────────────────────────────────────────────────
left, right = st.columns([5, 7], gap="large")

with left:
    st.subheader("📥 Jira Input")
    jira_id = st.text_input("Jira ID *", placeholder="e.g., PROJ-123")

    tab_paste, tab_upload = st.tabs(["Paste JSON", "Upload JSON File"])
    with tab_paste:
        if st.button("📋 Load Sample", use_container_width=True):
            st.session_state.json_text = load_sample_text()
            st.rerun()
        json_text = st.text_area(
            "Jira JSON", value=st.session_state.json_text, height=360,
            key="json_textarea", label_visibility="collapsed",
        )
        st.session_state.json_text = json_text
    with tab_upload:
        uploaded = st.file_uploader("Upload .json", type=["json"])
        if uploaded:
            st.session_state.json_text = uploaded.read().decode("utf-8")
            st.success(f"Loaded: {uploaded.name}")

    need_key = config.type == ProviderType.ANTHROPIC and not config.api_key
    if need_key:
        st.warning("Enter your Anthropic API Key in the sidebar.")
    ready = bool(config.model and jira_id.strip() and st.session_state.json_text.strip() and not need_key)
    generate = st.button("🚀 Generate Test Cases", type="primary", use_container_width=True, disabled=not ready)

    if st.session_state.last_result and st.button("🗑️ Clear Results", use_container_width=True):
        st.session_state.last_result = None
        st.session_state.last_jira_id = ""
        st.rerun()


with right:
    st.subheader("📊 Test Cases")

    if generate and ready:
        import json as _json

        try:
            jira_data = _json.loads(st.session_state.json_text.strip())
        except _json.JSONDecodeError as exc:
            st.error(f"Invalid JSON: {exc}")
            st.stop()

        jira_id_clean = jira_id.strip()
        if not jira_data.get("id") and not jira_data.get("key"):
            jira_data["id"] = jira_id_clean

        logs: list[str] = []
        with st.status(f"Processing {jira_id_clean} with {config.model}…", expanded=True) as status:
            try:
                provider = create_provider(config)
                service = GeneratorService(provider, repo)
                result = service.process(jira_id_clean, jira_data, progress_cb=logs.append)
                for m in logs:
                    st.write(f"→ {m}")
                status.update(
                    label="Failed." if result.action == ACTION_ERROR else "Complete!",
                    state="error" if result.action == ACTION_ERROR else "complete",
                )
                st.session_state.last_result = {
                    "test_cases": result.test_cases, "action": result.action,
                    "message": result.message, "stats": result.stats, "usage": result.usage,
                }
                st.session_state.last_jira_id = jira_id_clean
            except LLMError as exc:
                status.update(label="Provider error.", state="error")
                st.error(str(exc))
                st.stop()
            except Exception as exc:  # noqa: BLE001
                status.update(label="Error.", state="error")
                st.error(f"Unexpected error: {exc}")
                st.stop()

    res = st.session_state.last_result
    if res:
        action = res.get("action", ACTION_GENERATED)
        test_cases = res.get("test_cases", [])
        st.markdown(badge_html(action), unsafe_allow_html=True)

        msg = res.get("message", "")
        {ACTION_ERROR: st.error, ACTION_UNCHANGED: st.info, ACTION_UPDATED: st.warning}.get(
            action, st.success
        )(msg)

        stats = res.get("stats")
        if stats:
            st.markdown(
                f"""<div class="metric-row">
<div class="mtile"><div class="val">{stats.total}</div><div class="lbl">Total</div></div>
<div class="mtile"><div class="val">{stats.new}</div><div class="lbl">New</div></div>
<div class="mtile"><div class="val">{stats.updated}</div><div class="lbl">Updated</div></div>
<div class="mtile"><div class="val">{stats.kept}</div><div class="lbl">Kept</div></div>
</div>""",
                unsafe_allow_html=True,
            )

        usage = res.get("usage")
        if usage and (usage.input_tokens or usage.output_tokens):
            cached = f" · {usage.cache_read_tokens} cached" if usage.cache_read_tokens else ""
            st.caption(f"🔢 Tokens — in: {usage.input_tokens}{cached} · out: {usage.output_tokens}")

        if test_cases:
            st.dataframe(to_df(test_cases), use_container_width=True, height=420, hide_index=True)
            xlsx_path = repo.path_for(st.session_state.last_jira_id)
            if os.path.exists(xlsx_path):
                with open(xlsx_path, "rb") as fh:
                    st.download_button(
                        "📥 Download Excel", fh.read(),
                        file_name=f"{st.session_state.last_jira_id}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
        elif action != ACTION_ERROR:
            st.warning("No test cases returned — the requirements may lack testable detail.")
    else:
        st.markdown(
            """
<div style="text-align:center;padding:90px 30px;background:#fff;border-radius:12px;border:2px dashed #c8d6e5;color:#7a8fa6;">
  <div style="font-size:3rem">📝</div>
  <h3 style="margin:12px 0 8px;color:#4a5e74">No Test Cases Yet</h3>
  <p style="margin:0">Pick a provider, enter a Jira ID, paste the ticket JSON,<br>then click <strong>Generate Test Cases</strong>.</p>
</div>
""",
            unsafe_allow_html=True,
        )
