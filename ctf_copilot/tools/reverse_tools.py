"""Reverse tooling is data-driven via :mod:`ctf_copilot.tools.registry` (category
`reverse`). This module is the place for richer Python-native wrappers.

TODO: add native helpers that don't shell out, e.g.:
  - forensic: scapy PCAP flow reconstruction, OLE/RTF parsing
  - reverse:  capstone-based quick disassembly preview
  - pwn:      pwntools ELF/ROP helpers, libc-database lookups
  - stego:    LSB plane extraction without external tools
  - osint:    Wayback CDX (only when user enables internet OSINT)
"""
from .registry import Category

CATEGORY = Category.REVERSE
