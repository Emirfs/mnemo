"""mnemo — persistent, portable, cross-AI memory over a markdown vault."""

__version__ = "0.2.0"

from .config import Config
from .index import Index
from .note import Note
from .search import Search

__all__ = ["Config", "Index", "Note", "Search", "__version__"]
