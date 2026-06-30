# Test Documentation

## Priority Rules
- If a flag is passed via **CLI**, it takes priority over `config.ini`
- If a flag is **not passed via CLI**, the value is read from `config.ini`
- If a flag is **not in `config.ini`**, the hardcoded default in `click.option` is used

---

## 1. CLI Flag Priority Tests

These tests verify that CLI flags are honored over `config.ini` defaults.

> ℹ️ **Autodiscovery applies here:** All boolean (`is_flag=True`) CLI options defined in `transcriber.py`
> can be tested automatically. The test suite discovers each flag and its `config.ini` counterpart,
> then asserts that a value passed on the CLI wins over `config.ini`. The table below lists
> every boolean flag covered by this autodiscovery.
>
> **How it works:** For each `(cli_flag, config_key, default)` tuple below:
> 1. A synthetic `config.ini` is written with the **opposite** of the CLI value.
> 2. The CLI flag is invoked.
> 3. The resolved value in the `Transcription` object is asserted to match the CLI flag.

| CLI Flag | `config.ini` Key | Code Default | Test assertion |
|---|---|---|---|
| `--summarize` | `summarize` | `False` | CLI `True` overrides config `False` |
| `--diarize` | `diarize` | `False` | CLI `True` overrides config `True` |
| `--github` | `github` | `False` | CLI `True` overrides config `False` |
| `--markdown` | `save_to_markdown` | `False` | CLI `True` overrides config `True` |
| `--needs-review` | `needs_review` | `False` | CLI `True` overrides config `False` |
| `--nocheck` | `nocheck` | `False` | CLI `True` overrides config `False` |
| `--upload` | `upload_to_s3` | `False` | CLI `True` overrides config `False` |
| `--nocleanup` | `nocleanup` | `False` | CLI `True` overrides config `False` |
| `--no-metadata` | `no_metadata` | `False` | CLI `True` overrides config `False` |
| `--text` | `save_to_text` | `False` | CLI `True` overrides config `False` |
| `--json` | `save_to_json` | `False` | CLI `True` overrides config `False` |
| `--verbose` | `verbose_logging` | `False` | CLI `True` overrides config `False` |
| `--correct` | `correct` | `False` | CLI `True` overrides config `False` |

**Non-boolean flags also tested individually:**

### Test: `--llm-provider` CLI flag overrides config

```bash
# config.ini has: llm_provider = openai
tstbtc transcribe "path/to/audio.mp3" \
  --llm-provider google \
  --username "test_user" \
  --title "Test"
```
**Expected:** `CorrectionService(provider=google, ...)` NOT `openai`

### Test: `--asr-provider` CLI flag overrides config

```bash
# config.ini has: asr_provider = whisper
tstbtc transcribe "path/to/audio.mp3" \
  --asr-provider deepgram \
  --username "test_user" \
  --title "Test"
```
**Expected:** `Initialized ASR service: Deepgram(...)` NOT `Whisper(...)`

### Test: `--model` CLI flag overrides config default

```bash
tstbtc transcribe "path/to/audio.mp3" \
  --asr-provider whisper \
  --model small \
  --username "test_user" \
  --title "Test"
```
**Expected:** `Initialized ASR service: Whisper(model=small)`

---

## 2. ASR Provider Tests

> ℹ️ **Autodiscovery applies here:** Provider names are discovered at runtime via
> `get_available_providers()` (which scans `app/services/providers/` for
> `BaseTranscriptionService` subclasses). The tests below are **generated automatically**
> for every discovered provider so that adding a new provider file automatically
> adds test coverage.
>
> **How it works:**
> 1. `get_available_providers()` returns the live list (e.g. `['whisper', 'deepgram', 'smallestai']`).
> 2. For each provider name, a parametrised test:
>    - Calls `get_asr_service(provider_name, config, mock_writer)`.
>    - Asserts the returned object is a `BaseTranscriptionService`.
>    - Asserts `service.__class__.PROVIDER_NAME == provider_name`.
> 3. Provider-specific requirements (API keys, local models) are handled by
>    `pytest.mark.skipif` guards and `monkeypatch.setenv` fixtures per provider.

**Currently discovered providers:** `whisper`, `deepgram`, `smallestai`
*(VibeVoice is excluded from CI autodiscovery due to 16 GB+ RAM requirements — see note below)*

### Test: Whisper Provider (Local)

```bash
tstbtc transcribe "test/testAssets/audio.mp3" \
  --asr-provider whisper \
  --model small \
  --username "test_user" \
  --title "Whisper Test" \
  --markdown
```
**Expected:**
- `Initialized ASR service: Whisper(model=small)`
- Transcript is generated and saved
- No crash / OOM errors

**Available models:** `tiny`, `tiny.en`, `base`, `base.en`, `small`, `small.en`, `medium`, `medium.en`, `large-v2`

### Test: Deepgram Provider (Remote)

```bash
tstbtc transcribe "test/testAssets/audio.mp3" \
  --asr-provider deepgram \
  --diarize \
  --username "test_user" \
  --title "Deepgram Test" \
  --markdown
```
**Expected:**
- `Initialized ASR service: Deepgram(summarize=False, diarize=True)`
- Deepgram JSON output file created in `local_models/`
- Transcript generated with speaker labels

