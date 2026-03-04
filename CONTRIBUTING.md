# Contributing to queuectl

Thank you for wanting to contribute! Here's how to get started.

## Development Setup

```bash
# Fork and clone
git clone https://github.com/YOUR-USERNAME/Queuectl.git
cd Queuectl

# Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install in dev mode
pip install -e ".[dev]"

# Run migrations
queuectl migrate run
```

## Running Tests

```bash
# Unit tests (fast, no side effects)
pytest tests/test_unit.py -v

# Integration tests (spawns workers)
python tests/test_scenarios.py

# Full suite
python tests/test_phase1_enhancements.py
python tests/test_phase2.py
python tests/test_phase3.py
```

## Making Changes

1. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Write code** following the existing patterns:
   - Use `with self.storage._get_conn() as conn:` for DB access
   - Add type hints to all functions
   - Use Python `logging` module (not `print()`)
   - Add docstrings to public methods

3. **Add tests** for new features in `tests/test_unit.py`

4. **Lint your code**:
   ```bash
   flake8 queuectl/ --max-line-length=120
   ```

5. **Run the full test suite** and make sure everything passes

6. **Commit** with a clear message:
   ```
   feat: add job tagging support
   fix: resolve race condition in claim_job
   docs: update README with pool examples
   ```

7. **Open a Pull Request** against `main`

## Code Style

- **Line length**: 120 characters max
- **Imports**: stdlib → third-party → local, separated by blank lines
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes
- **DB access**: Always use `_get_conn()` context manager; never open raw connections

## Pull Request Guidelines

- Keep PRs focused — one feature or fix per PR
- Include tests for any new functionality
- Update documentation if adding new CLI commands or config options
- All CI checks must pass before merge

## Reporting Bugs

Open an issue with:
- Python version and OS
- Steps to reproduce
- Expected vs actual behavior
- Full error traceback

## Feature Requests

Open an issue describing:
- The problem you're solving
- Your proposed solution
- Any alternatives you considered

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
