#!/bin/bash
# FastReads Taso — double-click on macOS.
cd "$(dirname "$0")" || exit 1
bash ./Start_Viewer.sh
viewer_status=$?
if [ "$viewer_status" -ne 0 ]; then
  echo "FastReads Taso did not start. Read the message above."
  read -r -p "Press Return to close this window…"
fi
exit "$viewer_status"
