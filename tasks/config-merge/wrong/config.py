def merge(value):
    return {**value.get('cli', {}), **value.get('file', {}), **value.get('defaults', {})}
