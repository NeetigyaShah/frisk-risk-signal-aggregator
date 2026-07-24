import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# tests must be offline + deterministic: never call a real LLM provider
os.environ["LLM_MODE"] = "off"
