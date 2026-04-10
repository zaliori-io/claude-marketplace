#!/usr/bin/env bash
# Clean reinstall of the saxotrader Claude Code plugin.
# Run this any time the plugin needs a fresh install or version update.
# Your config (~/.config/saxo/config.json) and Keychain tokens are untouched.

set -e

MARKETPLACE="zaliori-io/claude-marketplace"
PLUGIN_ID="saxotrader"
PLUGINS_DIR="$HOME/.claude/plugins"

echo "==> Removing cached plugin files..."
rm -rf "$PLUGINS_DIR/cache/$PLUGIN_ID"
rm -rf "$PLUGINS_DIR/marketplaces/zaliori-io"

echo "==> Removing stale marketplace registration..."
python3 - <<'PY'
import json, pathlib, sys
p = pathlib.Path.home() / ".claude/plugins/known_marketplaces.json"
if not p.exists():
    sys.exit(0)
data = json.loads(p.read_text())
removed = [k for k in list(data) if k == "zaliori-io"]
for k in removed:
    del data[k]
p.write_text(json.dumps(data, indent=2))
if removed:
    print(f"  Removed: {', '.join(removed)}")
PY

echo "==> Uninstalling existing plugin (errors here are safe to ignore)..."
claude plugin uninstall "$PLUGIN_ID" 2>/dev/null || true

echo "==> Fetching latest marketplace data..."
claude plugin marketplace add "$MARKETPLACE"

echo "==> Installing plugin..."
claude plugin install "$PLUGIN_ID@zaliori-io"

echo ""
echo "Done. Restart Claude Code to load the updated plugin."
