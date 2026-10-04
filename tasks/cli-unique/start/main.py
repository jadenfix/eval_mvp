import argparse, json, sys
parser = argparse.ArgumentParser()
parser.add_argument('--sort', action='store_true')
args = parser.parse_args()
numbers = json.load(sys.stdin)
print(json.dumps(sorted(numbers) if args.sort else numbers))
