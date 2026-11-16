import os


def load(path):
    """Read a file."""
    with open(path) as fh:
        return fh.read()


class Store:
    def save(self, rec):
        return helper(rec)


def helper(rec):
    return load(os.fspath(rec))
