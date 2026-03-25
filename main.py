from __future__ import annotations

import argparse
from pathlib import Path

from seating_optimizer.api import (
    run_optimization_from_files,
    save_configurations,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Office seating optimizer: enumerate all legal seating configurations.",
    )
    parser.add_argument(
        "--teams",
        type=str,
        default="data/teams.json",
        help="Path to teams JSON definition file.",
    )
    parser.add_argument(
        "--office-map",
        type=str,
        default="data/office_map.csv",
        help="Path to office map CSV file.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="output/configurations.json",
        help="Path to write configurations JSON file.",
    )
    parser.add_argument(
        "--max-solutions",
        type=int,
        default=None,
        help="Optional maximum number of configurations to generate.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    result = run_optimization_from_files(
        teams_path=args.teams,
        office_map_path=args.office_map,
        max_solutions=args.max_solutions,
    )

    teams = result["teams"]
    configs = result["configurations"]

    print(f"Loaded {len(teams)} teams.")
    print(f"Found {len(configs)} legal configurations.")

    if configs:
        output_path = Path(args.output)
        save_configurations(configs, teams, output_path)
        print(f"Configurations written to {output_path}")


if __name__ == "__main__":
    main()

