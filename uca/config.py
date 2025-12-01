import os
from dotenv import load_dotenv

load_dotenv()

# API Keys (Placeholders for now)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MIDJOURNEY_API_KEY = os.getenv("MIDJOURNEY_API_KEY") # If using an API wrapper
FLUX_API_KEY = os.getenv("FLUX_API_KEY")

# Configuration
DEFAULT_AGENT_MODE = "Store Owner"
MAX_PRODUCTS_PER_RUN = 5
TREND_VELOCITY_THRESHOLD = 7.0 # Minimum score to trigger product generation

# Paths
OUTPUT_DIR = os.getenv("UCA_OUTPUT_DIR", "./uca_output")
