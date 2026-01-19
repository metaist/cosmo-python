# Agent Guidelines

This document captures preferences for AI agents (Claude, etc.) working on this codebase.

## GitHub Issues and Comments

- Use prefixes: `add:`, `fix:`, `update:`, `remove:`, `refactor:`
- Keep titles lowercase where possible
- Use backticks for code references in titles
- Add `aigen` label for AI-generated issues
- Include "Created by {Model Name} during {code review | discussion with...}" at start of issue/comment body
- Prefer flat (or no) hierarchy in the markdown body; use bolding appropriately

## Development Commands

- **Quick validation**: `ds dev` (lint + script validation; run before commits)
- **Build single version**: `ds build 3.12.8`
- **Build all versions**: `ds build-all`
- **Run smoke tests**: `ds smoke dist/python-3.12.8-cosmo.com`
- **Run all smoke tests**: `ds smoke-all`
- **Clean build artifacts**: `ds clean`

## Shell Commands

- Use `uv` instead of `pip` (faster, more modern)
- Use `fd` instead of `find` (simpler syntax, respects `.gitignore`)
- Use `rg` instead of `grep` (faster, better defaults)
- For long-running commands (builds), pipe to a file so user can follow: `cmd 2>&1 | tee /tmp/build.log`
- If a command seems to hang, check what's happening rather than waiting silently

## Code Style

- Follow existing patterns in the codebase
- Use type hints (modern syntax: `Path | None` not `Optional[Path]`)
- Prefer editing existing files over creating new ones
- Don't add unnecessary comments or docstrings to unchanged code
- Try to maintain 100% unit test coverage
- Don't delete build artifacts (e.g., `work/`) unnecessarily—only delete what needs rebuilding

## Workflow

- Create an issue before implementing non-trivial changes
- Add comments to existing issues when scope expands
- Discuss structural/organizational changes before implementing (avoid churn)

## Commits and Pushing

- Commit frequently as you complete fixes, but **do not push until asked** or until a batch of related changes is ready
- Pushing to `main` triggers CI, so batch multiple commits before pushing to limit CI runs to a few times per hour
- **Always run `ds dev` before committing** to catch lint, type check, and test issues early
- When ready to push, the user will explicitly ask or approve

## Commit Messages

- Use same prefix convention as issues: `add:`, `fix:`, `update:`, `refactor:`
- Keep titles lowercase where possible
- Titles are sentence fragments (no trailing period)
- Use backticks for code references in titles (e.g., `fix: bug in \`keep_going\` parsing`)
- Reference issue numbers with `(#123)` or `(closes #123)`
- Include `Co-Authored-By: {Model Name} <noreply@anthropic.com>` in commit body
