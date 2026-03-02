import warnings

from dotenv import load_dotenv

# Set warning filters at import time so they're active before transitive
# imports (e.g. scrapers → httpx → requests) trigger module-load warnings.
warnings.filterwarnings("ignore", module="requests")
warnings.filterwarnings("ignore", message="nltk is not installed", category=UserWarning)


def bootstrap() -> None:
    """Shared CLI startup: load env vars and silence known-harmless warnings."""
    load_dotenv()
