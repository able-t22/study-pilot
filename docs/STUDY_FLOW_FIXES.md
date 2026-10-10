# Study-flow fixes and verification

## Changes

- Startup separates optional language loading from backend health. A SQLite WAL setup race on first load is fixed.
- All seven note-style buttons work and retain the selected source, focus and other controls. Job polling reports failures and restores the Generate button.
- Common TeX formulas render locally as MathML: fractions, roots, sums, integrals, indices, Greek symbols, matrices and cases. Markdown preserves formulas; detailed source notes retain formulas.
- Tutor uses one English answer request, conversation-aware retrieval, reasoning instructions and required source citations. Failed requests explicitly show source excerpts rather than claiming an AI explanation.
- OpenRouter uses reusable HTTP connections, specific errors, model cooldowns, bounded failover and a diagnostics/test panel. Configuration loads from the project .env. A fixed primary model replaces the random free router; fallback model IDs remain configurable.
- Quizzes reuse the question bank, generate one batch, review one batch without showing the reviewer the answer key, and share a default 25-second AI budget. Model failover can add HTTP attempts within that budget. Local definition/concept checks and supported maths exercises remain available during outages. Shorter or repeated practice is labelled when the material limits new questions.
- Revision packs load automatically without AI requests, include strong topics when needed, and have a corrected document layout. Spaced review builds locally. Revision and Evaluation are both inside the main panel, with responsive controls.
- HOW_TO_RUN.md documents startup and connection troubleshooting.

## Verification

Passed Python checks:
- scripts/selftest.py
- scripts/test_llm_fallback.py
- scripts/test_features.py
- scripts/test_repairs.py
- scripts/test_v4.py
- scripts/test_requirements.py
- scripts/test_study_flow.py
- tests/test_lang.py

Passed JavaScript syntax checks and scripts/test_ui.cjs in Chrome at desktop and 390px mobile widths. UI verification covers all note styles, preserved focus input, Revision/Evaluation containment, fractions/roots/matrices, and status behavior when the language endpoint fails. The optional UI script needs Playwright, UI_TEST_URL pointing to an isolated test server with a learner and course material, and CHROME_PATH when using installed Chrome.

The simulation regression checks finite, valid results rather than assuming the adaptive policy must always win. Its outcomes remain visible, including unfavourable ones.

## Limits

Live OpenRouter authentication, availability and latency could not be verified: this execution environment blocks outbound sockets (WinError 10013). Mocked tests cover successful requests, invalid credentials, quotas, timeouts, model failures and malformed responses. Use the connection panel's Test connection action on the machine running StudyPilot.

MathML covers common study formulas, not the full LaTeX typesetting language. Local fallback checks need readable definitions or supported formulas; they cannot invent good questions from empty or unreadable uploads.
