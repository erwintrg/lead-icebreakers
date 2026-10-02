"""lead-icebreakers: fixed-template first lines for B2B lead lists.

A model fills two slots of a sentence a person wrote (casual first name, company as people
say it), a second model pass checks every finished line, and a human overrides file beats both.
"""
from .leads import COLUMN
from .pipeline import Result, enrich_rows
from .template import Change, Draft, render

__all__ = ["COLUMN", "Change", "Draft", "Result", "enrich_rows", "render"]
__version__ = "0.1.0"
