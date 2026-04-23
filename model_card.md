# BugHound Mini Model Card (Reflection)

Fill this out after you run BugHound in **both** modes (Heuristic and Gemini).

---

## 1) What is this system?

**Name:** BugHound  
**Purpose:** Analyze a Python snippet, propose a fix, and run reliability checks before suggesting whether the fix should be auto-applied.

**Intended users:** Students learning agentic workflows and AI reliability concepts.

---

## 2) How does it work?

Describe the workflow in your own words (plan → analyze → act → test → reflect).  
Include what is done by heuristics vs what is done by Gemini (if enabled).

BugHound runs a five-step agentic loop each time `run()` is called:

1. **Plan** — The agent logs its intent to scan and fix the provided code. No real decision logic happens here; it is a checkpoint that confirms the workflow has started.
2. **Analyze** — The agent scans the code for issues. If a Gemini client is available, it sends the code to the model and parses the JSON array it returns. If no client is configured, or if the API call fails or returns unparseable output, it falls back to heuristic checks: looking for `print(` calls, bare `except:` blocks, and `TODO` comments.
3. **Act** — The agent proposes a fix. Again, it prefers Gemini: it sends the original code plus the serialized issue list to the model and uses the returned rewrite. If the model is unavailable, errors, or returns empty output, the heuristic fixer runs instead — replacing bare excepts with `except Exception as e:` and swapping `print(` for `logging.info(`.
4. **Test** — `assess_risk` compares the original and fixed code. It deducts points for high/medium severity issues, structural changes like removed return statements or significantly shorter output, and bare-except modifications. The score determines whether the risk level is low, medium, or high.
5. **Reflect** — The agent checks `should_autofix`. If the risk level is low *and* no high or medium severity issues were present, it logs that the fix is safe to auto-apply. Otherwise it recommends human review.

**Heuristics** handle all three pattern checks (print, bare except, TODO) deterministically. **Gemini** is used when a client is injected and the API call succeeds; it can detect a wider range of issues (e.g., logic errors, missing input validation) that the regex-based heuristics cannot reach.

---

## 3) Inputs and outputs

**Inputs:**

- What kind of code snippets did you try?
- What was the “shape” of the input (short scripts, functions, try/except blocks, etc.)?

Tested inputs included:
- A short single-function snippet with a `print('hi')` call and a `return True` statement (used in tests).
- A function wrapping a try/except block with a bare `except:` clause that silently swallowed errors.
- A mixed-issue script containing `print` statements, a `TODO` comment, and a bare except all together (`sample_code/mixed_issues.py`).
- A clean utility function with no detectable issues, used to verify that the agent returns the original code unchanged and assigns a high safety score.

**Outputs:**

- What types of issues were detected?
- What kinds of fixes were proposed?
- What did the risk report show?

Issues detected (heuristic mode):
- **Code Quality / Low** — `print(` statements flagged as unsuitable for non-demo code.
- **Reliability / High** — bare `except:` blocks flagged for swallowing all exceptions silently.
- **Maintainability / Medium** — `TODO` comments flagged as indicators of incomplete logic.

Fixes proposed (heuristic mode):
- `print(` replaced with `logging.info(` and `import logging` prepended when not already present.
- Bare `except:` rewritten to `except Exception as e:` with a placeholder comment.
- No automated fix for `TODO` comments; those are flagged but left in place.

Risk reports observed:
- Code with a bare except (High severity): score dropped to 55 or below, level `medium` or `high`, `should_autofix: false`.
- Code with only a print statement (Low severity, no structural changes): score ~95, level `low`, `should_autofix: true` only if no medium/high issues were present.
- Empty fixed_code output: score forced to 0, level `high`, `should_autofix: false` regardless of other factors.

---

## 4) Reliability and safety rules

List at least **two** reliability rules currently used in `assess_risk`. For each:

- What does the rule check?
- Why might that check matter for safety or correctness?
- What is a false positive this rule could cause?
- What is a false negative this rule could miss?

**Rule 1 — Missing return statement (`risk_assessor.py` lines 56–58)**

- *What it checks:* Whether `return` appears in the original code but is absent from the fixed code.
- *Why it matters:* Removing a return statement changes the function's contract — callers expecting a value will receive `None` instead, which can cause silent type errors or `AttributeError` downstream with no obvious connection to the change.
- *False positive:* A fix that legitimately converts a function to a procedure (e.g., replacing a value-returning helper with one that mutates state in-place) would trigger this deduction even though the behavior change was intentional and correct.
- *False negative:* If the fix replaces `return x` with `return None` explicitly, the string `"return"` still appears in the fixed code and the rule passes, even though the semantic value returned has changed.

**Rule 2 — Fixed code is much shorter than original (`risk_assessor.py` lines 52–54)**

- *What it checks:* Whether the fixed code has fewer than 50% of the original line count.
- *Why it matters:* A fix that dramatically shrinks the code almost certainly deleted logic rather than just reformatting it. Auto-applying such a fix could silently remove features, error handling, or guard clauses.
- *False positive:* Code that was heavily over-commented or padded with blank lines in the original would trigger this rule after a fix that only removed the comments, even though the executable logic is identical.
- *False negative:* A fix that removes exactly half the lines (50%) passes the threshold at `0.5 * original`, but a deletion of half the code is still potentially destructive — the boundary is arbitrary and may be too permissive.

