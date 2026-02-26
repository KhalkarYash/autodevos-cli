#!/bin/bash
# Build script for macOS .dmg

set -e

echo "🔨 Building AutoDevOS for macOS..."

# Ensure we're in project root
cd "$(dirname "$0")/.."

# Install build dependencies
pip install pyinstaller dmgbuild

# Build the executable
pyinstaller build/autodevos.spec --clean --noconfirm

# Create DMG
echo "📦 Creating DMG installer..."

cat > /tmp/dmg_settings.py << 'EOF'
import os

# DMG settings
application = defines.get('app', 'dist/AutoDevOS.app')
appname = os.path.basename(application)

format = 'UDBZ'
size = None
files = [application]
symlinks = {'Applications': '/Applications'}
icon_locations = {
    appname: (140, 120),
    'Applications': (500, 120)
}
background = 'builtin-arrow'
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
sidebar_width = 180
window_rect = ((200, 120), (660, 400))
default_view = 'icon-view'
icon_size = 128
text_size = 12
EOF

# Build DMG
dmgbuild -s /tmp/dmg_settings.py "AutoDevOS" "dist/AutoDevOS-$(uname -m).dmg"

echo "✅ Built: dist/AutoDevOS-$(uname -m).dmg"
