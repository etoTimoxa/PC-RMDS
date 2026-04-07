#!/bin/bash

# Build script for creating AppImage using Docker
# This script builds a Linux AppImage of the Remote Access Agent

set -e

echo "=========================================="
echo "  Remote Access Agent - AppImage Builder"
echo "=========================================="
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if we're on Linux (AppImage is for Linux)
if [[ "$OSTYPE" != "linux-gnu"* ]] && [[ "$OSTYPE" != "msys" ]] && [[ "$OSTYPE" != "win32" ]]; then
    echo "⚠️  Warning: This script is designed for Linux, but detected: $OSTYPE"
    echo "   You can still try to build, but the AppImage may not work correctly."
fi

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

echo "📁 Project directory: $SCRIPT_DIR"
echo ""

# Check if app_icon.png exists
if [ ! -f "app_icon.png" ]; then
    echo "❌ app_icon.png not found! Please provide an icon file."
    echo "   The icon should be at least 256x256 pixels."
    exit 1
fi

echo "✅ Icon file found: app_icon.png"
echo ""

# Build the Docker image
echo "🔨 Building Docker image..."
docker build -t pc-rmds-appimage-builder . || {
    echo "❌ Docker build failed!"
    exit 1
}

echo "✅ Docker image built successfully"
echo ""

# Create output directory
mkdir -p output

# Run the container to build AppImage
echo "📦 Building AppImage inside container..."
docker run --rm \
    -v "$(pwd)/output:/output" \
    pc-rmds-appimage-builder || {
    echo "❌ AppImage build failed!"
    echo "   Check the Docker output for details."
    exit 1
}

echo ""
echo "=========================================="
echo "  ✅ AppImage build completed!"
echo "=========================================="
echo ""
echo "📁 Output directory: $(pwd)/output"
echo ""
echo "📋 Next steps:"
echo "   1. Make the AppImage executable:"
echo "      chmod +x output/RemoteAccessAgent-*.AppImage"
echo ""
echo "   2. Run the AppImage:"
echo "      ./output/RemoteAccessAgent-*.AppImage"
echo ""
echo "   3. (Optional) Extract AppImage for inspection:"
echo "      ./output/RemoteAccessAgent-*.AppImage --appimage-extract"
echo ""