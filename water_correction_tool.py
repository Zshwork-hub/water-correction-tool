import sys

from water_tool.water_app import main


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        sys.exit(0)
    main()
