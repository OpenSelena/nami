# Publishing Nami to PyPI (Automated via GitHub Actions)

Nami uses **GitHub Trusted Publishing** (OIDC) for safe, passwordless automated PyPI releases directly from GitHub Actions.

---

## 1. Initial One-Time Setup

### A. Configure GitHub Environment
1. Go to your GitHub repo: **Settings → Environments**.
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

## 2. How to Release a New Version Later

When you are ready to publish a new release:

1. **Bump Version Number**:
   Update the version string in `pyproject.toml` (`version = "X.Y.Z"`). Everything else in Nami automatically derives from `pyproject.toml` via `importlib.metadata`.

2. **Commit & Push to GitHub**:
   ```bash
   git add .
   git commit -m "Bump version to X.Y.Z"
   git push origin main
   ```

3. **Publish a Release on GitHub**:
   - Go to your repository on GitHub: **Releases → Draft a new release**.
   - Create a new tag (e.g., `vX.Y.Z`).
   - Title your release and click **Publish release**.

4. **Automated Deployment**:
   GitHub Actions will automatically trigger `.github/workflows/publish.yml`, build the package, and publish it securely to PyPI without needing any API tokens or secrets.

---

## 3. Manual Fallback (Optional Local Upload)

If you ever need to publish manually from your machine:

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine upload dist/*
```
*(When prompted, set username to `__token__` and password to an active PyPI API token).*
