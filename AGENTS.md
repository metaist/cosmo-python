# Project-Specific (cosmo-python)

**Goal**: Build portable, trustworthy versions of every supported Python release.

**Principles** (for resolving tradeoffs):

- **Portability**: Must work on Linux, macOS, and Windows (in that order)
- **Supply chain trust**: Prefer upstream sources, verify checksums, minimize dependencies
- **Reproducibility**: Same inputs → same outputs; pin versions, document build environments

## Development Commands

| Command                                 | Purpose                                                                  |
| --------------------------------------- | ------------------------------------------------------------------------ |
| `ds dev`                                | **Must pass before every commit** — lint, type check, tests, spell check |
| `ds build 3.12.8`                       | Build single Python version                                              |
| `ds build-all`                          | Build all Python versions                                                |
| `ds smoke dist/python-3.12.8-cosmo.com` | Run smoke tests on a binary                                              |
| `ds smoke-all`                          | Run all smoke tests                                                      |
| `ds clean`                              | Clean build artifacts                                                    |

## Validation Rules

**`ds dev` is mandatory before commits.** Check the **full output**, not just the last few lines.

Common issues caught by `ds dev`:

- **cspell**: Unknown words → add to `.cspell.json`
- **ruff**: Python lint/format issues
- **shellcheck**: Shell script issues
- **clang-format**: C code formatting
- **ty/pyright/mypy**: Type errors

If `ds dev` fails, fix the issue before committing. Don't assume CI will catch it.

## Project-Specific Notes

- **Never want external libb2** — defeats purpose of portable binary; use Python's built-in blake2
- **sys.platform should reflect runtime OS** — not a fake "cosmo" platform
- **Rebuilding requires removing outputs** — Python's build caches aggressively; use `--clean` flag
- **cosmoext testing**: `./scripts/smoke-cosmoext.sh dist/python-X.Y.Z-cosmo.com --ext all`

---

# General Principles (all projects)

## Preflight

Before starting any task:

1. Confirm you have the tools to do the work _and_ verify it succeeded
2. Identify the goal and immediate task; restate if conversation is long or after compaction
3. Check for relevant GitHub issues; add comments for significant progress
4. Clarify: **quick experiment** (user will check) or **deep dive** (use judgment)?
5. If you need more thinking time, ask to adjust thinking tokens (off / low / medium / high)

## Working Style

- Default to minimal changes; propose scope before larger refactors
- Don't delete files you didn't create (others may be working in same directory)
- Don't delete build artifacts needlessly; prefer idempotent approaches
- Follow existing patterns in the codebase
- Prefer editing existing files over creating new ones
- Don't add unnecessary comments or docstrings to unchanged code

## Communication

- Number items in summaries so user can reference specifics
- Present meaningful alternatives and wait—unless this is a deep dive
- If solving a different problem than started, stop and check in
- For long-running commands: `cmd 2>&1 | tee /tmp/build.log`
- If something hangs, investigate rather than waiting silently
- Notify when long-running tasks complete

## Shell Commands

**Do not use `find` or `grep`.** Use these instead:

| Instead of | Use | Why |
|------------|-----|-----|
| `find` | `fd` | Respects `.gitignore`, skips `work/`, `.venv/`, etc. |
| `grep` | `rg` | Same—avoids searching 12k+ files in build directories |
| `pip` | `uv` | Faster, better dependency resolution |

This repo has large build artifacts (`work/`) that make `find`/`grep` return thousands of irrelevant results and take 75+ seconds instead of milliseconds.

## Code Style

- Type hints with modern syntax (`Path | None` not `Optional[Path]`)
- Require 100% test coverage; task isn't complete without it
- `# pragma: no cover` only for trivial `if __name__ == "__main__"` or truly unreachable code
- Test observable behavior, not implementation details
- Prefer comprehensive edge case coverage

## Workflow

1. Create an issue before implementing non-trivial changes
2. Add comments to issues when scope expands or for significant progress
3. Update issue body to reflect overall goal and remaining tasks
4. Discuss structural/organizational changes before implementing
5. **Run `ds dev` and check full output** before committing
6. Commit frequently, but **do not push until asked**
7. Pushing to `main` triggers CI; batch commits to limit runs

## Commit Messages

Format: `prefix: description (#issue)`

| Prefix      | Use for                                    |
| ----------- | ------------------------------------------ |
| `add:`      | New features, files, capabilities          |
| `fix:`      | Bug fixes, corrections                     |
| `update:`   | Changes to existing functionality, docs    |
| `remove:`   | Deletions                                  |
| `refactor:` | Code restructuring without behavior change |

Rules:

- Lowercase titles, sentence fragments (no trailing period)
- Backticks for code: ``fix: bug in `keep_going` parsing``
- Reference issues: `(#123)` or `(closes #123)`
- Include `Co-Authored-By: {Model Name} <noreply@anthropic.com>` in body

## GitHub Issues and Comments

- Same prefix convention as commits
- Lowercase titles; backticks for code references
- Add `aigen` label for AI-generated issues
- Start body: "Created by {Model Name + Version} during {context}..."
- Prefer flat hierarchy in markdown; use bolding appropriately

## Conventions

- Dates: ISO 8601 (`YYYY-MM-DD`)
- Prefer well-adopted standards where they exist
