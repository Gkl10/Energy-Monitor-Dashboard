import cv2
import os

TEMPLATE_PATH = "template.png"

METRICS = [
    "consumption",
    "production",
    "import",
    "peak",
    "peak_time",
    "dam_now",
    "dam_before"
]

if not os.path.exists(TEMPLATE_PATH):
    print(f" Error: {TEMPLATE_PATH} not found!")
    exit()

img = cv2.imread(TEMPLATE_PATH)
h, w = img.shape[:2]

# Scale image so it fits comfortably on screen during selection
screen_h = 800
scale = screen_h / float(h)
resized_img = cv2.resize(img, (0, 0), fx=scale, fy=scale)

new_boxes = {}

print("=" * 60)
print(" INSTRUCTIONS:")
print("1. A window will pop up for each metric.")
print("2. Drag a box around the target number with your mouse.")
print("3. Press SPACE or ENTER to confirm and move to the next metric.")
print("=" * 60)

for metric in METRICS:
    window_title = f"Select box for: [{metric.upper()}] (Press SPACE/ENTER when done)"
    roi = cv2.selectROI(window_title, resized_img)
    cv2.destroyAllWindows()

    x, y, box_w, box_h = roi
    
    if box_w == 0 or box_h == 0:
        print(f"Skipped {metric}")
        continue

    # Scale back to original 300 DPI pixel coordinates
    px_x0 = int(x / scale)
    px_top = int(y / scale)
    px_x1 = int((x + box_w) / scale)
    px_bottom = int((y + box_h) / scale)

    new_boxes[metric] = (px_x0, px_top, px_x1, px_bottom)

print("\n" + "=" * 60)
print(" COPY & PASTE THIS INTO scraper.py OVER BOUNDING_BOXES_PIXELS:")
print("=" * 60)
print("BOUNDING_BOXES_PIXELS = {")
for k, v in new_boxes.items():
    print(f'    "{k}": {v},')
print("}")
print("=" * 60)