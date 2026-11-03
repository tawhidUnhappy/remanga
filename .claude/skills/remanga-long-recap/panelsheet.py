"""Contact sheet of cut panels matching glob patterns: panelsheet.py OUT.jpg CELL_W CELL_H COLS file..."""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

out, cw, ch, cols = Path(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
files = [Path(f) for f in sys.argv[5:]]
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
rows = (len(files) + cols - 1) // cols
sheet = Image.new("RGB", (cols * cw, rows * ch), (90, 90, 90))
d = ImageDraw.Draw(sheet)
for i, f in enumerate(files):
    im = Image.open(f).convert("RGB")
    size = f"{im.width}x{im.height}"
    im.thumbnail((cw - 8, ch - 26))
    x, y = (i % cols) * cw, (i // cols) * ch
    sheet.paste(im, (x + 4, y + 22))
    d.text((x + 4, y + 2), f"{f.stem}  {size}", fill="yellow", font=font)
sheet.save(out, quality=85)
print(out)
