#!/bin/bash
set -e
if [ -f "packages/smooth-api-ts/package.json" ]; then
  npm test --prefix packages/smooth-api-ts
fi
if [ -f "packages/smooth-api-py/pyproject.toml" ]; then
  pytest packages/smooth-api-py/tests/ -v
fi
