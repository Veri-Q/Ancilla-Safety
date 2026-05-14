import sys

from ae.run_suite import main


if __name__ == "__main__":
    raise SystemExit(main(["generate-tables", *sys.argv[1:]]))
