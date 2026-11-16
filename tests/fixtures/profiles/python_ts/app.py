from src.store import Store, load


def main():
    s = Store()
    s.save("a")
    return load("b")
