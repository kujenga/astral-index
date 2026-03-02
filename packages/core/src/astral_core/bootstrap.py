import warnings

from dotenv import load_dotenv


def bootstrap() -> None:
    """Shared CLI startup: load env vars and silence known-harmless warnings."""
    load_dotenv()
    warnings.filterwarnings("ignore", module="requests")
    warnings.filterwarnings(
        "ignore", message="nltk is not installed", category=UserWarning
    )
