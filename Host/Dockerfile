# Multi-stage Dockerfile for building Linux AppImage
# This Dockerfile creates a self-contained AppImage with all dependencies

# ==============================================================================
# Stage 1: Build environment
# ==============================================================================
FROM ubuntu:22.04 AS builder

# Avoid interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies for building and running the application
RUN apt-get update && apt-get install -y \
    # Python
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    \
    # PyQt6 runtime dependencies
    libgl1-mesa-glx \
    libxkbcommon-x11-0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-xinerama0 \
    libxcb-xfixes0 \
    libegl1 \
    libopengl0 \
    \
    # Screenshot dependencies (mss, PIL)
    libxcb-shm0 \
    libxcb-shape0 \
    \
    # Input control dependencies (pynput, pyautogui)
    libxtst6 \
    libx11-xcb1 \
    libxcb-record0 \
    libxi6 \
    \
    # Build tools
    build-essential \
    git \
    wget \
    curl \
    \
    # AppImage tools
    desktop-file-utils \
    libfuse2 \
    file \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Download and setup linuxdeploy tools
WORKDIR /tmp

# Download linuxdeploy
RUN wget -q https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage \
    && chmod +x linuxdeploy-x86_64.AppImage \
    && ./linuxdeploy-x86_64.AppImage --appimage-extract \
    && mv squashfs-root /opt/linuxdeploy

# Download linuxdeploy-plugin-qt
RUN wget -q https://github.com/linuxdeploy/linuxdeploy-plugin-qt/releases/download/continuous/linuxdeploy-plugin-qt-x86_64.AppImage \
    && chmod +x linuxdeploy-plugin-qt-x86_64.AppImage \
    && ./linuxdeploy-plugin-qt-x86_64.AppImage --appimage-extract \
    && mv squashfs-root /opt/linuxdeploy-plugin-qt

# Download appimagetool
RUN wget -q https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage \
    && chmod +x appimagetool-x86_64.AppImage \
    && ./appimagetool-x86_64.AppImage --appimage-extract \
    && mv squashfs-root /opt/appimagetool

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Create virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# Install Python dependencies (Linux only - exclude Windows-specific packages)
# Note: pywin32 is excluded as it's Windows-only
RUN pip install --no-cache-dir \
    PyQt6>=6.4.0 \
    pymysql>=1.0.2 \
    psutil>=5.9.0 \
    pyautogui>=0.9.53 \
    mss>=6.1.0 \
    Pillow>=9.0.0 \
    websockets>=10.0 \
    pynput>=1.7.6 \
    boto3>=1.26.0

# ==============================================================================
# Stage 2: Create AppDir structure
# ==============================================================================
FROM ubuntu:22.04 AS appdir-creator

ENV DEBIAN_FRONTEND=noninteractive

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    # Python
    python3 \
    python3-venv \
    \
    # PyQt6 runtime dependencies
    libgl1-mesa-glx \
    libxkbcommon-x11-0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-xinerama0 \
    libxcb-xfixes0 \
    libegl1 \
    libopengl0 \
    \
    # Screenshot dependencies
    libxcb-shm0 \
    libxcb-shape0 \
    \
    # Input control dependencies
    libxtst6 \
    libx11-xcb1 \
    libxcb-record0 \
    libxi6 \
    \
    # Misc
    libfuse2 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create AppDir structure
WORKDIR /app
RUN mkdir -p AppDir/usr/bin \
    && mkdir -p AppDir/usr/lib \
    && mkdir -p AppDir/usr/share/applications \
    && mkdir -p AppDir/usr/share/icons/hicolor/256x256/apps \
    && mkdir -p AppDir/usr/share/icons/hicolor/128x128/apps \
    && mkdir -p AppDir/usr/share/icons/hicolor/64x64/apps \
    && mkdir -p AppDir/usr/share/icons/hicolor/48x48/apps \
    && mkdir -p AppDir/usr/share/icons/hicolor/32x32/apps \
    && mkdir -p AppDir/usr/share/icons/hicolor/16x16/apps \
    && mkdir -p AppDir/usr/lib/python3.10/site-packages

# Copy virtual environment from builder
COPY --from=builder /opt/venv /app/AppDir/usr/venv

