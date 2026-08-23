# Error classes

Apply only the sections the user selected in Step 0.

Each heuristic is a **question to ask the code**, not a pattern to match against.

---

## Logic

The claim is right, the mechanism is wrong.

**Boundaries.** For every comparison, ask what happens at exactly the boundary value. `<` where `<=` was meant is the single most common real bug in production code. Check every loop bound, every range check, every retry limit, every expiry check, every pagination offset. Say the boundary value out loud: "at `len(items)`, this reads index `len(items)`."

**Inverted and partial conditions.** Read every negation literally. `if not (a and b)` is not `if not a and not b`. Check that every `else` branch handles what its `if` genuinely excludes — not what the author was picturing. A condition guarded on three fields where the data has four states leaves one state unhandled.

**Operator slips.** Assignment where comparison was meant, `and` for `or`, `+` for `-`, bitwise for logical, integer division where float was meant, string concatenation where addition was meant. These survive review because they read correctly at a glance.

**Order of operations.** Not just arithmetic precedence — sequencing. A value read before it is written, a lock taken after the thing it protects, a cache invalidated before the write it should follow, a validation that runs after the side effect it was supposed to prevent.

**State machines.** List the states, list the transitions the code allows, and find the one it allows that should be impossible. Look hard for transitions out of a terminal state, and for two paths into the same state that leave different fields set.

**Unreachable and always-taken.** A branch whose condition cannot be false given the checks above it. A `return` before code that was meant to run. An exception path that swallows the only signal a caller had.

**Loops.** Does the loop variable change on every path through the body? Is the collection mutated while iterated? Does the accumulator reset where it should not, or fail to reset where it should? Does an early `break` skip cleanup that runs at the bottom?

**Copy-paste divergence.** Where two blocks are near-identical, diff them line by line. The bug is the line that was supposed to change and did not — a wrong index, a wrong field name, a wrong variable in the second copy.

---

## Crash & runtime

The code works on the input the author had in mind.

**Nullability.** For every dereference, trace back to where the value originated. Can that origin produce null, `None`, `undefined`, an empty result, or a missing key? A lookup that returns a default in one place and raises in another is a crash waiting on data.

**Unbounded assumptions.** Index access without a length check. `[0]` on a collection that can be empty. Division by a value derived from a count. Parsing a string assumed to have a delimiter. Casting a value assumed to be numeric.

**Exception paths.** Which exceptions can each call actually raise, and does anything catch them? Then the reverse: does any catch block swallow a class broader than it handles — catching everything to suppress one expected failure, and hiding real errors with it? A bare catch-all that discards the error is a finding whenever the block can fail for a second reason.

**Resources.** Every open, connect, acquire, or allocate: is it released on **every** path out, including the exception path and the early return? A close at the bottom of a function with a return above it is a leak.

**Side effects already committed.** When you find an early return or a raise, look at what happened *above* it, not only what is skipped below. Opening a file for write truncates it; a row is inserted; a counter is incremented; a message is sent. Code that bails out after a destructive step and before the step that made it worthwhile leaves the system in a state neither branch intended.

**Concurrency.** Shared mutable state touched without a lock. A check-then-act that another thread can interleave. An await between reading a value and writing it back. A callback that assumes it runs before another that has no ordering guarantee.

**External boundaries.** Anything crossing a process boundary — network, disk, subprocess, database — can fail, time out, or return a shape you did not expect. Code that treats a response as if it always arrives and always parses is a crash under normal operating conditions, not an edge case.

---

## Contract mismatch

The mechanism works. It is not what the code promised.

This is the highest-yield class for *unintended* errors specifically.

**Name against body.** A function called `validate_x` that returns a value instead of raising. A `get_` prefix on something that mutates. An `is_` prefix on something that returns other than a boolean. An `_all` suffix on something that stops at the first match. A plural name over a single-item return. Take the name literally and check.

**Docstring and comment against body.** Read every comment as an assertion and test it. Comments rot silently: they describe the code as it was two changes ago. "Returns -1 if not found" over a body that returns null. "Caller must hold the lock" where a caller does not. A comment that contradicts its code is always a finding — either the code is wrong or the comment is, and both mislead the next reader.

**Signature against behavior.** A declared return type never returned on some path. An optional parameter treated as required. A parameter documented as a list handled as a string. A function that returns a value on one path and nothing on another — an implicit empty return where the caller expects data.

**Tests against implementation.** Read what the tests assert, then find what they do not. An untested branch that contradicts a tested one is the bug. A test asserting only that the function does not throw is a claim about nothing.

**Callers against callee.** Every call site is an assertion about the callee. Where two callers use the same return value differently — one checking for null, one not — one of them is wrong. Where a caller passes an argument the callee's checks never anticipated, follow it in.

**Defaults that disagree.** The same setting defaulted in two places to two values. A config key read with one default and written with another. This produces behavior that depends on load order and is invisible until it is not.

---

## Security

For the input-driven checks below — taint, authorization, validation — a finding needs a specific untrusted input reaching a specific dangerous operation. A missing best practice with no reachable path is not a finding.

**Secrets and weak crypto are exempt from that gate**, because neither has a taint path by nature: an exposed credential or a guessable token is a defect on sight. Where the value's sensitivity is genuinely arguable — an identifier that may or may not be a security boundary — that is exactly what the Suspected section is for. Do not use the taint rule to drop it.

**Trace the taint.** Start from every point untrusted data enters — request parameters, headers, file uploads, environment, command-line arguments, database rows written by users, third-party API responses. Follow each forward. Does it reach a query, a shell command, a file path, an eval, a deserializer, a template, a redirect? Name the path or drop the finding.

**Authorization, per handler.** Authentication proves who; authorization decides what. For every operation touching user-owned data, ask whether it checks that *this* user owns *this* record — not just that someone is logged in. An ID taken from the request and used directly in a query is the most common real breach in application code.

**Secrets.** Credentials in source, in defaults, in comments, in log lines, in error messages returned to a client, in a stack trace rendered to a response.

**Crypto and randomness.** A non-cryptographic random number generator producing a token, session ID, password reset key, or nonce. A password stored with a fast hash or none. A comparison of secrets that short-circuits on the first differing byte.

**Validation placement.** Validation on the client with none on the server. Validation before a transformation that reintroduces what it stripped. A check on the decoded value where the raw value is what gets used.
