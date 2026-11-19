FILES = {
    "pkg/mod.py": '''import os

CONST_A = 1
CONST_B = 2


@decorator
def handler(a, b):
    """doc"""
    x = a + b
    return x


class Widget:
    size = 3

    def render(self):
        return handler(1, 2)

    def other(self):
        return self.render()


def helper(a):
    return a
''',
    "pkg/use.py": '''from pkg.mod import handler, Widget


def go():
    handler(1, 2)
    w = Widget()
    w.render()
    handler(3, 4)
    handler(5, 6)
    return {"handler": 1}
''',
    "docs/guide.md": "call handler(1, 2) to run\n",
}
