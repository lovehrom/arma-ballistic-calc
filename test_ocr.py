import cv2
import numpy as np
import re
import sys

def find_distance_value(img_bgr):
    """Ищет 3+ значное число дальномера (красные цифры)"""
    h, w = img_bgr.shape[:2]
    
    # Центр экрана, правая часть
    cx, cy = w // 2, h // 2
    roi_h = h // 4
    roi_w = w // 3
    roi = img_bgr[cy - roi_h:cy + roi_h, cx:cx + roi_w]
    
    print(f"[DIST] ROI size: {roi.shape}")
    
    # Бинаризация по красному
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower_red1 = np.array([0, 100, 100])
    upper_red1 = np.array([10, 255, 255])
    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    
    lower_red2 = np.array([160, 100, 100])
    upper_red2 = np.array([180, 255, 255])
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    
    mask = cv2.bitwise_or(mask1, mask2)
    
    # Сохраняем маску для анализа
    cv2.imwrite("K:/Работа/projects/arma-ballistic-calc/assets/debug_distance_mask.png", mask)
    cv2.imwrite("K:/Работа/projects/arma-ballistic-calc/assets/debug_distance_roi.png", roi)
    
    white_pixels = cv2.countNonZero(mask)
    print(f"[DIST] Red pixels found: {white_pixels}")
    
    import pytesseract
    text = pytesseract.image_to_string(
        mask, config='--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789'
    )
    print(f"[DIST] OCR raw text: '{text.strip()}'")
    
    numbers = re.findall(r'\d{3,}', text)
    print(f"[DIST] Found numbers: {numbers}")
    
    if numbers:
        return int(numbers[0])
    
    # Попробуем другие PSM modes
    for psm in [7, 8, 11, 13]:
        text2 = pytesseract.image_to_string(
            mask, config=f'--psm {psm} --oem 3 -c tessedit_char_whitelist=0123456789'
        )
        nums = re.findall(r'\d{3,}', text2)
        if nums:
            print(f"[DIST] Found via psm={psm}: {nums}")
            return int(nums[0])
    
    return None


def find_wind_info(img_bgr):
    """Ищет ветер в нижнем левом углу"""
    h, w = img_bgr.shape[:2]
    
    roi = img_bgr[int(h * 0.7):int(h * 0.95), 0:int(w * 0.35)]
    print(f"\n[WIND] ROI size: {roi.shape}")
    
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    
    cv2.imwrite("K:/Работа/projects/arma-ballistic-calc/assets/debug_wind_roi.png", roi)
    cv2.imwrite("K:/Работа/projects/arma-ballistic-calc/assets/debug_wind_mask.png", binary)
    
    import pytesseract
    text = pytesseract.image_to_string(binary, config='--psm 6 --oem 3')
    print(f"[WIND] OCR raw text: '{text.strip()}'")
    
    # Пробуем разные паттерны
    patterns = [
        r'([\d.]+)\s*m/s\s*(N|NE|NW|S|SE|SW|E|W)',
        r'([\d.]+)\s*/s\s*(N|NE|NW|S|SE|SW|E|W)',
        r'([\d.]+)\s*m/s',
        r'(\d\.\d)\s',
    ]
    
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            print(f"[WIND] Match pattern '{pat}': {match.groups()}")
            direction = match.group(2) if len(match.groups()) > 1 else "?"
            return {"speed": float(match.group(1)), "direction": direction}
    
    # Fallback: пробуем весь текст
    all_nums = re.findall(r'[\d.]+', text)
    all_dirs = re.findall(r'\b(N|NE|NW|S|SE|SW|E|W)\b', text, re.IGNORECASE)
    print(f"[WIND] All numbers: {all_nums}, All directions: {all_dirs}")
    
    if all_nums and all_dirs:
        return {"speed": float(all_nums[0]), "direction": all_dirs[0].upper()}
    
    return None


def find_azimuth(img_bgr):
    """Ищет азимут на компасе внизу по центру"""
    h, w = img_bgr.shape[:2]
    
    roi = img_bgr[int(h * 0.88):int(h * 0.98), int(w * 0.3):int(w * 0.7)]
    print(f"\n[COMP] ROI size: {roi.shape}")
    
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
    
    cv2.imwrite("K:/Работа/projects/arma-ballistic-calc/assets/debug_compass_roi.png", roi)
    cv2.imwrite("K:/Работа/projects/arma-ballistic-calc/assets/debug_compass_mask.png", binary)
    
    import pytesseract
    text = pytesseract.image_to_string(binary, config='--psm 6 --oem 3')
    print(f"[COMP] OCR raw text: '{text.strip()}'")
    
    nums = re.findall(r'\b(\d{1,3})\b', text)
    dirs = re.findall(r'\b(N|NE|NW|S|SE|SW|E|W)\b', text, re.IGNORECASE)
    
    print(f"[COMP] Numbers: {nums}, Directions: {dirs}")
    
    for n in nums:
        val = int(n)
        if 0 <= val <= 360:
            print(f"[COMP] Valid azimuth: {val}")
            return val
    
    return None


if __name__ == "__main__":
    img_path = sys.argv[1]
    print(f"Loading: {img_path}")
    img = cv2.imread(img_path)
    print(f"Image size: {img.shape}")
    
    dist = find_distance_value(img)
    wind = find_wind_info(img)
    azimuth = find_azimuth(img)
    
    print("\n" + "=" * 40)
    print("RESULTS:")
    print(f"  Distance: {dist}")
    print(f"  Wind: {wind}")
    print(f"  Azimuth: {azimuth}")
