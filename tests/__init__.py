import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # tests never open real windows or tray icons
