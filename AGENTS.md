# Repository guidance

Read CONTRIBUTING.md before changing this repository. Keep private runtime evidence outside the public tree. Review and CI must run offline and must not send input to the game.

## Code Review Rules

- Preserve user takeover, exclusive input ownership, normal host readiness, foreground/path validation, bounded duration and held-input release. A helper configuration or successful ACK never grants input permission or proves game success.
- Verify timing definitions and receipt pairing. Multi-frame observations start at the first operable frame; menu and movement samples stay separate. Keep historical live evidence distinct from offline results and newly adapted tools.
- Flag exposed credentials, personal paths, account identifiers, screenshots, raw operation logs and content whose redistribution rights are unclear. Only project-owned content receives this repository's license.
