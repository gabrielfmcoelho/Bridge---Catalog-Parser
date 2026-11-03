"""Lint rules. Write a new one by subclassing FileRule or CrossRule and adding it to a CatalogKind."""

from .base import CrossRule, FileRule, Finding, Rule

__all__ = ["CrossRule", "FileRule", "Finding", "Rule"]