**Requires:** `DEEPGRAM_API_KEY` in `.env`

### Test: VibeVoice Provider (Local — Short Audio Only)

> ⚠️ **Only works on audio < 3 minutes due to RAM constraints (16GB+ needed for longer audio)**
> ⚠️ **Excluded from automated CI autodiscovery. Run manually.**

```bash
tstbtc transcribe "test/testAssets/audio.mp3" \
  --asr-provider vibevoice \
  --diarize \
  --username "test_user" \
  --title "VibeVoice Test" \
  --markdown
```
**Expected:**
- `Initialized ASR service: VibeVoice(model=microsoft/VibeVoice-ASR-HF, diarize=True)`
- Transcript created with speaker labels

**Known failure:** `RuntimeError: Invalid buffer size: 14.49 GiB` on audio > 5 minutes

### Test: Invalid Provider Name

> ℹ️ **Autodiscovery applies here:** The list of valid provider names in the error message
> is also auto-discovered, so the assertion checks for every registered provider.

```bash
tstbtc transcribe "test/testAssets/audio.mp3" \
  --asr-provider invalid_provider \
  --username "test_user" \
  --title "Invalid Provider Test"
```
**Expected:**
- The command should fail with a clear error message.
- Error in logs or output: `ValueError: Unknown ASR provider: 'invalid_provider'. Choose from ['whisper', 'deepgram', 'vibevoice', 'smallestai']`

---

## 3. LLM Provider Tests

> ℹ️ **Autodiscovery applies here:** The `--llm-provider` CLI option is defined as
> `click.Choice(["openai", "google", "claude"])`. The test suite reads this choice list
> and generates a parametrised test for each valid LLM provider, verifying that
> `CorrectionService` and `SummarizerService` are initialized with the correct provider name.
> API keys are injected via `monkeypatch.setenv`; tests are skipped if the required key
> is not available in the environment.

| LLM Provider | Required env var | Expected model |
|---|---|---|
| `openai` | `OPENAI_API_KEY` | `gpt-4o` |
| `google` | `GOOGLE_API_KEY` | `gemini-3-flash-preview` |
| `claude` | `CLAUDE_API_KEY` | (claude default) |
| `gemma4` | Ollama running locally | `gemma3:4b` |

### Test: Gemma4 (Ollama — Local)

```bash
tstbtc transcribe "test/testAssets/audio.mp3" \
  --asr-provider whisper \
  --llm-provider gemma4 \
  --correct \
  --summarize \
  --username "test_user" \
  --title "Gemma4 Test" \
  --markdown
```
**Expected:**
- `CorrectionService(provider=gemma4, model=gemma3:4b)`
- `SummarizerService(provider=gemma4, model=gemma3:4b)`
- Corrected transcript and summary generated

**Requires:** Ollama running locally with `gemma3:4b` pulled

### Test: Google Gemini (Remote)

```bash
tstbtc transcribe "test/testAssets/audio.mp3" \
  --asr-provider whisper \
  --llm-provider google \
  --correct \
  --summarize \
  --username "test_user" \
  --title "Gemini Test" \
  --markdown
```
**Expected:**
- `CorrectionService(provider=google, model=gemini-3-flash-preview)`
- `SummarizerService(provider=google, model=gemini-3-flash-preview)`
- Model auto-remapped from `gpt-4o` → `gemini-3-flash-preview`

**Requires:** `GOOGLE_API_KEY` in `.env`

### Test: OpenAI (Remote)

```bash
tstbtc transcribe "test/testAssets/audio.mp3" \
  --asr-provider whisper \
  --llm-provider openai \
  --correct \
  --summarize \
  --username "test_user" \
  --title "OpenAI Test" \
  --markdown
```
**Expected:**
- `CorrectionService(provider=openai, model=gpt-4o)`
- `SummarizerService(provider=openai, model=gpt-4o)`

**Requires:** `OPENAI_API_KEY` in `.env`

---

## 4. Processing Pipeline Tests

> ℹ️ **Autodiscovery applies here for stage presence:** The pipeline stages (`correction`,
> `summarization`) are controlled by boolean flags (`--correct`, `--summarize`). For each
> combination of enabled stages, tests assert that:
> - The corresponding service object is **not None** when enabled.
> - The corresponding service object **is None** when disabled.
> - The `pipeline_state["stages"]` dict contains exactly the expected stage names.

| `--correct` | `--summarize` | Expected services initialized |
|---|---|---|
| ✗ | ✗ | `MetadataExtractorService` only |
| ✓ | ✗ | `MetadataExtractorService` + `CorrectionService` |
| ✗ | ✓ | `MetadataExtractorService` + `SummarizerService` |
| ✓ | ✓ | `MetadataExtractorService` + `CorrectionService` + `SummarizerService` |

### Test: Correction Only

