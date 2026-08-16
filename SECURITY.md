# Security Policy

## Supported versions

Security fixes are provided for the latest released major version of Nami.

| Version | Supported |
| --- | :---: |
| 4.x | Yes |
| 3.x and older | No |

## Reporting a vulnerability

Please report security issues privately through GitHub Security Advisories for this repository. Do not open a public issue for suspected vulnerabilities involving credential handling, path traversal, command execution, archive corruption, or private content exposure.

Include as much detail as you can safely provide:

- affected Nami version
- operating system and Python version
- reproduction steps
- expected and actual behavior
- whether credentials, cookies, or private media could be exposed

We will acknowledge reports as soon as practical, investigate, and coordinate a fix and disclosure timeline based on severity.

## Credential handling expectations

- Nami never needs PyPI tokens for project releases; publishing uses GitHub Trusted Publishing (OIDC).
- Do not commit cookie files, `.env` files, generated downloads, archives, or local workspace data.
- Cookie files should be Netscape-format exports stored in the configured cookies directory with restrictive local permissions where possible.
- `nami doctor` is designed to be read-only and does not make network requests.

## Scope

In scope:

- path traversal or workspace escape vulnerabilities
- unsafe subprocess invocation or argument handling
- accidental credential disclosure in output, logs, packages, or workflows
- archive corruption that causes unintended overwrite or deletion
- release workflow weaknesses that could publish unauthorized packages

Out of scope:

- upstream platform blocking, rate limits, or extractor availability changes
- vulnerabilities only present in unsupported Nami versions
- issues requiring already compromised local user accounts or malicious system-level dependencies
