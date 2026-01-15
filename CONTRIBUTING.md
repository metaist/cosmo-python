# Contributing

## Toolchain

This project requires these tools to set up and run the project (tested on Linux):

- [`ds`](https://github.com/metaist/ds#install)
- [`gh`](https://github.com/cli/cli#installation)
- [`git`](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
- [`jq`](https://jqlang.github.io/jq/download/)
- [`npx`](https://docs.npmjs.com/cli/commands/npx) (part of [`npm`](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm); used for [`cspell`](https://cspell.org/docs/installation/), [`shellcheck`](https://github.com/koalaman/shellcheck))
- [`uv`](https://github.com/astral-sh/uv#installation) & [`uvx`](https://docs.astral.sh/uv/guides/tools/) (part of `uv`)

Build dependencies (installed by `scripts/00-setup/system-deps.sh`):

- Standard C build tools (`build-essential`, `autoconf`, `libtool`, etc.)
- `gpg` for signature verification

## Local Development

```bash
# get the code
git clone git@github.com:metaist/cosmo-python.git
cd cosmo-python

# install system deps (requires sudo)
./scripts/00-setup/system-deps.sh

# build a single Python version
./scripts/build.sh 3.13.11

# build all versions
./scripts/build.sh --all
```

Periodically, you should run:

```bash
ds dev  # lint, spell check, cog check, script validation
```

## Making a Release

Checkout `prod`:

```bash
git checkout prod
git merge --no-ff --no-edit main
```

Update `CHANGELOG.md`. To see recently closed issues run:

```bash
gh issue list --state closed --limit 50 --json number,title,closedAt \
  --jq 'sort_by(.closedAt) | reverse | .[] | "#\(.number): \(.title)"'
```

You can also look at the [unreleased](https://github.com/metaist/cosmo-python/compare/prod...main) log.

Sections order is: `Fixed`, `Changed`, `Added`, `Deprecated`, `Removed`, `Security`.

```markdown
---

[YYYYMMDD-HHMMSS]: https://github.com/metaist/cosmo-python/compare/PREVIOUS...YYYYMMDD-HHMMSS

## [YYYYMMDD-HHMMSS] - YYYY-MM-DD

**Fixed**

**Changed**

**Added**

**Deprecated**

**Removed**

**Security**
```

Move items from `[Unreleased]` to the new version section.

### Final checks and push

```bash
# final checks
ds dev

# commit changelog
git add CHANGELOG.md
git commit -m "update: CHANGELOG for release"

# push to prod
git push origin prod

# trigger release workflow manually from GitHub Actions
# (release.yaml creates the tag and uploads artifacts)
```

After the release workflow completes:

```bash
# fast-forward main to prod
git checkout main
git merge --ff-only prod
git push origin main
```

[Review the release on GitHub](https://github.com/metaist/cosmo-python/releases).

## Dependency Updates

The `check-updates.yaml` workflow runs weekly to detect new versions:

1. It creates a PR with updated `versions.json` and `README.md`
2. CI builds all Python versions to verify compatibility
3. A maintainer reviews and merges the PR
4. A maintainer triggers the release workflow

To check for updates manually:

```bash
./scripts/check-updates.sh --dry-run  # see what would change
./scripts/check-updates.sh            # apply changes
```

## Adding a New Python Version

When a new Python minor version is released (e.g., 3.15):

1. Add version to `versions.json` with SHA256 and sigstore info
2. Create `scripts/02-python/3.15/` directory if patches needed
3. Test build: `./scripts/build.sh 3.15.0`
4. Run smoke tests: `./scripts/02-python/smoke.sh dist/python-3.15.0-cosmo.com`
5. Update `python.latest` in `versions.json`

## Adding GPG Keys for New Upstream Maintainers

If an upstream project rotates their signing key:

1. Fetch the new key: `gpg --keyserver keyserver.ubuntu.com --recv-keys <fingerprint>`
2. Verify the key via official project channels
3. Export to `keys.asc`: `gpg --armor --export <fingerprints...> > keys.asc`
4. Update `versions.json` with the new fingerprint for the version
