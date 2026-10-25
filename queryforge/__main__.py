import argparse
import json
from pathlib import Path
from .demo import make_demo_db
from .engine import QueryEngine, QueryError


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description='QueryForge research-driven natural language SQL engine')
    parser.add_argument('--database', default=str(root/'data'/'finance.sqlite'))
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('seed')
    ask = commands.add_parser('ask')
    ask.add_argument('question')
    commands.add_parser('bench')
    args = parser.parse_args()
    if args.command == 'seed':
        print(make_demo_db(args.database))
        return
    if args.command == 'bench':
        from .benchmark import run_benchmark
        print(json.dumps(run_benchmark(args.database, root/'data'/'benchmark.json'), indent=2))
        return
    try:
        result = QueryEngine(args.database).ask(args.question)
        print(json.dumps(result.as_dict(), indent=2))
    except QueryError as exc:
        parser.error(str(exc))

if __name__ == '__main__':
    main()
