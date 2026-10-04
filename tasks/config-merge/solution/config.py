def merge(value):
    return {**value.get('defaults', {}), **value.get('file', {}), **value.get('cli', {})}
