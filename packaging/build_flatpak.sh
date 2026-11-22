#!/bin/bash
# SplitScreenP2P Flatpak Build and Bundle Script
set -e

echo "=== Building SplitScreenP2P Flatpak ==="

# Check flatpak-builder
if ! command -v flatpak-builder &> /dev/null; then
    echo "Error: flatpak-builder is required to build Flatpak. Install with: sudo apt install flatpak-builder / dnf install flatpak-builder"
    exit 1
fi

# Ensure Freedesktop runtime is installed
flatpak install -y --noninteractive flathub org.freedesktop.Platform//23.08 org.freedesktop.Sdk//23.08 || true

BUILD_DIR="build-flatpak"
REPO_DIR="repo"

rm -rf "$BUILD_DIR"
flatpak-builder --force-clean --repo="$REPO_DIR" "$BUILD_DIR" packaging/org.splitscreenp2p.SplitScreenP2P.yaml

echo "=== Generating Single-File .flatpak Bundle ==="
flatpak build-bundle "$REPO_DIR" SplitScreenP2P.flatpak org.splitscreenp2p.SplitScreenP2P

echo "=== Build Complete! Created SplitScreenP2P.flatpak ==="
echo "To install on any Linux system: flatpak install --user SplitScreenP2P.flatpak"
echo "To run: flatpak run org.splitscreenp2p.SplitScreenP2P"
