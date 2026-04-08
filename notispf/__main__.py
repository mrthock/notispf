import sys
from notispf.app import App


def main():
    if len(sys.argv) < 2:
        print("Usage: notispf <file>")
        sys.exit(1)
    app = App(sys.argv[1])
    app.run()


if __name__ == "__main__":
    main()
