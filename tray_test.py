import pystray
from PIL import Image, ImageDraw

img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)
draw.ellipse((2, 2, 62, 62), fill=(38, 162, 105, 255))
draw.text((26, 22), "R", fill=(255, 255, 255, 255))

def on_quit(icon, item):
    icon.stop()

menu = pystray.Menu(pystray.MenuItem("Quit", on_quit))
icon = pystray.Icon("test", img, "Tray Test", menu)
print("Starting tray icon... check your system tray now (including the ^ hidden icons area).")
icon.run()
print("Tray icon stopped.")
