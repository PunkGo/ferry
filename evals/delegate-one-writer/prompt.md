Use $ferry to complete this repository task through Codex's native worker
thread.

Use the built-in `worker`; no alternate model or provider is requested. Delegate the implementation
in `TASK.md` to exactly one writer. The worker may edit only `label.py` and
`test_label.py` and must run the repository's unittest suite.

Neither the root nor the worker may call a Ferry alternate-provider worker tool
or launch `codex` / `codex app-server` from a shell.

After the worker's first completed result, send a follow-up to that same native
thread asking it to add this regression test and rerun the suite:

```python
def test_preserves_ascii_digits(self) -> None:
    self.assertEqual(canonicalize_label("R2 / D2"), "r2-d2")
```

Then independently inspect the worktree and run `python3 -m unittest -v` as the
root. Do not edit `.agents/`, `AUTHORITY.toml`, `AGENTS.md`, or `TASK.md`.

Pass only if:

- the same native worker thread handled the initial task and follow-up;
- the complete root and worker tool traces contain the native worker call but
  no Ferry alternate-provider worker-tool call and no shell invocation of
  `codex` or `codex app-server`;
- only `label.py` and `test_label.py` changed;
- the final command reports at least five executed tests and zero failures;
- `canonicalize_label` has no external dependencies;
- the root reports the thread identity, changed paths, and final test count.

If any condition cannot be proved, report `BLOCKED` with the observed cause. Do
not silently fall back to root implementation.
