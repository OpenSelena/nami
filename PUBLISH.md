# Publishing Nami

Nami publishes to PyPI through GitHub Actions Trusted Publishing (OIDC). Releases must be built by GitHub from a validated annotated tag on `main`; do not upload with local API tokens.

## One-time PyPI and GitHub setup

1. In GitHub, create an environment named `pypi` under **Settings → Environments**.
2. In PyPI, open the `nami` project publishing settings.
3. Add a GitHub trusted publisher with:
   - Owner: `OpenSelena`
   - Repository: `nami`
   - Workflow name: `publish.yml`
   - Environment name: `pypi`
4. Revoke old PyPI upload tokens used for this project.
5. Protect the `pypi` environment with appropriate reviewers if desired.

## Release checklist

Use a fresh checkout or a clean working tree.

```bash
git --no-pager status --short
```

1. Update the version in `pyproject.toml`.
2. Update `CHANGELOG.md` by moving the release from `Unreleased` to the release date.
3. Run the local validation suite:

   ```bash
   PYTHONPATH=src python -m pytest -q
   python -m ruff check src tests
   python -m ruff format --check src tests
   rm -rf dist build .audit-dist
   python -m build
   python -m twine check dist/*
   check-wheel-contents dist/*.whl
   git --no-pager diff --check
   ```

4. Review changed files explicitly. Avoid `git add .`; stage only intentional files, for example:

   ```bash
   git add pyproject.toml CHANGELOG.md README.md PUBLISH.md SECURITY.md src tests .github
   ```

5. Commit and push to `main`.
6. Create an annotated stable SemVer tag from `main`:

   ```bash
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin main
   git push origin vX.Y.Z
   ```

7. Draft and publish a GitHub Release using the existing tag.

The `publish.yml` workflow validates that the tag:

- is a stable `vX.Y.Z` tag
- is annotated
- points at the release target commit when that target can be resolved
- is an ancestor of `origin/main`
- matches the version in `pyproject.toml`

It then builds once, validates metadata and wheel contents, smoke-installs the artifact on Ubuntu and Windows, and publishes with OIDC from the protected `pypi` environment.

## What not to do

- Do not use `git add .` without reviewing the worktree.
- Do not publish from a dirty local checkout.
- Do not use a PyPI API token fallback.
- Do not set `skip-existing`; repeated releases should fail loudly.
- Do not publish from lightweight tags or non-`main` commits.
- Do not rebuild locally and upload different artifacts from the GitHub release artifacts.
