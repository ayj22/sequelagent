# Security

This is a demonstration project on fictional data.

**Protections**: the model's SQL is parsed and checked, runs on a read-only database with no file or network access, and
the database holds no personal data. See the README for the layers.

**Known limits**: there is no user login. The API has an optional shared token and a rate limit; the web app has only a
per-session rate limit. Do not expose either to the internet without authentication in front of it.

**Secrets**: the model key is read from the environment or a git-ignored `.env` file. CI scans the whole history for secrets
and checks dependencies and code every push and weekly.

Report a problem by opening a private security advisory on the repository.
