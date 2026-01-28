#!/bin/bash
set -e

echo "Checking Homebrew.."
if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew not found. Install it first:"
    echo ' /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    exit 1
fi
echo "Installing Python3.12"
brew install python@3.12

echo "Installing ffmepg (ffplay)..."
brew install ffmpeg portaudio

echo "Creating virtual environment..."
/opt/homebrew/bin/python3.12 -m venv .venv

echo "Activating venv..."
source .venv/bin/activate

echo "Installing Python Requirements..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Installation complete!"
echo "Activate venv with: source .venv/bin/activate"