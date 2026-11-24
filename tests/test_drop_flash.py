"""Idea 5 (BiBi Nov 24): soft drop flash = ~60% white for 2 frames (was 100% for 4 frames)."""
import re
from pathlib import Path

TSX = (Path(__file__).resolve().parents[1] / "remotion" / "src" / "JuraijEdit.tsx").read_text()


def test_flash_constants():
    op = float(re.search(r"DROP_FLASH_OPACITY = ([0-9.]+)", TSX).group(1))
    fr = int(re.search(r"DROP_FLASH_FRAMES = (\d+)", TSX).group(1))
    assert 0.5 <= op <= 0.65 and fr == 2


def test_flash_uses_constants_not_full_white():
    block = TSX[TSX.index("Drop flash on the punch word"):]
    block = block[: block.index(")}") + 2]
    assert "frame < p.dropFrame + DROP_FLASH_FRAMES" in block
    assert "[DROP_FLASH_OPACITY, 0]" in block
    assert "[1, 0]" not in block and "dropFrame + 4" not in block


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
