#!/usr/bin/env python3
"""Entry point for the Embitel Competitor Intelligence Agent.

Usage:
    python main.py chat
    python main.py refresh [--competitor NAME]
    python main.py report [--send] [--save preview.html]
    python main.py weekly
    python main.py competitors
    python main.py stats
"""

from competitor_agent.cli import main

if __name__ == "__main__":
    main()
