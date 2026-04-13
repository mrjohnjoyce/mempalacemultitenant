#!/usr/bin/env python3
"""
MemPalace — Give your AI a memory. No API key required.
"""

import os
import sys
import shlex
import argparse
from pathlib import Path

from .config import MempalaceConfig

def _get_config(args):
    """Returns a MempalaceConfig instance based on CLI args."""
    return MempalaceConfig(config_dir=args.palace)

def cmd_init(args):
    import json
    from .entity_detector import scan_for_detection, detect_entities, confirm_entities
    from .room_detector_local import detect_rooms_local

    config = _get_config(args)
    print(f"\n  Initializing Palace in: {config.config_dir}")

    files = scan_for_detection(args.dir)
    if files:
        detected = detect_entities(files)
        if confirmed := confirm_entities(detected, yes=getattr(args, "yes", False)):
            entities_path = Path(args.dir).expanduser().resolve() / "entities.json"
            with open(entities_path, "w") as f:
                json.dump(confirmed, f, indent=2)

    detect_rooms_local(project_dir=args.dir, yes=getattr(args, "yes", False))
    config.init()
    print(f"  Done. Config saved to {config._config_file}")

def cmd_mine(args):
    config = _get_config(args)
    palace_path = config.palace_path
    
    if args.mode == "convos":
        from .convo_miner import mine_convos
        mine_convos(convo_dir=args.dir, palace_path=palace_path, wing=args.wing, agent=args.agent)
    else:
        from .miner import mine
        mine(project_dir=args.dir, palace_path=palace_path, wing_override=args.wing, agent=args.agent)

def cmd_search(args):
    from .searcher import search
    config = _get_config(args)
    search(query=args.query, palace_path=config.palace_path, wing=args.wing, room=args.room, n_results=args.results)

def cmd_status(args):
    from .miner import status
    config = _get_config(args)
    status(palace_path=config.palace_path)

def cmd_mcp(args):
    base_cmd = "python -m mempalace.mcp_server"
    if args.palace:
        base_cmd += f" --palace {shlex.quote(str(Path(args.palace).expanduser()))}"
    print(f"  claude mcp add mempalace -- {base_cmd}")

def main():
    parser = argparse.ArgumentParser(description="MemPalace Multi-Tenant CLI")
    parser.add_argument("--palace", help="Path to the palace directory")
    
    # Use global args early to set environment variables
    # This must be done BEFORE any other imports that use MempalaceConfig
    args_global, _ = parser.parse_known_args()
    if args_global.palace:
        os.environ["MEMPALACE_PALACE_PATH"] = os.path.abspath(os.path.expanduser(args_global.palace))

    sub = parser.add_subparsers(dest="command")
    
    p_init = sub.add_parser("init")
    p_init.add_argument("dir")
    p_init.add_argument("--yes", action="store_true")
    
    p_mine = sub.add_parser("mine")
    p_mine.add_argument("dir")
    p_mine.add_argument("--mode", choices=["projects", "convos"], default="projects")
    p_mine.add_argument("--wing", default=None)
    p_mine.add_argument("--agent", default="mempalace")
    
    p_search = sub.add_parser("search")
    p_search.add_argument("query")
    p_search.add_argument("--wing", default=None)
    p_search.add_argument("--room", default=None)
    p_search.add_argument("--results", type=int, default=5)
    
    sub.add_parser("status")
    sub.add_parser("mcp")
    
    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    dispatch = {
        "init": cmd_init,
        "mine": cmd_mine,
        "search": cmd_search,
        "status": cmd_status,
        "mcp": cmd_mcp,
    }
    dispatch[args.command](args)

if __name__ == "__main__":
    main()
