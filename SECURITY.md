# queuectl v2.0.0 - Known Limitations & Security

# For production deployments, this file documents important considerations.

# SECURITY: shell=True mitigation
# Commands are validated against dangerous patterns before execution.
# Set command_validation=true (default) in config to enable this.
# To disable: queuectl config set command-validation false

# AUTHENTICATION: The web dashboard supports basic API token auth.
# Set the QUEUECTL_API_TOKEN environment variable to enable:
#   export QUEUECTL_API_TOKEN=your-secret-token
# All API requests must include: Authorization: Bearer <token>

# SINGLE MACHINE: This system uses SQLite and is designed for single-machine use.
# For distributed deployments, consider migrating to PostgreSQL + Redis.