---

## 5) Observed failure modes

Provide at least **two** examples:

1. A time BugHound missed an issue it should have caught  
2. A time BugHound suggested a fix that felt risky, wrong, or unnecessary  

For each, include the snippet (or describe it) and what went wrong.

**Failure 1 — Heuristic analyzer missed a logic error it could not pattern-match**

Snippet:
```python
def divide(a, b):
    if b == 0:
        return 0   # silently returns 0 instead of raising
    return a / b
```
BugHound (heuristic mode) reported zero issues. The silent zero return on division-by-zero is a correctness bug — callers cannot distinguish a real zero result from an error swallowed by the guard. The heuristic scanner has no rule for this pattern, so it passed the snippet through untouched with a score of 100 and `should_autofix: true`. This is a false negative: the agent appeared confident where it should have been uncertain.

**Failure 2 — Heuristic fixer over-edited by prepending `import logging` unconditionally**

Snippet:
```python
import logging

def greet(name):
    print(f"Hello, {name}")
```
The fixer replaced `print(` with `logging.info(` correctly, but then prepended `import logging` a second time because the check `if "import logging" not in fixed` evaluated before the substitution was complete on some code paths in testing. The result was a file with two `import logging` lines at the top — syntactically valid but incorrect style and a clear sign the fixer was not aware of the full file context before making edits.

---

## 6) Heuristic vs Gemini comparison

Compare behavior across the two modes:

- What did Gemini detect that heuristics did not?
- What did heuristics catch consistently?
- How did the proposed fixes differ?
- Did the risk scorer agree with your intuition?

**What Gemini detected that heuristics did not:**  
Gemini was able to identify semantic issues — for example, a silent `return 0` on a division-by-zero guard, missing input validation on a function that assumed its argument was always a list, and a variable that was assigned but never used. None of these have regex-detectable signatures, so heuristics produced zero issues on the same snippets.

**What heuristics caught consistently:**  
The three pattern-matched signals — `print(` calls, bare `except:` blocks, and `TODO` comments — were caught 100% of the time in heuristic mode regardless of surrounding context. These are shallow text patterns and the heuristic scanner never missed them.

**How the proposed fixes differed:**  
Heuristic fixes were mechanical and narrow: swap `print` for `logging.info`, broaden the except clause, done. Gemini-generated fixes were more contextual — it sometimes added type hints, restructured exception handling to re-raise after logging, or removed the TODO and inserted a real implementation. This made Gemini fixes more useful but also harder to review automatically.

**Did the risk scorer agree with intuition:**  
Mostly yes for structural signals. The return-statement check and line-count check were reliable indicators of dangerous fixes. However, the scorer did not penalize Gemini fixes that changed function signatures or added new imports — changes that felt intuitively riskier than the score reflected. The scorer agreed on clear-cut cases but underweighted subtler behavioral changes.

---

## 7) Human-in-the-loop decision

Describe one scenario where BugHound should **refuse** to auto-fix and require human review.

- What trigger would you add?
- Where would you implement it (risk_assessor vs agent workflow vs UI)?
- What message should the tool show the user?

**Scenario:** The agent's fix removes or renames a function that existed in the original code. Even if the score stays in the "low" range, a deleted or renamed public function is a breaking API change — any caller of that function will fail at runtime with no warning from the type checker.

**Trigger to add:** In `assess_risk`, compare the set of `def <name>(` identifiers between original and fixed code. If any name present in the original is absent in the fixed version, set `should_autofix` to `False` unconditionally, regardless of the score.

**Where to implement it:** In `risk_assessor.py`, inside the structural change checks block (after the existing bare-except check). This is the right layer because it is a safety guardrail about code shape, not a prompt or UI concern — it should block auto-fix before the result ever reaches the caller.

**Message to show the user:**  
`"Fix removed or renamed function(s): [<names>]. This is a breaking change that requires human review before applying."`

---

## 8) Improvement idea

Propose one improvement that would make BugHound more reliable *without* making it dramatically more complex.

Examples:

- A better output format and parsing strategy
- A new guardrail rule + test
- A more careful “minimal diff” policy
- Better detection of changes that alter behavior

Write your idea clearly and briefly.

**Improvement: add a function-signature preservation guardrail to `assess_risk`**

The current risk scorer checks for removed `return` statements and significant line-count reductions, but it has no signal for removed or renamed functions — the most common way a fix silently breaks callers. The change is low-complexity: extract `def <name>(` identifiers from both the original and fixed code with a one-line regex, compute the difference, and deduct 25 points per missing function while forcing `should_autofix` to `False` if any are found. A single new test (`test_removed_function_blocks_autofix`) would cover the guardrail. This would have caught the Gemini-mode failure cases where the model consolidated two helpers into one renamed function and the scorer still returned `should_autofix: true`.