# Copy application files
COPY --from=builder /app/main.py AppDir/usr/bin/
COPY --from=builder /app/agent/ AppDir/usr/bin/agent/
COPY --from=builder /app/core/ AppDir/usr/bin/core/
COPY --from=builder /app/collectors/ AppDir/usr/bin/collectors/
COPY --from=builder /app/storage/ AppDir/usr/bin/storage/
COPY --from=builder /app/utils/ AppDir/usr/bin/utils/

# Copy icon (multiple sizes for better display)
COPY app_icon.png AppDir/usr/share/icons/hicolor/256x256/apps/app_icon.png
COPY app_icon.png AppDir/app_icon.png

# Create desktop file with proper icon paths
RUN cat > AppDir/RemoteAccessAgent.desktop << 'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=Remote Access Agent
Comment=Remote desktop access and monitoring agent
Exec=run.sh
Icon=app_icon
Terminal=false
Categories=Network;RemoteAccess;Utility;
Keywords=remote;desktop;access;monitoring;
EOF

# Copy desktop file to applications directory
RUN cp AppDir/RemoteAccessAgent.desktop AppDir/usr/share/applications/

# Create run script that properly sets up the environment
RUN cat > AppDir/run.sh << 'EOF'
#!/bin/bash

# Get the directory where the AppImage is mounted
BASE_DIR="$(dirname "$(readlink -f "$0")")"

# Set up environment variables
export LD_LIBRARY_PATH="${BASE_DIR}/usr/lib/x86_64-linux-gnu:${BASE_DIR}/usr/lib:${LD_LIBRARY_PATH}"
export PYTHONPATH="${BASE_DIR}/usr/lib/python3.10/site-packages:${BASE_DIR}/usr/bin:${PYTHONPATH}"
export QT_QPA_PLATFORM=xcb

# Activate virtual environment
source "${BASE_DIR}/usr/venv/bin/activate"

# Run the application
exec python3 "${BASE_DIR}/usr/bin/main.py" "$@"
EOF

RUN chmod +x AppDir/run.sh

# Copy symlinks for python
RUN ln -sf /app/AppDir/usr/venv/bin/python3 /app/AppDir/usr/bin/python3 \
    && ln -sf /app/AppDir/usr/venv/bin/pip /app/AppDir/usr/bin/pip

# ==============================================================================
# Stage 3: Final build - Create AppImage
# ==============================================================================
FROM ubuntu:22.04 AS final

ENV DEBIAN_FRONTEND=noninteractive

# Install tools needed for AppImage creation
RUN apt-get update && apt-get install -y \
    libfuse2 \
    wget \
    file \
    desktop-file-utils \
    squashfs-tools \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy linuxdeploy tools
COPY --from=builder /opt/linuxdeploy /opt/linuxdeploy
COPY --from=builder /opt/linuxdeploy-plugin-qt /opt/linuxdeploy-plugin-qt
COPY --from=builder /opt/appimagetool /opt/appimagetool

# Copy AppDir from previous stage
COPY --from=appdir-creator /app/AppDir /app/AppDir

WORKDIR /app

# Create output directory
RUN mkdir -p /output

# Build the AppImage
CMD ["/bin/bash", "-c", "\
    echo 'Building AppImage...' && \
    echo 'Creating AppDir structure...' && \
    mkdir -p /tmp/AppDir/usr/bin && \
    mkdir -p /tmp/AppDir/usr/lib && \
    mkdir -p /tmp/AppDir/usr/share/applications && \
    mkdir -p /tmp/AppDir/usr/share/icons/hicolor/256x256/apps && \
    echo 'Copying files...' && \
    cp -r /app/AppDir/usr/venv /tmp/AppDir/usr/ && \
    cp -r /app/AppDir/usr/bin/* /tmp/AppDir/usr/bin/ && \
    cp /app/AppDir/run.sh /tmp/AppDir/ && \
    cp /app/AppDir/app_icon.png /tmp/AppDir/ && \
    cp /app/AppDir/app_icon.png /tmp/AppDir/usr/share/icons/hicolor/256x256/apps/app_icon.png && \
    cp /app/AppDir/RemoteAccessAgent.desktop /tmp/AppDir/ && \
    cp /app/AppDir/RemoteAccessAgent.desktop /tmp/AppDir/usr/share/applications/ && \
    echo 'Creating AppImage...' && \
    /opt/appimagetool/usr/bin/appimagetool /tmp/AppDir /output/RemoteAccessAgent-x86_64.AppImage && \
    echo 'AppImage created successfully!' && \
    ls -la /output/ && \
    chmod +x /output/RemoteAccessAgent-x86_64.AppImage \
"]
