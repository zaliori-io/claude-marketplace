---
description: Re-authenticate with Saxo (opens browser for OAuth approval)
---

Run the Saxo PKCE login flow. The browser opens for user approval; on success the access + refresh tokens are stored in macOS Keychain and the preflight hook resumes silent refreshes.

!`python3 ${CLAUDE_PLUGIN_ROOT}/skills/saxo/scripts/saxo_auth.py login`
