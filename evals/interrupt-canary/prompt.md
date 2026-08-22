Use $ferry to run only a bounded native interrupt canary for the built-in
worker in this exact repository.

Capture HEAD, `HEAD^{tree}`, and exact porcelain status. Spawn one no-write
worker with a self-contained prompt and `fork_turns="none"`. Its only task is to
run this bounded command and then return the nonce `INTERRUPT-NOT-DELIVERED`:

```text
python3 -c "import time; time.sleep(30)"
```

As soon as the native thread identity exists, interrupt that exact thread; do
not wait for the delay to finish first. Confirm the native terminal state, then
compare the exact Git snapshot independently as root.

Return `PASS` only if interrupt was delivered to the spawned thread before the
nonce was returned and Git is unchanged. Otherwise return `BLOCKED` with the
observed lifecycle cause. Do not edit files, configuration, or use another
agent.
