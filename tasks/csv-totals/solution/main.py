import csv, io, json, sys
value = json.load(sys.stdin)
try:
    reader = csv.DictReader(io.StringIO(value['csv']))
    if reader.fieldnames != ['name', 'amount']:
        raise ValueError()
    totals = {}
    for row in reader:
        if None in row or row['name'] is None or row['amount'] is None:
            raise ValueError()
        totals[row['name']] = totals.get(row['name'], 0) + int(row['amount'])
    print(json.dumps(totals))
except (ValueError, TypeError):
    print(json.dumps({'error': 'invalid'}))
