# Project-Specific (cosmo-python)

**Goal**: Build portable, trustworthy versions of every supported Python release.

**Principles** (for resolving tradeoffs):

- **Portability**: Must work on Linux, macOS, and Windows (in that order)
- **Supply chain trust**: Prefer upstream sources, verify checksums, minimize dependencies
- **Reproducibility**: Same inputs → same outputs; pin versions, document build environments

**Development Commands**:

- `ds dev` — quick validation (lint + tests); **must** pass before commits
- `ds build 3.12.8` — build single version
- `ds build-all` — build all versions
- `ds smoke dist/python-3.12.8-cosmo.com` — run smoke tests
- `ds smoke-all` — run all smoke tests
- `ds clean` — clean build artifacts

# General Principles (all projects)

## Preflight

Before starting any task:

- Confirm you have the tools to do the work _and_ verify it succeeded
- Identify the goal and the immediate task; restate if the conversation is long or after compaction
- Check if there's a relevant GitHub issue; add a comment if relevant
- Clarify: is this a **quick experiment** (I'll check your work) or a **deep dive** (use your judgment, take your time)?
- If you need more thinking time, ask me to adjust thinking tokens (off / low / medium / high)

## Working Style

- Default to minimal changes; propose scope before larger refactors
- Don't delete files you didn't create (humans or other agents may be working in the same directory)
- Don't delete build artifacts needlessly; prefer idempotent approaches to keep things moving along
- Follow existing patterns in the codebase
- Prefer editing existing files over creating new ones
- Don't add unnecessary comments or docstrings to unchanged code

## Communication

- Number items in summaries and feedback so I can reference specifics
- If there are meaningful alternatives, present options and wait—unless this is a deep dive
- If you're solving a different problem than we started with, stop and check in
- For long-running commands, pipe output so I can follow: `cmd 2>&1 | tee /tmp/build.log`
- If something seems to hang, investigate rather than waiting silently
- Notify me when long-running tasks complete

## Shell Commands

- Use `uv` instead of `pip`
- Use `fd` instead of `find` (respects `.gitignore`)
- Use `rg` instead of `grep` (faster, better defaults)

## Code Style

- Use type hints with modern syntax (`Path | None` not `Optional[Path]`)
- Require 100% test coverage; task isn't complete without it
- `# pragma: no cover` only for trivial `if __name__ == "__main__"` or truly unreachable defensive code
- Test observable behavior, not implementation details; tests should survive refactors
- Prefer comprehensive edge case coverage

## Workflow

- Create an issue before implementing non-trivial changes
- Add comments to existing issues when scope expands or for significant progress
- Change the top-level body of the issue to reflect the overall goal and remaining tasks; mark tasks as complete after making relevant comments in the issue
- Discuss structural/organizational changes before implementing (avoid churn)
- Always run `ds dev` before committing (lint + type check + tests)
- Commit frequently, but **do not push until asked**
- Pushing to `main` triggers CI; batch commits to limit runs

## Commit Messages

- Prefix: `add:`, `fix:`, `update:`, `remove:`, `refactor:`
- Lowercase titles, sentence fragments (no trailing period)
- Backticks for code references: `fix: bug in \`keep_going\` parsing`
- Reference issues: `(#123)` or `(closes #123)`
- Include `Co-Authored-By: {Model Name} <noreply@anthropic.com>` in body

## GitHub Issues and Comments

- Same prefix convention as commits
- Lowercase titles; backticks for code references
- Add `aigen` label for AI-generated issues (create it if it doesn't exist)
- Start body with: "Created by {Model Name + Version} during {code review | discussion with...}"
- Prefer flat hierarchy in markdown; use bolding appropriately

## Conventions

- Dates: ISO 8601 (`YYYY-MM-DD`)
- Prefer well-adopted standards where they exist
