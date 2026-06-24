#!/bin/bash
cd "$(dirname "$0")" || exit 1
echo "============================================"
echo "  Custodian  -  setup (run this once)"
echo "============================================"
echo

if ! python3 -m venv .venv; then
  echo
  echo "Could not create the environment. Is python3 installed?"
  read -p "Press Enter to close."
  exit 1
fi

.venv/bin/python -m pip install --upgrade pip

if [ "$(uname)" = "Linux" ]; then
  .venv/bin/python -m pip install "pywebview[qt]" \
    || .venv/bin/python -m pip install "pywebview[gtk]" \
    || .venv/bin/python -m pip install pywebview
else
  .venv/bin/python -m pip install pywebview
fi

if [ $? -ne 0 ]; then
  echo
  echo "Installing pywebview failed. See the messages above."
  read -p "Press Enter to close."
  exit 1
fi

echo
echo "============================================"
echo "  Setup complete. Double-click run.command to start."
echo "============================================"
read -p "Press Enter to close."
