#!/bin/bash
# ============================================================
# BLUFIRE MARKETING — RUFLO AGENT INSTALLER
# Run this script to install all 37 agents into Claude Code
# Usage: bash INSTALL.sh
# ============================================================

AGENTS_DIR="$HOME/.claude/agents/blufire"

echo ""
echo "🔥 Blufire Marketing — Ruflo Agent Installer"
echo "============================================="
echo ""

# Create the agents directory
mkdir -p "$AGENTS_DIR/core"
mkdir -p "$AGENTS_DIR/outbound"
mkdir -p "$AGENTS_DIR/social"
mkdir -p "$AGENTS_DIR/sales"
mkdir -p "$AGENTS_DIR/cs"
mkdir -p "$AGENTS_DIR/web"
mkdir -p "$AGENTS_DIR/ai"
mkdir -p "$AGENTS_DIR/creative"
mkdir -p "$AGENTS_DIR/video"

# Copy all agent files
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp -r "$SCRIPT_DIR/core/"* "$AGENTS_DIR/core/"
cp -r "$SCRIPT_DIR/outbound/"* "$AGENTS_DIR/outbound/"
cp -r "$SCRIPT_DIR/social/"* "$AGENTS_DIR/social/"
cp -r "$SCRIPT_DIR/sales/"* "$AGENTS_DIR/sales/"
cp -r "$SCRIPT_DIR/cs/"* "$AGENTS_DIR/cs/"
cp -r "$SCRIPT_DIR/web/"* "$AGENTS_DIR/web/"
cp -r "$SCRIPT_DIR/ai/"* "$AGENTS_DIR/ai/"
cp -r "$SCRIPT_DIR/creative/"* "$AGENTS_DIR/creative/"
cp -r "$SCRIPT_DIR/video/"* "$AGENTS_DIR/video/"

COUNT=$(find "$AGENTS_DIR" -name "*.md" | wc -l)
echo "✅ Installed $COUNT agent files to: $AGENTS_DIR"
echo ""
echo "📁 Structure:"
find "$AGENTS_DIR" -name "*.md" | sort | sed "s|$AGENTS_DIR/||g" | sed 's/^/   /'
echo ""
echo "🚀 Next steps:"
echo "   1. Open Claude Code (npx claude or claude command)"
echo "   2. Agents are automatically available in every session"
echo "   3. Test with: npx ruflo agent list"
echo "   4. Spawn an agent: npx ruflo agent spawn --name the-roofing-queen"
echo ""
echo "📌 Also add agents to your project .claude/agents/ for project-scoped access:"
echo "   mkdir -p .claude/agents && cp -r $AGENTS_DIR/* .claude/agents/"
echo ""
echo "Done. The Blufire agent system is live. 🔥"