```bash
tstbtc transcribe "test/testAssets/audio.mp3" \
  --asr-provider whisper \
  --llm-provider gemma4 \
  --correct \
  --username "test_user" \
  --title "Correction Test"
```
**Expected log sequence:**
```log
Initialized LLM service: MetadataExtractorService(...)
Initialized LLM service: CorrectionService(...)
# NO SummarizerService
Initialized ASR service: Whisper(...)
```

### Test: Summarize Only (No Correction)

```bash
tstbtc transcribe "test/testAssets/audio.mp3" \
  --asr-provider whisper \
  --llm-provider gemma4 \
  --summarize \
  --username "test_user" \
  --title "Summarize Test"
```
**Expected:** `SummarizerService` initialized but NOT `CorrectionService`

### Test: Full Pipeline (Metadata + Correct + Summarize)

```bash
tstbtc transcribe "test/testAssets/audio.mp3" \
  --asr-provider whisper \
  --llm-provider gemma4 \
  --correct \
  --summarize \
  --diarize \
  --markdown \
  --username "test_user" \
  --title "Full Pipeline Test"
```
**Expected log order:**
```log
Initialized LLM service: MetadataExtractorService(...)
Initialized LLM service: CorrectionService(...)
Initialized LLM service: SummarizerService(...)
Initialized ASR service: Whisper(...)
```

---

## 5. Output Format Tests

> ℹ️ **Autodiscovery applies here:** Output format flags (`--markdown`, `--json`, `--text`)
> are boolean `is_flag` options. The test suite discovers all output-related flags and checks
> that the corresponding exporter is present in `Transcription.exporters` when the flag is set,
> and absent when it is not.

| CLI Flag | Exporter key | Output artifact |
|---|---|---|
| `--markdown` | `markdown` | `.md` file under `local_models/` |
| `--json` | `json` | `.json` file under `metadata/` |
| `--text` | `text` | `.txt` file under `local_models/` |

### Test: Markdown Output

```bash
tstbtc transcribe "test/testAssets/audio.mp3" \
  --asr-provider whisper \
  --markdown \
  --username "test_user" \
  --title "Markdown Test"
```
**Expected:** `.md` file created under `local_models/`

### Test: JSON Output

```bash
tstbtc transcribe "test/testAssets/audio.mp3" \
  --asr-provider whisper \
  --json \
  --username "test_user" \
  --title "JSON Test"
```
**Expected:** `.json` file created under `metadata/`

---

## 6. Source Type Tests

### Test: Local Audio File

```bash
tstbtc transcribe "test/testAssets/audio.mp3" \
  --asr-provider whisper \
  --username "test_user" \
  --title "Local Audio"
```

### Test: YouTube Video

```bash
tstbtc transcribe "https://www.youtube.com/watch?v=<VIDEO_ID>" \
  --asr-provider deepgram \
  --username "test_user"
```
> ⚠️ YouTube rate-limits (HTTP 429) can occur if the same video is fetched repeatedly. Use a different video each time.

---

## 7. Server Lifecycle Tests

### Test: Auto-start server

```bash
# Kill any existing server first
tstbtc server stop
# Then run a transcribe command — server should auto-start
tstbtc transcribe "test/testAssets/audio.mp3" \
  --asr-provider whisper \
  --username "test_user" \
  --title "AutoStart Test"
```
**Expected output:**
```log
Auto-starting server for command: transcribe
Transcription server is not running. Starting it automatically...
Server logs will be written to: logs/server_dev.log
Transcription server started successfully.
```

### Test: Server start/stop

```bash
tstbtc server start
# wait a moment
curl http://localhost:8000/health    # should return 200
tstbtc server stop
curl http://localhost:8000/health    # should fail/refuse connection
```

### Test: Server status / get queue

```bash
tstbtc get_queue
```
**Expected:** `{'data': []}` or list of queued items

---

## 8. Config.ini Fallback Tests

> ℹ️ **Autodiscovery applies here:** Every row in the table below is a `(config_key, expected_value)`
> pair. The test suite reads the actual `config.ini` (or a test fixture copy) and for each key,
> runs the CLI **without** its corresponding flag, then asserts that the `Transcription` object
> (or the resolved config dict) reflects the value from `config.ini`.

Verify that when no CLI flag is passed, `config.ini` values are used:

| `config.ini` key | Default in code | What to test |
|----------------|----------------|--------------|
| `asr_provider = whisper` | `openai` | Run without `--asr-provider` → Whisper is used |
| `diarize = True` | `False` | Run without `--diarize` → diarize is True |
| `summarize = False` | `False` | Run without `--summarize` → no SummarizerService |
| `save_to_markdown = True` | `False` | Run without `--markdown` → `.md` file still created |
| `llm_provider = openai` | `openai` | Run without `--llm-provider` → OpenAI used |
| `nocheck = True` | `False` | Source duplicate check is skipped |
| `gemma4_model = gemma3:4b` | `gemma3:4b` | Gemma4 uses this model when no override |
| `github = False` | `False` | Run without `--github` → no GitHub push |
| `needs_review = False` | `False` | Run without `--needs-review` → no review flag |
| `one_sentence_per_line = True` | `True` | Deepgram output has one sentence per line |

---