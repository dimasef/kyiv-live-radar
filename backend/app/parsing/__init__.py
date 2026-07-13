"""Parsing package public API — the only names outside consumers should import."""

from .matcher import DistrictHit, DistrictMatcher, normalize
from .rules import ParseResult, parse_message

__all__ = ["DistrictHit", "DistrictMatcher", "ParseResult", "normalize", "parse_message"]
