# AGENTS

This file defines repository rules for AI agents and contributors.

## Mandatory Rules

1. Keep changes small and scoped.
2. Do not keep multiple old versions of documentation.
3. Remove stale docs when they are replaced.
4. Update documentation in the same change whenever project behavior changes.
5. Keep UI code, generation logic, config, assets, output, hardware files, and logs in their assigned folders.

## Documentation Update Requirement

If you modify code that changes behavior, architecture, setup, commands, folder layout, or hardware configuration:
- update the matching human docs: `README.md`, `GETTING_STARTED.md`, `PROJECT_DESCRIPTION.md`, `DOCS_INDEX.md`, or `Spotter-Control_v3/README.md`
- update `AGENT_DOC.md` with a short machine-readable note

A pull request is incomplete if code changed but docs did not.

## Documentation Split

- Human docs: concise, task-focused, low-noise.
- `AGENT_DOC.md`: compact tracking context for AI and automation.

## Review Checklist

- Is any doc now stale?
- Did we remove replaced docs?
- Are setup steps still accurate?
- Does `python main.py` still work from `Spotter-Control_v3`?
- Did `python -m compileall -q app` pass?
- Is `AGENT_DOC.md` updated?
