# Worker brief and report pattern

Use this field-tested structure for the first worker turn. It is a prompt shape, not a Ferry wire protocol or stored artifact. Omit a section only when it genuinely does not apply. Prefer exact facts over narrative.

## Initial worker brief

```text
ROLE
You are the sole task-scoped writer for <task>. The owner remains the final judge.

IDENTITY
- exact worktree: <absolute path>
- branch / baseline: <branch and commit, when relevant>
- starting dirty state and exclusions: <paths the worker must not touch>

ARCHITECTURAL INVARIANTS
- <facts that must remain true>
- forbidden alternate sources of truth: <if any>

GOALS
- G1 <observable outcome>

WORK SLICES
- W1 <bounded responsibility, affected seams, required cases>

HARD BOUNDARIES
- allowed mutation scope: <paths/actions>
- forbidden actions: <push, deploy, external writes, unrelated cleanup, etc.>
- exact stop conditions: <when to stop and report instead of guessing>

ACCEPTANCE
- <exact command and required nonzero execution/output>
- <same-seam integration check>

REPORT
Return delivery data, not greetings:
- changed file:line locations and what changed;
- each verification command plus decisive output and executed count;
- commits, only if commits were authorized;
- material design decisions and why they were necessary;
- remaining work and everything not verified.
```

## Live correction

Use native/App Server steer on an active turn when a newly observed fact changes work. State the changed fact, affected work slice, required adjustment, and that all other boundaries remain unchanged. If it invalidates most of the assignment, interrupt and start a fresh thread with a complete brief.

## Follow-up after completion

Use the same thread for a question or bounded rework: state the observed gap, required result, acceptance command, and request report delta only.

## Owner acceptance rule

The report is not proof. The owner independently checks the exact worktree, diff, and acceptance commands. A claimed passing test with zero executed tests, stale output, the wrong worktree, or a masked setup failure is rejection evidence.
