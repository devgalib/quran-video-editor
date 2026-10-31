# Security policy

## Supported versions

Only the latest release gets fixes.

## Reporting a vulnerability

Please do **not** open a public issue. Use GitHub's private reporting instead:
**Security → Report a vulnerability** on this repository
(<https://github.com/devgalib/quran-video-editor/security/advisories/new>).

Include what you found, how to reproduce it, and its impact. You can expect a first reply within a
week. Once a fix is released, you will be credited in the advisory unless you prefer not to be.

## Things to know

- The app runs FFmpeg on files you choose. Project files are JSON and are never executed, but they
  contain file paths, so only open projects you trust.
- The MCP server (`qve mcp`) runs locally over stdio and can read and write files that the user
  running it can access. Only connect it to MCP clients you trust.
