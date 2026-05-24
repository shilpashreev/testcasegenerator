# 🧪 Test Case Generator

Generate requirement-based QA test cases from Jira tickets and export them to
formatted, per-ticket Excel files. The LLM backend is pluggable: use
**Anthropic Claude** in the cloud, or run **open-source Gemma / Llama** models
locally via **Ollama** or any **OpenAI-compatible** server (LM Studio, vLLM,
llama.cpp).

---

## Highlights

- **Bring your own model** — pick Claude, Ollama, or an OpenAI-compatible
  endpoint from a dropdown in the UI. No code change to switch.
- **Incremental updates** — a SHA-256 hash of the requirements is stored in each
  Excel file. Unchanged requirements ⇒ no model call; changed requirements ⇒
  only the affected tests are revised; brand-new ticket ⇒ generated from scratch.
- **Token-optimized** — a single cacheable system prompt, compact JSON payloads,
  and forced-JSON output keep cost and latency low. Anthropic prompt caching is
  enabled automatically.
- **Grounded output** — the model is instructed to derive tests *only* from the
  ticket, never to invent URLs, credentials, or values.
- **Offline path** — `generate_login_offline.py` produces a sample login suite
  with no API key, for demos or air-gapped environments.

---

## Quick start

```powershell
# 1. Install dependencies
python -m pip install -r requirements.txt

# 2. Launch the app
streamlit run app.py          # or: .\run.ps1   (Windows)   |   run.bat
```

Then open <http://localhost:8501>:

1. Pick a **provider** in the sidebar and configure it (see below).
2. Enter a **Jira ID** and paste the ticket **JSON** (or click **Load Sample**).
3. Click **🚀 Generate Test Cases**.
4. Review the table and **📥 Download Excel**.

### No-API-key demo

```powershell
python generate_login_offline.py     # writes test_cases/PROJ-101.xlsx
```

---

## Provider setup

| Provider | What you need | Sidebar fields |
|----------|---------------|----------------|
| **Anthropic (Claude)** | API key from <https://console.anthropic.com> | API key, model |
| **Ollama** | [Ollama](https://ollama.com) running locally | Base URL (`http://localhost:11434`), model |
| **OpenAI-compatible** | LM Studio / vLLM / llama.cpp server | Base URL (`…/v1`), optional API key, model |

### Running an open-source model with Ollama

```powershell
# install Ollama (https://ollama.com/download), then:
ollama pull gemma2          # or: ollama pull llama3.1
ollama serve                # serves the API at http://localhost:11434
```

In the app choose **Ollama**, click **🔄 Refresh model list**, pick `gemma2`,
and generate. No API key, no cloud calls.

### Running with LM Studio / vLLM (OpenAI-compatible)

Start the server's OpenAI endpoint (LM Studio default `http://localhost:1234/v1`),
choose **OpenAI-compatible** in the app, set the base URL, refresh the model
list, and generate.

---

## Architecture

The codebase is a small, layered package. The UI knows nothing about *which*
model is used — it just builds a `ProviderConfig` and hands it to the factory.

```
app.py                      Streamlit UI (presentation only)
generate_login_offline.py   Keyless sample generator

testcasegen/
├── config.py        ProviderType, ProviderConfig, model registry
├── domain.py        TestCase, Requirements, GenerationResult, TokenUsage
├── extraction.py    RequirementExtractor (flat + Jira REST shapes)
├── prompts.py       Token-optimized system/user prompt builders
├── json_utils.py    Robust JSON-object extraction from model output
├── storage.py       ExcelRepository (per-ticket .xlsx + hidden hash sheet)
├── service.py       GeneratorService — orchestrates the whole flow
├── samples.py       Bundled demo ticket loader
└── providers/
    ├── base.py             LLMProvider interface + LLMResponse
    ├── anthropic_provider.py
    ├── ollama_provider.py
    ├── openai_compatible.py
    └── factory.py          ProviderFactory (config → provider)
```

### Request flow

```
Jira JSON
   │  RequirementExtractor.extract()
   ▼
Requirements ──content_hash()──▶ compare with hash stored in Excel
   │                                   │
   │ unchanged ─────────────────▶ return existing (no model call)
   │ changed / new
   ▼
PromptBuilder ─▶ LLMProvider.complete() ─▶ JSON ─▶ TestCase[]
   │
   ▼
ExcelRepository.save()  (writes .xlsx + requirements hash)
```

### Design patterns used

- **Strategy** — `LLMProvider` defines one interface; `AnthropicProvider`,
  `OllamaProvider`, and `OpenAICompatibleProvider` are interchangeable strategies.
- **Factory** — `ProviderFactory` maps a `ProviderConfig` to the right strategy;
  adding a backend is one subclass + one registry line.
- **Repository** — `ExcelRepository` hides all Excel/openpyxl detail behind
  `load()` / `save()`.
- **Facade / Service Layer** — `GeneratorService` coordinates extraction,
  hashing, the provider, and storage so callers (UI, scripts) stay trivial.
- **Value Objects (DTOs)** — immutable-ish dataclasses in `domain.py` carry data
  between layers; behaviour that belongs to the data (hashing, context rendering)
  lives with it.
- **Dependency Injection** — the provider and repository are injected into
  `GeneratorService`, which makes it testable with fakes.

---

## Token optimization

| Technique | Where | Effect |
|-----------|-------|--------|
| Single static system prompt | `prompts.py` | Fixed overhead; no per-call rule repetition |
| Anthropic prompt caching | `anthropic_provider.py` | System block billed once per 5-min window |
| Forced JSON output | all providers | No prose tokens; Anthropic uses a `{` prefill |
| Compact JSON on updates | `prompts.py` | Existing tests sent without whitespace |
| Incremental skip | `service.py` | Unchanged requirements ⇒ **zero** tokens |

Token usage (in / out / cached) is shown under the results after each run.

---

## Jira JSON format

Both a flat shape and the Jira REST `fields` shape are accepted. Minimal flat
example:

```json
{
  "id": "PROJ-101",
  "summary": "User Login and Authentication",
  "description": "As a user I want to log in with email and password…",
  "acceptance_criteria": ["Valid credentials grant access", "…"],
  "attachments": [{ "filename": "spec.txt", "content": "…" }]
}
```

See `sample_jira.json` and `sample_login_test.json` for fuller examples.

Output Excel columns: **Test ID · Jira ID · Test Title · Description · Steps ·
Data · Expected Result**, plus a hidden `_metadata` sheet holding the
requirements hash.

---

## Project layout notes

- Generated `test_cases/*.xlsx` are git-ignored (regenerate them anytime).
- Secrets (`.env`, `*.key`) are git-ignored — never commit your API key.
- Requires Python 3.10+.
