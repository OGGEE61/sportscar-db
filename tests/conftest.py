"""Keep the tests' reveal budget out of logs/: base_scraper reads REVEAL_STATE_FILE when imported."""
import os
import tempfile

os.environ["REVEAL_STATE_FILE"] = os.path.join(tempfile.mkdtemp(prefix="reveal-state-"), "reveal_state.json")
