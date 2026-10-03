"""Lanceur du widget (double-cliquer sous Windows : aucune console ne s'ouvre)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prayer_widget.widget import main  # noqa: E402

if __name__ == "__main__":
    main()
