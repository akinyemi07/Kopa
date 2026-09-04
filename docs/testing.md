# Testing

```bash
cd kopa_backend && ../.venv/Scripts/python.exe -m pytest -q   # 58 passed
cd kopa_app     && flutter analyze && flutter test            # 17 passed
```

**75 tests.** They are not spread evenly, on purpose — they concentrate on the
two claims a sceptical reviewer should press hardest.

## Claim 1 — the engine is deterministic and auditable

`tests/test_safety_engine.py` (31 tests)

Every test pins `as_of` explicitly. The engine never reads the clock, so these
results are stable forever.

| Area | What is covered |
|---|---|
| Core verdicts | Ample buffer → safe; negative balance → unsafe; obligation uncovered → unsafe; tight runway → caution |
| Thresholds | Runway ≤3 unsafe, ≤7 caution; ≥50% of balance caution; thin obligation buffer |
| Boundaries | Exactly at the 1.10× obligation buffer is **safe**; only strictly below is thin |
| Ordering | Obligations settle by due date, so the *specific* breaking commitment is named |
| Horizon | Obligations beyond 30 days excluded; past-due excluded |
| Validation | Zero, negative and non-numeric amounts rejected; negative balance rejected; zero balance does not divide by zero |
| Spend estimate | Sparse history flagged `history_limited`, not averaged over the full window; stale history excluded; manual override honoured |
| Counterpart | First-time detection; recurring average and frequency; case/whitespace-insensitive matching; amount far above the norm |
| Determinism | Identical inputs → byte-identical `numeric_justification` |
| Money | Rendered as exact 2dp strings, never floats (`0.10 − 0.07 == "0.03"`) |

The two that matter most:

```python
def test_identical_inputs_produce_identical_output():
    assert first.to_numeric_justification() == second.to_numeric_justification()

def test_money_is_never_rendered_as_a_float():
    assert payload["resulting_balance"] == "0.03"
```

## Claim 2 — the AI cannot override the verdict

`tests/test_ai_copilot.py` (20 tests)

Most of these are about failure, because "the AI is optional" is the claim
being made.

| Failure | Asserted result |
|---|---|
| No API key | Fallback, `ai_not_configured`, verdict intact |
| API exception | Fallback, verdict intact |
| Timeout | Fallback, verdict intact |
| Empty / truncated response | Rejected, `too short` |
| Runaway-long response | Rejected, `too long` |
| Guarantee language | Rejected |
| **Contradicts an `unsafe` verdict** | **Rejected**, deterministic text shown |

The load-bearing one:

```python
def test_model_contradicting_an_unsafe_verdict_is_rejected(unsafe_justification):
    client = FakeClient(
        text="Go ahead, this is safe and there is no risk at all to your account."
    )
    result = explain(unsafe_justification, ai_settings(), client=client)
    assert result.is_fallback is True
    assert "strongly suggest reconsidering" in result.text
```

A model that ignores every instruction still cannot mislead the user.

Also covered: the prompt carries every engine figure verbatim; a missing runway
is stated as `NOT AVAILABLE ... rather than guessing`; the fallback quotes the
engine's numbers exactly and never promises safety.

## Demo integrity

`tests/test_demo_scenarios.py` (7 tests)

Pins the exact figures quoted in [demo-script.md](demo-script.md), so the
script and the code cannot drift before judging.

```python
assert j["resulting_balance"] == "17500.00"
assert j["runway_days"] == 12
assert [o["description"] for o in j["at_risk_obligations"]] == ["Rent", "Data subscription"]
```

Plus `test_scenario_b_fires_three_independent_reasons`, which asserts the
unsafe demo is not resting on a single threshold.

## Flutter

`test/widget_test.dart` (17 tests) — `flutter analyze` reports no issues.

| Area | What is covered |
|---|---|
| Money formatting | Thousands separators; negatives; **no rounding or reformatting** of the engine's decimal |
| Verdict parsing | The three known verdicts; **an unrecognised verdict is treated as `unsafe`**, never `safe` |
| Figures | The screen renders the engine's numbers verbatim |
| Accessibility | Unsafe shows icon **and** text, not colour alone |
| At-risk | Obligations named with amounts and due dates |
| Agency | "Send anyway" is present on an unsafe verdict |
| Honesty | Fallback explanations are disclosed; demo data is labelled; "guarantee" never appears |
| Counterpart | First-time and recurring recipients rendered correctly |
| Missing data | "not enough history" shown instead of a fabricated runway |

One implementation note worth recording: these tests set a tall test surface
via `useTallSurface()`. Flutter only builds what is on screen, so on a
phone-sized surface the actions and disclaimer were never built and finders
silently missed content a real scrolling user would see. Four tests failed for
exactly that reason before the fix.

## Not covered

Stated rather than glossed over.

- **No integration test against the live BMONI sandbox.** The chain was
  verified manually via `scripts/bmoni_spike.py`, whose output is recorded in
  [bmoni-integration.md](bmoni-integration.md). An automated test would depend
  on a shared sandbox and a manually funded balance.
- **No database tests.** The models are exercised through demo mode and the
  seed script, not by a test suite.
- **No end-to-end test** of the full app journey on a device.
- **The Android APK build is unverified** — the build machine ran out of disk
  space. Dart code passes analysis and tests; the packaged artifact is
  unproven.

## Reproducing

```bash
# the whole backend suite
cd kopa_backend && ../.venv/Scripts/python.exe -m pytest -q

# just the responsible-AI guarantee
../.venv/Scripts/python.exe -m pytest tests/test_ai_copilot.py -k contradicting -v

# just the demo figures
../.venv/Scripts/python.exe -m pytest tests/test_demo_scenarios.py -v
```
