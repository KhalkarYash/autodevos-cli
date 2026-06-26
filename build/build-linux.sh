#!/bin/bash
# Build script for Linux (AppImage and .deb)

set -e

echo "🔨 Building AutoDevOS for Linux..."

# Ensure we're in project root
cd "$(dirname "$0")/.."

VERSION="0.1.0"
ARCH=$(uname -m)

# Install build dependencies
pip install pyinstaller

# Build the executable
pyinstaller build/autodevos.spec --clean --noconfirm

echo "📦 Creating AppImage..."

# Create AppDir structure
APPDIR="dist/AutoDevOS.AppDir"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Copy executable
cp dist/ados "$APPDIR/usr/bin/"

# Create desktop file
cat > "$APPDIR/usr/share/applications/autodevos.desktop" << EOF
[Desktop Entry]
Name=AutoDevOS
Exec=ados
Icon=autodevos
Type=Application
Categories=Development;Utility;
Terminal=true
Comment=AI-powered coding assistant for your terminal
EOF

# Create AppRun
cat > "$APPDIR/AppRun" << 'EOF'
#!/bin/bash
SELF=$(readlink -f "$0")
HERE=${SELF%/*}
export PATH="${HERE}/usr/bin:${PATH}"
exec "${HERE}/usr/bin/ados" "$@"
EOF
chmod +x "$APPDIR/AppRun"

# Link desktop and icon to root
ln -sf usr/share/applications/autodevos.desktop "$APPDIR/autodevos.desktop"
# Create a simple icon placeholder (replace with actual icon)
echo "Replace with actual icon" > "$APPDIR/autodevos.png"

# Download appimagetool if not present
if [ ! -f /tmp/appimagetool ]; then
    echo "Downloading appimagetool..."
    wget -q "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -O /tmp/appimagetool
    chmod +x /tmp/appimagetool
fi

# Build AppImage
ARCH=$ARCH /tmp/appimagetool "$APPDIR" "dist/AutoDevOS-${VERSION}-${ARCH}.AppImage"

echo ""
echo "📦 Creating .deb package..."

# Create deb structure
DEBDIR="dist/autodevos_${VERSION}_amd64"
mkdir -p "$DEBDIR/DEBIAN"
mkdir -p "$DEBDIR/usr/bin"
mkdir -p "$DEBDIR/usr/share/applications"

# Copy executable
cp dist/ados "$DEBDIR/usr/bin/"

# Create control file
cat > "$DEBDIR/DEBIAN/control" << EOF
Package: autodevos
Version: ${VERSION}
Section: devel
Priority: optional
Architecture: amd64
Maintainer: AutoDevOS <support@autodevos.dev>
Description: AI-powered coding assistant for your terminal
 AutoDevOS is an AI-powered coding assistant that runs in your terminal.
 It supports multiple LLM providers including OpenAI, Anthropic, Google,
 and local models via Ollama.
EOF

# Create desktop file for deb
cat > "$DEBDIR/usr/share/applications/autodevos.desktop" << EOF
[Desktop Entry]
Name=AutoDevOS
Exec=ados
Icon=autodevos
Type=Application
Categories=Development;Utility;
Terminal=true
Comment=AI-powered coding assistant for your terminal
EOF

# Build deb
dpkg-deb --build "$DEBDIR"
mv "dist/autodevos_${VERSION}_amd64.deb" "dist/AutoDevOS-${VERSION}-amd64.deb"

echo ""
echo "✅ Built:"
echo "   - dist/AutoDevOS-${VERSION}-${ARCH}.AppImage"
echo "   - dist/AutoDevOS-${VERSION}-amd64.deb"
