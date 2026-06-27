# Contributing to SmoothAPI

First off, thank you for taking the time to contribute! Contributions are what make the open-source community such an amazing place to learn, inspire, and create.

Join our [Discord Server](https://discord.gg/2NabXnQzmv) to connect with the maintainers and other contributors!


All types of contributions are welcome:
- 🐛 **Reporting & Fixing Bugs**
- 📝 **Improving Documentation**
- 💡 **Proposing & Implementing Features**
- 🧪 **Adding Examples or Test Coverage**

---

## Repository Layout

SmoothAPI is a dual-language API resilience and fault-tolerance library. The workspace is organized as follows:

```text
smooth-api/
├── examples/                   # Broswer based examples for SmoothAPI
├── packages/
│   ├── smooth-api-ts/          # TypeScript package (@codingaryan/smoothapi)
│   └── smooth-api-py/          # Python package (smoothapi-py)
├── sandbox/                    # Express-based chaos server (used by integration tests)
├── website/                    # Documentation wesbsite
├── README.md                   # Project overview
└── CONTRIBUTING.md             # You are here!
```

---

## Development Prerequisites

To develop locally, you will need:
- **Node.js** (v18 or higher)
- **npm** (v9 or higher)
- **Python** (v3.10 or higher)
- **pip**

---

## Local Development Setup

### 1. Start the Sandbox Server
Both the TypeScript and Python integration tests rely on a local Express server running in the background to simulate transient API failures, circuit breaker states, and timeouts.

Before running any tests, start the sandbox:
```bash
# Navigate to the sandbox directory
cd sandbox

# Install dependencies
npm install

# Start the chaos server
node server.js
```
The server runs on `http://localhost:3001` and provides `/health`, `/chaos`, and other endpoints. Keep this terminal open.

---

## Package-Specific Development

### TypeScript Package (`packages/smooth-api-ts`)

1. **Install dependencies**:
   ```bash
   cd packages/smooth-api-ts
   npm install
   ```

2. **Build the project**:
   To compile the TypeScript source files to the `dist` directory:
   ```bash
   npm run build
   ```

3. **Watch mode**:
   To automatically recompile files when changes are saved:
   ```bash
   npm run build:watch
   ```

4. **Run tests**:
   Make sure the Sandbox Server is running first, then execute:
   ```bash
   npm test
   ```
   This compiles the test files and runs the suite using Node's native test runner.

---

### Python Package (`packages/smooth-api-py`)

1. **Set up a virtual environment** (recommended):
   ```bash
   cd packages/smooth-api-py
   python -m venv .venv
   
   # Activate virtualenv (Windows)
   .venv\Scripts\activate
   # Activate virtualenv (macOS/Linux)
   source .venv/bin/activate
   ```

2. **Install package in editable mode with dev tools**:
   ```bash
   pip install -e ".[dev]"
   ```

3. **Run tests**:
   Make sure the Sandbox Server is running first, then execute:
   ```bash
   pytest tests/ -v
   ```

---

## Coding Standards & Quality

To keep the repository clean, please adhere to these guidelines:

### Core Philosophy
- **Zero Dependencies**: Keep the packages lightweight. Do not add external runtime dependencies unless absolutely necessary and approved by maintainers.
- **Dual Language Alignment**: When adding configuration options or features, try to maintain parity between the TypeScript and Python implementations so that their API shapes and features stay equivalent.
- **Clean Code**: Follow the Single Responsibility Principle, keep functions small, use descriptive naming, and prefer code clarity over excessive comments.

### Testing
- No changes should be merged without accompanying tests.
- Ensure all tests pass locally for both Python and TypeScript before submitting a PR.
- Add regression tests if you are fixing a bug, and feature tests if you are adding capabilities.

### Commit Messages
We encourage semantic/structured commit messages to help automate release notes and versioning:
- `feat: <description>` (new feature for the user)
- `fix: <description>` (bug fix for the user)
- `docs: <description>` (changes to documentation)
- `style: <description>` (formatting, missing semi colons, etc; no production code change)
- `refactor: <description>` (refactoring production code, eg. renaming a variable)
- `test: <description>` (adding missing tests, refactoring tests)
- `chore: <description>` (updating dev tasks, package dependencies, etc)

---

## Pull Request Process

1. Create a new branch from `main` (e.g., `feature/timeout-support` or `bugfix/retry-jitter`).
2. Make your changes in the codebase.
3. Verify that your changes compile successfully and all linting/types check out.
4. Run the full test suite with the local sandbox running.
5. Update documentation if you are changing or introducing features.
6. Open a Pull Request pointing to the `main` branch. Provide a clear description of the problem solved, changes made, and proof of testing.
