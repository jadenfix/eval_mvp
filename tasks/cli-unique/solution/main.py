import argparse, json, sys
parser = argparse.ArgumentParser()
parser.add_argument('--sort', action='store_true')
parser.add_argument('--unique', action='store_true')
args = parser.parse_args()
numbers = json.load(sys.stdin)
if args.unique:
    numbers = list(dict.fromkeys(numbers))
print(json.dumps(sorted(numbers) if args.sort else numbers))
