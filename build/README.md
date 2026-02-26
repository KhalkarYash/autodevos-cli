# Building AutoDevOS Installers

This directory contains scripts and configurations to build standalone installers for AutoDevOS.

## Prerequisites

```bash
pip install pyinstaller
```

## Quick Build (Local)

### macOS
```bash
chmod +x build/build-macos.sh
./build/build-macos.sh
# Output: dist/AutoDevOS-arm64.dmg (or x86_64)
```

### Windows
```cmd
build\build-windows.bat
# Then use Inno Setup to compile build\installer.iss
# Output: dist/AutoDevOS-Setup-0.1.0.exe
```

### Linux
```bash
chmod +x build/build-linux.sh
./build/build-linux.sh
# Output: dist/AutoDevOS-x86_64.AppImage
# Output: dist/AutoDevOS-amd64.deb
```

## Automated Builds (GitHub Actions)

The project includes a GitHub Actions workflow that automatically builds installers for all platforms when you create a release tag:

```bash
git tag v0.1.0
git push origin v0.1.0
```

This will:
1. Build executables for Windows, macOS (Intel + ARM), and Linux
2. Create installers (.exe, .dmg, .AppImage, .deb)
3. Create a draft GitHub Release with all artifacts

## Installation by End Users

### Windows
1. Download `AutoDevOS-Setup-x.x.x.exe`
2. Run installer (adds `ados` to PATH automatically)
3. Open terminal and run: `ados`

### macOS
1. Download `AutoDevOS-arm64.dmg` (Apple Silicon) or `AutoDevOS-x86_64.dmg` (Intel)
2. Open DMG and drag to Applications
3. Add to PATH: `echo 'export PATH="/Applications/AutoDevOS.app/Contents/MacOS:$PATH"' >> ~/.zshrc`
4. Open terminal and run: `ados`

### Linux (AppImage)
```bash
wget https://github.com/KhalkarYash/autodevos-cli/releases/download/vX.X.X/AutoDevOS-x86_64.AppImage
chmod +x AutoDevOS-x86_64.AppImage
./AutoDevOS-x86_64.AppImage
# Or move to /usr/local/bin/ados for system-wide access
```

### Linux (Debian/Ubuntu)
```bash
wget https://github.com/KhalkarYash/autodevos-cli/releases/download/vX.X.X/AutoDevOS-amd64.deb
sudo dpkg -i AutoDevOS-amd64.deb
ados
```

## Files

- `autodevos.spec` - PyInstaller specification file
- `build-macos.sh` - macOS build script (creates .dmg)
- `build-windows.bat` - Windows build script
- `build-linux.sh` - Linux build script (creates .AppImage and .deb)
- `installer.iss` - Inno Setup script for Windows installer

## Notes

- The built executable includes all Python dependencies
- No Python installation required on target machines
- First run may take a few seconds as the bundled Python initializes
- For Ollama support, users still need Ollama installed separately
