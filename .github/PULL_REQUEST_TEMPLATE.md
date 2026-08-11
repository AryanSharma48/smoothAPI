## Description
Please include a summary of the change and the related issue/motivation. Specify which package(s) or files are affected (e.g. `smooth-api-ts`, `smooth-api-py`, `examples`, or `website`).

Fixes # (issue number)

## Type of Change
Please check the option that applies:
- [ ] **Bug fix** (non-breaking change which fixes an issue)
- [ ] **New feature** (non-breaking change which adds functionality)
- [ ] **Breaking change** (fix or feature that would cause existing functionality to not work as expected)
- [ ] **Documentation/Website update** (changes to READMEs, examples, inline comments, or the documentation website)

## Checklist

### Design & Parity
- [ ] If this introduces a new configuration option or public API, I have implemented equivalent options/behavior in **both** TypeScript and Python packages.
- [ ] The core packages remain dependency-free (no new external runtime dependencies added).
- [ ] I have updated the relevant package-specific `README.md` or general documentation where necessary.
- [ ] If applicable, I have updated the `examples` or `website` to reflect these changes.

### Quality & Testing
- [ ] I started the sandbox Express server (`cd sandbox && npm install && npm start`) in a separate terminal before running the tests.
- [ ] **TypeScript Package:** I have run the TypeScript tests (`npm install && npm run build && npm test` inside `packages/smooth-api-ts`) and all tests passed.
- [ ] **Python Package:** I have run the Python tests (`pip install -e ".[dev]" && pytest` inside `packages/smooth-api-py`) and all tests passed.
- [ ] I have added new tests to cover my changes.
- [ ] I have commented my code, particularly in hard-to-understand areas, and updated JSDoc/docstrings.
