import streamlit as st
import json
import os
import pandas as pd
from pathlib import Path
import anthropic

from test_generator import TestCaseGenerator
from excel_manager import ExcelManager

# ──────────────────────────────────────────────────────────────────────────────
# Page config
# ──────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Test Case Generator",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
/* Header banner */
.app-header {
    background: linear-gradient(135deg, #0d2c4e 0%, #1565c0 100%);
    color: #fff;
    padding: 22px 28px;
    border-radius: 12px;
    margin-bottom: 20px;
}
.app-header h1 { margin: 0 0 4px; font-size: 1.85rem; }
.app-header p  { margin: 0; opacity: .85; font-size: .92rem; }

/* Metric tiles */
.metric-row { display: flex; gap: 10px; margin: 12px 0; }
.mtile {
    flex: 1; background: #fff; border: 1px solid #dde3ea;
    border-radius: 10px; padding: 12px 16px; text-align: center;
}
.mtile .val { font-size: 1.9rem; font-weight: 700; color: #1565c0; }
.mtile .lbl { font-size: .75rem; color: #5a6474; margin-top: 2px; }

/* Status badges */
.badge {
    display: inline-block; padding: 3px 12px; border-radius: 20px;
    font-size: .8rem; font-weight: 600; margin-bottom: 8px;
}
.badge-gen  { background:#d4f1d4; color:#1a6b1a; }
.badge-upd  { background:#fff3cc; color:#7a5500; }
.badge-same { background:#ddeeff; color:#0d4080; }
.badge-err  { background:#fde8e8; color:#9b1c1c; }

/* Monospace textarea */
div[data-testid="stTextArea"] textarea { font-family: monospace; font-size: .82rem; }
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# Session state
# ──────────────────────────────────────────────────────────────────────────────
_DEFAULTS = {
    "json_text": "",
    "last_result": None,
    "last_jira_id": "",
    "log_lines": [],
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def load_sample() -> str:
    p = Path(__file__).parent / "sample_jira.json"
    if p.exists():
        return p.read_text(encoding="utf-8")
    return json.dumps({
        "id": "PROJ-101",
        "summary": "User Login and Authentication",
        "type": "Story",
        "description": "As a user I want to log in with email and password.",
        "acceptance_criteria": [
            "Valid credentials grant access",
            "Invalid credentials show a generic error",
            "Account locks after 5 failed attempts",
        ],
        "attachments": [],
    }, indent=2)


def badge_html(action: str) -> str:
    mapping = {
        "generated": ("Generated", "badge-gen"),
        "updated":   ("Updated",   "badge-upd"),
        "unchanged": ("Unchanged", "badge-same"),
        "error":     ("Error",     "badge-err"),
    }
    label, cls = mapping.get(action, ("Done", "badge-gen"))
    return f'<span class="badge {cls}">{label}</span>'


def to_df(test_cases: list) -> pd.DataFrame:
    col_map = {
        "test_id":        "Test ID",
        "jira_id":        "Jira ID",
        "test_title":     "Test Title",
        "description":    "Description",
        "steps":          "Steps",
        "data":           "Data",
        "expected_result":"Expected Result",
    }
    df = pd.DataFrame(test_cases)
    for c in col_map:
        if c not in df.columns:
            df[c] = ""
    df = df[list(col_map.keys())]
    return df.rename(columns=col_map)


def validate_json_structure(data: dict) -> list:
    """Return a list of warnings for missing/empty fields."""
    warnings = []
    if not data.get("summary") and not data.get("fields", {}).get("summary"):
        warnings.append("No 'summary' field found.")
    has_desc = data.get("description") or data.get("fields", {}).get("description")
    has_ac   = data.get("acceptance_criteria") or data.get("fields", {}).get("acceptanceCriteria")
    has_att  = data.get("attachments") or data.get("attachment") or \
               data.get("fields", {}).get("attachments") or data.get("fields", {}).get("attachment")
    if not any([has_desc, has_ac, has_att]):
        warnings.append(
            "No description, acceptance_criteria, or attachments found — "
            "test cases will be minimal or empty."
        )
    return warnings

# ──────────────────────────────────────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="app-header">
    <h1>🧪 Test Case Generator</h1>
    <p>Generates requirement-based test cases from Jira JSON &rarr; exports to per-ticket Excel files</p>
</div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Settings")
    api_key = st.text_input(
        "Anthropic API Key",
        type="password",
        value=os.environ.get("ANTHROPIC_API_KEY", ""),
        help="Starts with sk-ant-…",
    )
    output_dir = st.text_input(
        "Output Directory",
        value="./test_cases",
        help="Where Excel files are saved (one per Jira ID)",
    )

    st.divider()
    st.markdown("**How it works**")
    st.markdown("""
1. Enter a Jira ID and paste the ticket JSON
2. Click **Generate** — AI reads *only* the Jira content
3. If tests already exist for this ticket:
   - Same requirements → no rewrite, shows existing
   - Changed requirements → updates affected tests
   - New requirements → adds new tests
4. Download the formatted `.xlsx`
    """)

    # History panel
    st.divider()
    em_side = ExcelManager(output_dir)
    existing_ids = em_side.list_jira_ids()
    if existing_ids:
        st.markdown("**Processed Tickets**")
        for jid in existing_ids:
            col_a, col_b = st.columns([3, 1])
            col_a.markdown(f"`{jid}`")
            if col_b.button("Load", key=f"load_{jid}", help=f"View existing tests for {jid}"):
                data = em_side.load_existing(jid)
                st.session_state.last_result = {
                    "message": f"Loaded {len(data['test_cases'])} existing test cases from Excel.",
                    "test_cases": data["test_cases"],
                    "action": "unchanged",
                    "stats": {
                        "total": len(data["test_cases"]),
                        "new": 0, "updated": 0, "kept": len(data["test_cases"]),
                    },
                }
                st.session_state.last_jira_id = jid
                st.rerun()

# ──────────────────────────────────────────────────────────────────────────────
# Main layout
# ──────────────────────────────────────────────────────────────────────────────
left, right = st.columns([5, 7], gap="large")

# ── LEFT ──────────────────────────────────────────────────────────────────────
with left:
    st.subheader("📥 Jira Input")

    jira_id = st.text_input(
        "Jira ID *",
        placeholder="e.g., PROJ-123",
        help="Ticket identifier — used as the Excel filename.",
    )

    tab_paste, tab_upload = st.tabs(["Paste JSON", "Upload JSON File"])

    with tab_paste:
        btn_col, _ = st.columns([1, 3])
        with btn_col:
            if st.button("📋 Load Sample", use_container_width=True):
                st.session_state.json_text = load_sample()
                st.rerun()

        json_text = st.text_area(
            "Jira JSON",
            value=st.session_state.json_text,
            height=370,
            placeholder='{\n  "id": "PROJ-123",\n  "summary": "...",\n  "description": "...",\n  "acceptance_criteria": [...]\n}',
            key="json_textarea",
            label_visibility="collapsed",
        )
        st.session_state.json_text = json_text

    with tab_upload:
        uploaded = st.file_uploader("Upload .json file", type=["json"])
        if uploaded:
            content = uploaded.read().decode("utf-8")
            st.session_state.json_text = content
            st.success(f"Loaded: {uploaded.name}")

    if not api_key:
        st.warning("Enter your Anthropic API Key in the sidebar.")

    ready = bool(api_key and jira_id.strip() and st.session_state.json_text.strip())

    generate = st.button(
        "🚀 Generate Test Cases",
        type="primary",
        use_container_width=True,
        disabled=not ready,
    )

    if st.session_state.last_result:
        if st.button("🗑️ Clear Results", use_container_width=True):
            st.session_state.last_result = None
            st.session_state.last_jira_id = ""
            st.session_state.log_lines = []
            st.rerun()

# ── RIGHT ─────────────────────────────────────────────────────────────────────
with right:
    st.subheader("📊 Test Cases")

    # ── Run generation ────────────────────────────────────────────────
    if generate and ready:
        raw_json = st.session_state.json_text.strip()
        jira_id_clean = jira_id.strip()

        # Parse JSON
        try:
            jira_data = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            st.error(f"Invalid JSON: {exc}")
            st.stop()

        # Inject jira_id if missing
        if not jira_data.get("id") and not jira_data.get("key"):
            jira_data["id"] = jira_id_clean

        # Structural warnings
        warns = validate_json_structure(jira_data)
        for w in warns:
            st.warning(f"⚠️ {w}")

        # Collect progress messages
        log_msgs = []

        def on_progress(msg: str):
            log_msgs.append(msg)

        with st.status(f"Processing {jira_id_clean}…", expanded=True) as status:
            try:
                generator = TestCaseGenerator(api_key, output_dir)
                result = generator.process_jira(jira_id_clean, jira_data, progress_cb=on_progress)

                for msg in log_msgs:
                    st.write(f"→ {msg}")

                if result["action"] == "error":
                    status.update(label="Failed.", state="error")
                else:
                    status.update(label="Complete!", state="complete")

                st.session_state.last_result = result
                st.session_state.last_jira_id = jira_id_clean
                st.session_state.log_lines = log_msgs

            except anthropic.AuthenticationError:
                status.update(label="Authentication failed.", state="error")
                st.error("Invalid API key. Check the key in the sidebar.")
                st.stop()
            except Exception as exc:
                status.update(label="Error.", state="error")
                st.error(f"Unexpected error: {exc}")
                st.stop()

    # ── Display result ────────────────────────────────────────────────
    result = st.session_state.last_result
    if result:
        action = result.get("action", "generated")
        test_cases = result.get("test_cases", [])
        stats = result.get("stats", {})
        jira_label = st.session_state.last_jira_id

        st.markdown(badge_html(action), unsafe_allow_html=True)

        if action == "error":
            st.error(result["message"])
        elif action == "unchanged":
            st.info(result["message"])
        elif action == "updated":
            st.warning(result["message"])
        else:
            st.success(result["message"])

        # Metric tiles
        total   = stats.get("total",   len(test_cases))
        new_ct  = stats.get("new",     0)
        upd_ct  = stats.get("updated", 0)
        kept_ct = stats.get("kept",    0)
        st.markdown(f"""
        <div class="metric-row">
            <div class="mtile"><div class="val">{total}</div><div class="lbl">Total</div></div>
            <div class="mtile"><div class="val">{new_ct}</div><div class="lbl">New</div></div>
            <div class="mtile"><div class="val">{upd_ct}</div><div class="lbl">Updated</div></div>
            <div class="mtile"><div class="val">{kept_ct}</div><div class="lbl">Kept</div></div>
        </div>
        """, unsafe_allow_html=True)

        if test_cases:
            df = to_df(test_cases)
            st.dataframe(
                df,
                use_container_width=True,
                height=430,
                column_config={
                    "Test ID":         st.column_config.TextColumn(width="small"),
                    "Jira ID":         st.column_config.TextColumn(width="small"),
                    "Test Title":      st.column_config.TextColumn(width="medium"),
                    "Description":     st.column_config.TextColumn(width="medium"),
                    "Steps":           st.column_config.TextColumn(width="large"),
                    "Data":            st.column_config.TextColumn(width="medium"),
                    "Expected Result": st.column_config.TextColumn(width="large"),
                },
                hide_index=True,
            )

            excel_path = os.path.join(output_dir, f"{jira_label}.xlsx")
            if os.path.exists(excel_path):
                with open(excel_path, "rb") as fh:
                    st.download_button(
                        label="📥 Download Excel",
                        data=fh.read(),
                        file_name=f"{jira_label}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
        else:
            if action != "error":
                st.warning("No test cases returned. The requirements may lack testable details.")

    else:
        st.markdown("""
        <div style="
            text-align:center; padding:90px 30px;
            background:#fff; border-radius:12px;
            border:2px dashed #c8d6e5; color:#7a8fa6;
        ">
            <div style="font-size:3rem">📝</div>
            <h3 style="margin:12px 0 8px; color:#4a5e74">No Test Cases Yet</h3>
            <p style="margin:0">
                Enter a Jira ID, paste the ticket JSON,<br>
                then click <strong>Generate Test Cases</strong>.<br><br>
                Or click <strong>Load Sample</strong> to try a demo ticket.
            </p>
        </div>
        """, unsafe_allow_html=True)
