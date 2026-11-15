# Security

AgentForge v0.1 supports owned synthetic local evaluations, not production actions.
Read the [threat model and review](docs/security.md) before running fixtures or
installing adapters. Installed Python plugins, the host and Docker remain trusted.

A public repository and private advisory channel are not configured in this working
copy. Before publication, the maintainer should enable a private reporting channel
and document its verified URL. Do not send secrets or exploit details to an invented
contact address or a public issue. Until a private channel is available, report only
a minimal non-sensitive issue to the maintainer through an existing trusted channel.

Include affected revision, platform, synthetic reproduction, expected/observed
behavior and sanitized evidence. Never test against production or include real
credentials/customer data. No response-time guarantee or supported-release policy
has been established; this is pre-release software.
