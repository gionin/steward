#!/bin/bash
cd "$(dirname "$0")" || exit 1

if [ ! -x ".venv/bin/python" ]; then
  echo "The environment is missing. Please run setup.command first."
  read -p "Press Enter to close."
  exit 1
fi

echo "Starting Steward...  (close the app window to come back here)"
echo
.venv/bin/python app.py

echo
echo "------------------------------------------------------------"
echo "Steward has exited."
echo "If it crashed, the reason is shown above and saved in:"
echo "   ~/.steward/steward.log"
echo "------------------------------------------------------------"
read -p "Press Enter to close."
