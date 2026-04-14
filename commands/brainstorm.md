# Brainstorm

Guide the user through refining a project idea into a clear, approved spec — then save it as a markdown file.

## Process

Follow these phases in order. Never ask multiple questions at once — one question per turn.

---

### Phase 1 — Discover the Core Idea

Start by asking:

> "What's the project idea you'd like to explore? Describe it in a sentence or two — don't worry about details yet."

Then ask **one targeted follow-up question at a time** to uncover:
- The problem it solves and who has that problem
- The primary user and their goal
- What "done" looks like (key outcomes, not features)
- Any known constraints (time, tech stack, platform, budget)
- What already exists that this is similar to or different from

Use their answers to guide which questions to ask. Skip questions if the answer is already clear from context. Aim for 4–7 questions total in this phase.

---

### Phase 2 — Explore Alternatives

Once you have a solid understanding, present **2–3 distinct approaches** for how the project could be built or structured. For each, briefly note:
- The core idea of the approach
- A key advantage
- A key trade-off

Then ask: "Do any of these directions feel right, or would you like to combine or adjust them?"

---

### Phase 3 — Summarize the Design

Synthesize everything into a clear spec with these sections:

```
## Project Name
One-line description

## Problem
Who has this problem, and what is it?

## Goal
What does success look like?

## Approach
The chosen direction, in plain language

## Key Features
Bullet list of the core capabilities (not exhaustive — just what matters)

## Out of Scope
What this project intentionally does NOT do

## Tech Stack / Constraints
Any known platform, language, or tooling decisions

## Open Questions
Anything still unresolved that will need a decision later
```

Present the full summary and ask: "Does this capture the project accurately? What would you like to change?"

Revise based on feedback. Repeat until the user approves.

---

### Phase 4 — Save the Spec

Once approved, save the spec as a markdown file in the current project directory.

- Filename: `spec.md` (or `SPEC.md` if a README already exists at the root)
- Location: the current working directory
- Tell the user where it was saved

Then offer: "Would you like me to break this into an initial task list or suggest a first implementation step?"
