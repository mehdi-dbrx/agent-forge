"""BrickForge CLI entry point."""
import sys

if sys.version_info < (3, 9):
    sys.exit(f"brickforge requires Python 3.9+. You have {sys.version.split()[0]}.")


def main():
    """Start the BrickForge Setup App."""
    from brickforge import __version__, USER_DIR

    if "--version" in sys.argv or "-v" in sys.argv:
        print(f"brickforge {__version__}")
        return

    print(f"\n  BrickForge {__version__}")
    print(f"  Setup App starting at http://localhost:9000")
    print(f"  Logs: {USER_DIR}")
    print(f"  Press Ctrl+C to stop\n")

    from brickforge.server import main as server_main
    server_main()


if __name__ == "__main__":
    main()
