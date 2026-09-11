# Security policy

DeepGuard processes untrusted uploads and web-originated claim text, so security
issues are taken seriously.

## Supported version

The `main` branch is the actively maintained research version.

## Reporting

For non-sensitive bugs, open a GitHub issue with reproduction steps.

For a vulnerability that could expose user data, allow remote code execution,
bypass upload controls, or otherwise create material risk, use GitHub's private
vulnerability-reporting/security-advisory flow when available instead of posting
exploit details publicly.

Do not include private user media, API keys, access tokens, passwords, or other
secrets in a report.

## Deployment notes

- Use HTTPS in production.
- Keep `DEEPGUARD_ENABLE_EXTERNAL_MODELS=0` unless you intentionally operate a
  compatible trained-model service.
- Restrict `DEEPGUARD_CORS_ORIGINS` and `DEEPGUARD_TRUSTED_HOSTS` to your final
  deployment when possible.
- Treat claim-search and model-provider credentials as server secrets.
- Keep dependencies and GitHub Actions updated; Dependabot is configured.
