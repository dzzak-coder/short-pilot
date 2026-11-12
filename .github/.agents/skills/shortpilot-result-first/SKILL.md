---
name: shortpilot-result-first
description: Work on ShortPilot with result-first communication, avoiding status chatter and unverified claims. Use for any ShortPilot analysis, bug fix, or feature change.
---

# ShortPilot — résultat d'abord

This project is used interactively. The user values a fast, verified outcome
more than narration of intermediate work.

- Do not announce that a change is ready until it has been implemented and
  verified with the smallest relevant test.
- Do not send repeated progress messages. Communicate only a concrete finding,
  a blocker that needs the user, or the verified outcome.
- Make one coherent change set per request. Avoid speculative iterations that
  do not directly improve the requested result.
- If an assumption materially affects the implementation, state it once before
  editing. Otherwise decide from the code and proceed.
- When a problem cannot be objectively validated locally, say so plainly; do
  not claim it is fixed. Give the shortest practical test for the user.
- Keep final handoff to: what changed, what was verified, and whether a restart
  or a new render is needed.

