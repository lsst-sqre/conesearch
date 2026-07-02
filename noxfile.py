"""nox configuration for Conesearch."""

import nox
from nox_uv import session

# Default sessions.
nox.options.sessions = ["lint", "typing", "test", "coverage-report"]

# Other nox defaults.
nox.options.default_venv_backend = "uv"
nox.options.reuse_existing_virtualenvs = True


@session(name="coverage-report", requires=["test"], uv_groups=["dev"])
def coverage_report(session: nox.Session) -> None:
    """Generate a code coverage report from the test suite."""
    session.run("coverage", "report", *session.posargs)


@session(uv_only_groups=["lint"], uv_no_install_project=True)
def lint(session: nox.Session) -> None:
    """Run pre-commit hooks."""
    session.run("pre-commit", "run", "--all-files", *session.posargs)


@session(uv_groups=["dev"])
def run(session: nox.Session) -> None:
    """Run the development server with auto-reload for code changes."""
    session.run("uvicorn", "conesearch.main:app", "--reload")


@session(uv_groups=["dev"])
def test(session: nox.Session) -> None:
    """Run the test suite."""
    session.run(
        "pytest",
        "--cov=conesearch",
        "--cov-branch",
        "--cov-report=",
        *session.posargs,
    )


@session(uv_groups=["dev", "typing"])
def typing(session: nox.Session) -> None:
    """Run mypy."""
    session.run(
        "mypy",
        *session.posargs,
        "src/conesearch",
        "tests",
    )
