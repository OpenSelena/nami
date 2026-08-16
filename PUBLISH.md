# Publishing Nami to PyPI (Automated via GitHub Actions)

Nami uses **GitHub Trusted Publishing** (OIDC) for safe, passwordless automated PyPI releases directly from GitHub Actions.

---

## 1. Initial One-Time Setup

### A. Configure GitHub Environment
1. Go to your GitHub repository: **Settings → Environments**.
2. Click **New environment**.
3. Name it: `pypi`.
4. Click **Configure environment** and save.

### B. Configure PyPI Trusted Publisher
1. Log in to [PyPI Publishing Management](https://pypi.org/manage/project/nami/publishing/).
2. Under **GitHub Actions**, click **Add a new publisher**.
3. Fill in the required details:
   - **PyPI Project Name**: `nami`
   - **Owner**: `OpenSelena`
   - **Repository name**: `nami`
   - **Workflow name**: `publish.yml`
   - **Environment name**: `pypi`
4. Click **Add publisher**.

### C. Revoke Legacy API Tokens
Now that Trusted Publishing is configured:
1. Go to [PyPI Account Settings](https://pypi.org/manage/account/).
2. Scroll to **API tokens**.
3. Revoke any legacy tokens used for previous manual uploads.

---

## 2. Release Procedure

When you are ready to publish a new release:

### 1. Pre-flight Quality & Validation Checks
Run all local release-grade checks before committing:

```bash
# Run test suite
pytest

# Run code style & formatting checks
ruff check src tests
ruff format --check src tests

# Build distribution packages
python -m build

# Validate package distribution artifacts
twine check dist/*
check-wheel-contents dist/*.whl
```

### 2. Update Version Number
Update the single source of truth version string in `pyproject.toml`:
```toml
[project]
name = "nami"
version = "X.Y.Z"
```

*(Note: `src/nami/__init__.py` dynamically resolves the installed distribution version using standard `importlib.metadata`).*

### 3. Commit & Push to GitHub
```bash
git add .
git commit -m "chore(release): bump version to X.Y.Z"
git push origin main
```

### 4. Create & Publish GitHub Release
- Go to your repository on GitHub: **Releases → Draft a new release**.
- Create a new tag (e.g., `vX.Y.Z`).
- Title your release (e.g., `vX.Y.Z - Release Title`) and describe highlights.
- Click **Publish release**.

### 5. Automated Deployment
GitHub Actions will automatically trigger `.github/workflows/publish.yml`, verify artifacts, build distributions, and publish securely to PyPI via OIDC Trusted Publishing without needing stored secrets or passwords.

---

## 3. Manual Fallback (Optional Local Upload)

If you ever need to publish manually from your local development environment:

```bash
python -m pip install --upgrade build twine check-wheel-contents
python -m build
twine check dist/*
twine upload dist/*
```
*(When prompted, set username to `__token__` and password to an active PyPI API token).*
