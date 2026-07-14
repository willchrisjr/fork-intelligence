# Security policy

Do not open an issue containing an unpatched vulnerability, credential, private
repository content, or exploit details.

Use GitHub's private vulnerability reporting flow:

<https://github.com/willchrisjr/fork-intelligence/security/advisories/new>

Include the affected commit/version, impact, safe reproduction details, and any
suggested mitigation. Repository code analyzed by Fork Intelligence is untrusted
input; never attach secrets or execute repository-supplied instructions while
investigating a report.

Operational incidents and credential exposure follow `docs/OPERATIONS.md` and
the threat boundaries in `docs/SECURITY.md`.
