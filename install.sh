#!/bin/bash
set -e

echo "Checking Homebrew.."
if ! command -v brew >/dev/null 2>&1; then
    echo "Homebrew not found. Install it first:"
    echo ' /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    exit 1
fi

echo "Installing ffmepg (ffplay)..."
brew install ffmpeg

echo "Creating virtual environment..."
python3 -m venv .venv

echo "Activating venv..."
source .venv/bin/activate

echo "Installing Python Requirements..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Installation complete!"
echo "Activate venv with: source .venv/bin/activate"