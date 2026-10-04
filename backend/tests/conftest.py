import os

# Tests never start the background refresh loop (app/jobs/refresh.py).
os.environ["AUTO_REFRESH"] = "0"
