# Contributing

Contributions are welcome, and they are greatly appreciated! Every little bit helps, and credit will always be given.

You can contribute in many ways:

## Types of Contributions

### Report Bugs

Report bugs at https://github.com/iLiftALot/intelliyaml/issues.

If you are reporting a bug, please include:

- Your operating system name and version.
- Any details about your local setup that might be helpful in troubleshooting.
- Detailed steps to reproduce the bug.

### Fix Bugs

Look through the GitHub issues for bugs. Anything tagged with "bug" and "help wanted" is open to whoever wants to implement it.

### Implement Features

Look through the GitHub issues for features. Anything tagged with "enhancement" and "help wanted" is open to whoever wants to implement it.

### Write Documentation

IntelliYaml could always use more documentation, whether as part of the official docs, in docstrings, or even on the web in blog posts, articles, and such.

### Submit Feedback

The best way to send feedback is to file an issue at https://github.com/iLiftALot/intelliyaml/issues.

If you are proposing a feature:

- Explain in detail how it would work.
- Keep the scope as narrow as possible, to make it easier to implement.
- Remember that this is a volunteer-driven project, and that contributions are welcome :)

## Get Started!

Ready to contribute? Here's how to set up `intelliyaml` for local development.

1. Fork the `intelliyaml` repo on GitHub.
2. Clone your fork locally:

   ```sh
   git clone git@github.com:your_name_here/intelliyaml.git
   cd intelliyaml
   ```

3. Install the project and development dependencies with `uv`:

   ```sh
   uv sync --dev
   ```

   This checkout uses local editable sources for some sibling packages under `[tool.uv.sources]`. If you are not using that local workspace layout, install those packages from PyPI or adjust the local source paths before syncing.

4. Create a branch for local development:

   ```sh
   git checkout -b name-of-your-bugfix-or-feature
   ```

   Now you can make your changes locally.

5. When you're done making changes, run the relevant quality checks:

   ```sh
   uv run ruff format --check .
   uv run ruff check .
   uv run pyright
   uv run pytest
   ```

6. Commit your changes and push your branch to GitHub:

   ```sh
   git add .
   git commit -m "Your detailed description of your changes."
   git push origin name-of-your-bugfix-or-feature
   ```

7. Submit a pull request through the GitHub website.

## Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.
2. If the pull request adds or changes public behavior, update README.md and the relevant page under `docs/`.
3. The pull request should work for Python 3.13 or newer.
4. If user-facing behavior changes, add an entry to HISTORY.md.

## Tips

To run a subset of tests:

```sh
uv run pytest tests/test_utils.py
```

## Deploying

A reminder for the maintainers on how to deploy. Make sure all your changes are committed (including an entry in HISTORY.md). Then run:

```sh
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv build
```

Update the version in `pyproject.toml`, tag the release, and push:

```sh
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push
git push --tags
```

## Code of Conduct

Please note that this project is released with a [Contributor Code of Conduct](CODE_OF_CONDUCT.md). By participating in this project you agree to abide by its terms.
