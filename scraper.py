import os
import re
import json
import requests
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import pdfplumber
import pytesseract
from datetime import datetime
import cv2
import numpy as np
from PIL import Image

PAGE_URL = "https://kseb.in"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Set SCRAPER_DEBUG=1 (or "true" / "yes") to enable debug image dumps from OCR
DEBUG_MODE = os.environ.get("SCRAPER_DEBUG", "").lower() in ("1", "true", "yes")


BOUNDING_BOXES_PIXELS = {
    "consumption": (1306, 1297, 1639, 1495),
    "production": (1324, 1596, 1639, 1802),
    "import": (1291, 1903, 1635, 2117),
    "peak": (1427, 2214, 1740, 2372),
    "peak_time": (1447, 2389, 1767, 2543),
    "dam_now": (1219, 2863, 1517, 2994),
    "dam_before": (1227, 3012, 1534, 3170),
}


# UNCOMMENT & UPDATE THIS LINE IF RUNNING LOCALLY ON WINDOWS:
# pytesseract.pytesseract.tesseract_cmd = r''


def parse_clean_value(raw_text, label=""):
    if not raw_text:
        return None
    
    cleaned = raw_text.strip()

    # Handle time metrics (e.g., "7:20", "19:45", "07:20 AM")
    if "time" in label.lower():
        time_match = re.search(r"\b([0-1]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?\b", cleaned)
        if time_match:
            return time_match.group(0) # Returns string "7:20"

        # Case B: Missing colon like "738a" or "0738" -> convert to "07:38"
        digits_only = re.sub(r"[^\d]", "", cleaned)
        if len(digits_only) == 3:  # e.g., "738" -> "07:38"
            return f"0{digits_only[0]}:{digits_only[1:]}"
        elif len(digits_only) == 4:  # e.g., "1800" -> "18:00"
            return f"{digits_only[:2]}:{digits_only[2:]}"
        elif len(digits_only) == 2:  # e.g., "18" -> "18:00"
            return f"{digits_only}:00"

        return cleaned if cleaned else None

    # Handle standard numbers
    num_str = re.sub(r"[^\d.-]", "", cleaned)
    if num_str:
        try:
            val = float(num_str) if "." in num_str else int(num_str)

            # GUARDRAIL: Fix missed decimal points for DAM metrics (e.g., 29530 -> 29.53)
            if "dam" in label.lower() and val > 500:
                val = round(val / 1000.0, 3) if val > 10000 else round(val / 100.0, 3)

            return val
        except ValueError:
            return None

    return None


