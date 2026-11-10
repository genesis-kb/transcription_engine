# Instructions for AI coding agents

These instructions are for any AI agent working in this repository (Claude Code, Copilot,
Cursor, Codex, etc.). The human you work with must follow `AI_POLICY.md`. Help them comply.

## Before writing code
- Ask the human which issue this work is for. If there is none, suggest opening one first.
- Read the relevant existing code and follow its conventions, structure and libraries.
  Don't introduce new dependencies, patterns or frameworks unless asked to.

## While working
- Keep the diff minimal and limited to the issue. No unrelated refactors, renames or reformatting.
- Explain non-obvious decisions to the human as you go, so they can defend them in review.
- Run the project's tests, linter and build. Report the real output, and never claim tests pass without running them.

## Before a commit or PR
- Keep the AI co-author trailer in commit messages. Never remove it.
- Don't open or push PRs on your own. The human decides when to submit.
- Don't fill in the PR description's **Why**, **What changed** or **How I tested** for the human.
  Give them a short summary, and ask them to write those sections in their own words.
- Remind the human to tick the **AI usage** box honestly.

## Never
- Write replies to reviewer comments for the human to paste.
- Generate bug or security reports that the human hasn't reproduced.
- Touch secrets, credentials or files listed in `.gitignore`.

<!-- Add project-specific rules below: build commands, architecture notes, no-go areas. -->
