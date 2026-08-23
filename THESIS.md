# The Ferry Thesis

> **Keep the agent. Choose the model.**

Ferry starts from a simple observation:

**an agent and a model are not the same thing.**

A coding agent owns the mission. It understands the user's intent, carries project context, reads the repository, plans work, delegates tasks, verifies changes, and decides what to accept.

A model is one of the resources that can perform that work.

Today, those two ideas are often bundled together. A vendor builds an agent around its own models, and the agent naturally sends most work back into that same model ecosystem.

That is a reasonable product design.

It does not have to be the only one.

## Models have different jobs

There is no reason to assume that every coding task should use the same model.

Some work deserves the strongest reasoning available:

- architecture decisions;
- ambiguous requirements;
- difficult debugging;
- cross-cutting changes;
- high-risk review.

Other work is already well bounded:

- implement a clearly specified function;
- add tests around known behavior;
- follow an existing component pattern;
- perform a mechanical refactor;
- make a localized change with explicit acceptance criteria.

For these tasks, another capable coding model may be faster, cheaper, or simply better suited to the work.

And cost is only one dimension.

Models can differ in reasoning, coding behavior, latency, context handling, tool use, style, specialization, reliability, and price.

The useful question is therefore not:

> Which model is best?

It is:

> **Which model makes sense for this task?**

Ferry exists to preserve that choice.

## The agent should remain the owner

Ferry does not try to replace Codex.

It exists because Codex is worth keeping.

The main Codex session remains responsible for the things that matter most:

- understanding the mission;
- holding project context;
- deciding what can safely be delegated;
- defining the boundaries of the task;
- inspecting the real worktree;
- running acceptance checks;
- steering or stopping work when necessary;
- making the final judgment.

The worker does work.

The owner decides whether that work is good.

> **Ferry work, not judgment.**

A worker report is delivery data, not truth.

Delegation must not transfer authority.

## Model choice is a user capability

The AI industry is naturally moving toward vertically integrated agent ecosystems.

A model company builds models. Those models power its agent. That agent becomes
the interface through which users perform work.

There is nothing inherently wrong with this.

But another future should remain possible.

A future where:

```text
your agent
  -> your project context
      -> your task
          -> the model you choose
```

Ferry is a small experiment in that direction.

It is not anti-OpenAI, anti-Anthropic, anti-Google, or anti-vendor.

It is **pro-user-agency**.

A user can prefer Codex as an agent, prefer a frontier OpenAI model for difficult reasoning, and still choose a different model for a bounded implementation task.

Those choices are not contradictory.

They are what a heterogeneous toolchain should allow.

## Agent does not imply model

This distinction becomes more important as agents become persistent working environments rather than single prompts.

When an agent is carrying a large project across many tasks, changing the worker should not require changing the owner of the mission.

The project context should not need to move just because the execution model changes.

The user's working relationship with an agent should not disappear because another model is more appropriate for one task.

In this view:

**the agent is the continuity layer.**

Models are interchangeable only where the task permits them to be.

That boundary matters.

Ferry does not assume all models are equivalent, and it does not assume every task is safely delegable.

Choosing not to delegate is also a routing decision.

## A delegation seam, not a dispatcher

Ferry provides a narrow delegation seam for a bounded piece of work that the Codex owner has already decided to delegate. It preserves an explicit choice of configured provider and model.

It does not own routing policy or become another agent orchestration framework.

It does not need its own:

- scheduler;
- task queue;
- durable state machine;
- context database;
- provider registry;
- authentication system;
- agent runtime;
- model configuration format;
- application UI.

Codex already owns the agent lifecycle and project context.

Codex-owned configuration retains provider access and authentication.

The repository already owns the actual work.

Ferry should compose those systems rather than duplicate them.

This is an important design constraint.

**Model plurality should not require infrastructure plurality.**

## Thin by design

Ferry uses the smallest upstream seam that preserves the owner's explicit provider and model choice.

That implementation detail is not the thesis.

When Codex makes that capability native, Ferry should use the native seam and delete what it no longer needs.

If upstream eventually solves the entire problem cleanly, more of Ferry should disappear with it.

That would be a successful outcome.

Ferry is not trying to defend its own complexity.

It is trying to preserve a capability for the user.

## No universal router

Ferry also does not assume that model selection can immediately be reduced to a perfect automatic routing algorithm.

Real software work is contextual.

The same task description can have different risk depending on the repository, the current state of the project, the quality of its tests, and the consequences of failure.

Today, explicit user choice is valuable.

Over time, evidence may reveal useful delegation patterns.

A bounded, observable, reversible implementation task may often be a good worker candidate.

An ambiguous, architectural, cross-cutting task may deserve the owner model.

But those policies should emerge from real use, not from premature orchestration complexity.

Ferry should earn automation before adding it.

## Cost matters, but choice matters more

Ferry began from a practical constraint.

Modern coding agents make it possible to work on many projects and many tasks in parallel. That can make even generous subscription limits restrictive, while using frontier models through APIs for every task can become expensive.

Delegating suitable work to another model can reduce that pressure.

That is useful.

**Keep Codex. Spend less.** is a useful acquisition hook. It is not a promise or the whole thesis.

Ferry does not promise that delegation is always cheaper.

Sometimes another model may be chosen because it is faster.

Sometimes because it behaves better for a particular type of coding work.

Sometimes because it is specialized.

Sometimes because the user simply prefers it.

The deeper principle is not:

> always spend less.

It is:

> **do not spend your best model where another model makes more sense.**

And ultimately:

> **the choice should remain yours.**

## A plural model future

We expect models to develop different niches.

The future may not look like one universal model permanently defeating every other model on every dimension.

It may look more like an engineering toolchain:

different strengths, different tradeoffs, different jobs.

If that happens, agents should be able to benefit from those differences without forcing users to abandon the agent environment they already trust.

The model ecosystem can be plural while the agent experience remains coherent.

That is the future Ferry is built for.

## The principle

Ferry can be summarized in three statements:

**Agent ≠ Model.**

**Keep the agent. Choose the model.**

**Ferry work, not judgment.**

Everything else is implementation.