def preprocess_crop_for_ocr(pil_crop_img):
    """Upscales crop 2x and binarizes it so Tesseract detects faint decimals and colons."""
    # Convert PIL to grayscale OpenCV image
    cv_img = cv2.cvtColor(np.array(pil_crop_img), cv2.COLOR_RGB2GRAY)

    # Upscale 2x using cubic interpolation
    resized = cv2.resize(cv_img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    # Apply Otsu binarization (high-contrast black/white)
    _, thresh = cv2.threshold(resized, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    return Image.fromarray(thresh)


def extract_ocr_from_pdf(pdf_path):
    """Aligns entire PDF page to template.png and crops target bounding boxes for OCR."""
    extracted_metrics = {}

    with pdfplumber.open(pdf_path) as pdf:
        first_page = pdf.pages[0]

        # 1. Render the entire PDF page as a high-res 300 DPI PIL image
        raw_page_img = first_page.to_image(resolution=300).original

        # 2. ALIGNMENT STEP: Auto-warp and fix paper rotation/shift
        aligned_page_img = align_image_to_template(raw_page_img, template_path="template.png")

        if DEBUG_MODE:
            aligned_page_img.save("debug_aligned_full_page.png")

        # 3. Crop target regions directly from the aligned 300 DPI image
        for label, px_box in BOUNDING_BOXES_PIXELS.items():

            # Crop raw image box
            raw_crop = aligned_page_img.crop(px_box)

            # Preprocess crop (Upscale + Binarize)
            processed_crop = preprocess_crop_for_ocr(raw_crop)

            if DEBUG_MODE:
                processed_crop.save(f"debug_{label}.png")

            # Configure Tesseract OCR (include ':' if metric is a time field)
            if "time" in label.lower():
                ocr_config = r'--psm 6 -c tessedit_char_whitelist=0123456789:APMapm'
            else:
                ocr_config = r'--psm 6 -c tessedit_char_whitelist=0123456789.,-$'

            raw_ocr_text = pytesseract.image_to_string(processed_crop, config=ocr_config)

            #if DEBUG_MODE:
                # print(f"DEBUG [{label}] Raw OCR Output: '{raw_ocr_text.strip()}'")

            # Clean and parse value (passing label so parser knows field type)
            extracted_metrics[label] = parse_clean_value(raw_ocr_text, label)

        c = extracted_metrics.get("consumption")
        p = extracted_metrics.get("production")
        i = extracted_metrics.get("import")

        # If Consumption, Production, and Import are all present:
        if c is not None and p is not None:
            expected_import = round(c - p, 3)

            # If OCR import is missing OR differs from math by > 1.0, trust the math!
            if i is None or abs(i - expected_import) > 1.0:
                #if DEBUG_MODE:
                    # print(f" Auto-correcting OCR import ({i}) -> Mathematical Value ({expected_import})")
                extracted_metrics["import"] = expected_import

        return extracted_metrics


def align_image_to_template(target_pil_img, template_path="template.png"):
    if not os.path.exists(template_path):
        print("ALIGNMENT SKIPPED: 'template.png' not found in project directory.")
        return target_pil_img

    target_cv = cv2.cvtColor(np.array(target_pil_img), cv2.COLOR_RGB2GRAY)
    template_cv = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)

    if template_cv is None:
        print("ALIGNMENT SKIPPED: Could not load 'template.png'.")
        return target_pil_img

    # Detect ORB visual features
    orb = cv2.ORB_create(5000)
    kp1, des1 = orb.detectAndCompute(target_cv, None)
    kp2, des2 = orb.detectAndCompute(template_cv, None)

    if des1 is None or des2 is None:
        print(" ALIGNMENT FAILED: No visual features detected on page.")
        return target_pil_img

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    matches = sorted(matcher.match(des1, des2), key=lambda x: x.distance)

    good_matches = matches[:int(len(matches) * 0.15)]

    # DIAGNOSTIC LOG
    print(f"OpenCV Feature Matching: Found {len(good_matches)} good feature point(s).")

    if len(good_matches) < 4:
        print(" ALIGNMENT FAILED: Not enough matching points (< 4). Returning raw unaligned image.")
        return target_pil_img

    pts1 = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    pts2 = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    matrix, _ = cv2.findHomography(pts1, pts2, cv2.RANSAC, 5.0)
    if matrix is None:
        print(" ALIGNMENT FAILED: Homography matrix calculation failed.")
        return target_pil_img

    h, w = template_cv.shape
    target_color_cv = cv2.cvtColor(np.array(target_pil_img), cv2.COLOR_RGB2BGR)
    aligned_cv = cv2.warpPerspective(target_color_cv, matrix, (w, h))

    aligned_rgb = cv2.cvtColor(aligned_cv, cv2.COLOR_BGR2RGB)
    print(" ALIGNMENT SUCCESSFUL: Page aligned and transformed!")
    return Image.fromarray(aligned_rgb)


def main():
    # Step 1: Load existing data.json to identify already scraped dates
    history_file = "data.json"
    history = []

    if os.path.exists(history_file):
        with open(history_file, "r") as f:
            try:
                history = json.load(f)
            except json.JSONDecodeError:
                history = []

    # Store set of already scraped dates (e.g. {'2026-07-28', '2026-07-29'})
    scraped_dates = {entry.get("date") for entry in history if entry.get("date")}

    # Step 2: Fetch the main page
    print(f" Fetching website report page: {PAGE_URL}")
    response = requests.get(PAGE_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    # Locate all <a> tags that link to PDF uploads
    pdf_tags = soup.find_all("a", href=lambda h: h and "/uploads/Downloadtemsuppy/" in h)

    if not pdf_tags:
        print(" No PDF links found on the webpage.")
        return

    print(f"Found {len(pdf_tags)} total PDF links on the page.")

    # Step 3: Iterate through PDF links and process any missing dates
    new_entries_count = 0
    MIN_YEAR = 2026

    for tag in pdf_tags:
        # Resolve relative hrefs (e.g. "/uploads/...") to fully-qualified URLs
        pdf_url = urljoin(PAGE_URL, tag["href"])
        link_text = tag.text.strip()

        # Combine visible text and link URL to ensure we capture filenames like '28.07.2026.pdf'
        combined_identifier = f"{link_text} {pdf_url}"

        # Extract DD.MM.YYYY date pattern using Regex
        date_match = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", combined_identifier)
        if not date_match:
            print(f" Could not extract date pattern from link: {combined_identifier}")
            continue

        day, month, year = date_match.groups()
        formatted_date = f"{year}-{month}-{day}"  # Standard ISO format: 'YYYY-MM-DD'

        if int(year) < MIN_YEAR:
            print(f" Skipping {formatted_date} — older than target cutoff year ({MIN_YEAR})")
            continue

        # Check if this date has already been processed
        if formatted_date in scraped_dates:
            print(f" Skipping {formatted_date} — already present in data.json")
            continue

        # Process missing report
        print(f" Processing report for missing date: {formatted_date} ({pdf_url})")
        temp_pdf = f"temp_{formatted_date}.pdf"

        try:
            # Download PDF file
            print(f"   Downloading: {pdf_url}")
            pdf_response = requests.get(pdf_url, headers=HEADERS, stream=True, timeout=60)
            pdf_response.raise_for_status()
            with open(temp_pdf, "wb") as f:
                for chunk in pdf_response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # Run multi-box OCR extraction
            metrics = extract_ocr_from_pdf(temp_pdf)
            print(f" Metrics extracted: {metrics}")

            # Append entry to history
            history.append({
                "date": formatted_date,
                "timestamp": datetime.now().isoformat(),
                "metrics": metrics
            })

            # Mark date as scraped
            scraped_dates.add(formatted_date)
            new_entries_count += 1

        except Exception as e:
            print(f" Failed to process {formatted_date}: {e}")

        finally:
            # Clean up temporary downloaded file
            if os.path.exists(temp_pdf):
                os.remove(temp_pdf)

    # Step 4: Save updated history back to data.json sorted chronologically
    if new_entries_count > 0:
        history.sort(key=lambda x: x["date"])  # Sort chronologically by date
        with open(history_file, "w") as f:
            json.dump(history, f, indent=2)
        print(f"\n Successfully added {new_entries_count} missing report(s) to data.json!")
        return new_entries_count  # Signal to caller that new data was written
    else:
        print("\n All reports are up to date. No new data needed.")
        return 0


if __name__ == "__main__":
    main()