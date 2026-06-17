## Description
Please include a summary of the change and the related issue/motivation. Specify which package(s) or files are affected.

Fixes # (issue number)

## Type of Change
Please check the option that applies:
- [ ] **Bug fix** (non-breaking change which fixes an issue)
- [ ] **New feature** (non-breaking change which adds functionality)
- [ ] **Breaking change** (fix or feature that would cause existing functionality to not work as expected)
- [ ] **Documentation update** (changes to READMEs, docs, or inline comments)

## Checklist

### Design & Parity
- [ ] If this introduces a new configuration option or public API, I have implemented equivalent options/behavior in **both** TypeScript and Python packages.
- [ ] The library remains dependency-free (no new external runtime dependencies added).
- [ ] I have updated the relevant package-specific `README.md` or general documentation where necessary.

### Quality & Testing
- [ ] I started the sandbox Express server (`cd sandbox && node server.js`) before running the tests.
- [ ] **TypeScript Package:** I have built and run the TypeScript tests (`npm run build && npm test` inside `packages/smooth-api-ts`) and all tests passed.
- [ ] **Python Package:** I have run the Python tests (`pytest tests/` inside `packages/smooth-api-py`) and all tests passed.
- [ ] I have added new tests to cover my changes.
- [ ] I have commented my code, particularly in hard-to-understand areas, and updated JSDoc/docstrings.
