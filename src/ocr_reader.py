"""
OCR модуль для Arma Reforger
Распознаёт дальность, ветер и азимут с экрана игры
"""

import cv2
import numpy as np
import re
import os


def capture_screen(region=None):
    """
    Захват скриншота экрана (или региона)
    region: (x, y, w, h) — если None, весь экран
    Возвращает numpy array (BGR)
    """
    try:
        import mss
        with mss.mss() as sct:
            if region:
                monitor = {"top": region[1], "left": region[0],
                            "width": region[2], "height": region[3]}
            else:
                monitor = sct.monitors[1]  # главный монитор

            img = np.array(sct.grab(monitor))
            # mss возвращает BGRA, конвертируем в BGR
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    except ImportError:
        # Fallback через pyautogui
        import pyautogui
        screenshot = pyautogui.screenshot()
        img = np.array(screenshot)
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)


def find_distance_value(screen_bgr):
    """
    Ищет 3+ значное число в центральной области экрана (красные цифры дальномера)
    Возвращает int или None
    """
    h, w = screen_bgr.shape[:2]

    # Центр экрана, правая половина — где обычно цифры дальномера
    cx, cy = w // 2, h // 2
    roi_w, roi_h = w // 4, h // 6
    roi = screen_bgr[cy - roi_h:cy + roi_h, cx:cx + roi_w * 2]

    # Бинаризация по красному каналу (цифры дальномера красные)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    lower_red = np.array([0, 100, 100])
    upper_red = np.array([10, 255, 255])
    mask1 = cv2.inRange(hsv, lower_red, upper_red)

    lower_red2 = np.array([160, 100, 100])
    upper_red2 = np.array([180, 255, 255])
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)

    mask = cv2.bitwise_or(mask1, mask2)

    # OCR через Tesseract
    try:
        import pytesseract
        text = pytesseract.image_to_string(
            mask, config='--psm 6 --oem 3 -c tessedit_char_whitelist=0123456789'
        )
        numbers = re.findall(r'\d{3,}', text)
        if numbers:
            return int(numbers[0])
    except ImportError:
        pass

    # Fallback: контурный анализ
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    digits = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        if 10 < cw < 80 and 20 < ch < 80:
            digits.append((x, roi[y:y+ch, x:x+cw]))

    if len(digits) >= 2:
        # Сортируем по X и пытаемся собрать число
        digits.sort(key=lambda d: d[0])
        digit_str = ""
        for _, digit_img in digits:
            digit_text = pytesseract.image_to_string(
                digit_img, config='--psm 10 -c tessedit_char_whitelist=0123456789'
            ).strip()
            digit_str += digit_text

        match = re.search(r'\d{3,}', digit_str)
        if match:
            return int(match.group())

    return None


def find_wind_info(screen_bgr):
    """
    Ищет информацию о ветре в нижней левой области экрана
    Формат: "X.X m/s NW" (или NE, S, SW, SE, E, W, N)
    Возвращает dict: {"speed": float, "direction": str} или None
    """
    h, w = screen_bgr.shape[:2]

    # Нижняя левая область (1/4 ширины, 1/4 высоты)
    roi = screen_bgr[int(h * 0.7):int(h * 0.95), 0:int(w * 0.35)]

    # Конвертируем в grayscale и бинаризуем
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

    # OCR
    try:
        import pytesseract
        text = pytesseract.image_to_string(
            binary, config='--psm 6 --oem 3'
        )

        # Ищем паттерн ветра: "X.X m/s DIRECTION"
        wind_pattern = r'([\d.]+)\s*m/s\s*(N|NE|NW|S|SE|SW|E|W)'
        match = re.search(wind_pattern, text, re.IGNORECASE)
        if match:
            return {
                "speed": float(match.group(1)),
                "direction": match.group(2).upper()
            }

        # Также ищем с русским "м/с"
        wind_pattern_ru = r'([\d.]+)\s*[мm][/\u0441s]\s*(N|NE|NW|S|SE|SW|E|W)'
        match = re.search(wind_pattern_ru, text, re.IGNORECASE)
        if match:
            return {
                "speed": float(match.group(1)),
                "direction": match.group(2).upper()
            }

    except ImportError:
        pass

    return None


def find_azimuth(screen_bgr):
    """
    Ищет азимут на компасе внизу экрана по центру
    Формат: 3 цифры (000-360) или буквы (N, NE, NW и т.д.)
    Возвращает int (градусы) или None
    """
    h, w = screen_bgr.shape[:2]

    # Нижняя центральная полоса (компас)
    compass_y_start = int(h * 0.88)
    compass_y_end = int(h * 0.98)
    compass_x_start = int(w * 0.3)
    compass_x_end = int(w * 0.7)

    roi = screen_bgr[compass_y_start:compass_y_end, compass_x_start:compass_x_end]

    # Белый текст на тёмном фоне
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)

    try:
        import pytesseract
        text = pytesseract.image_to_string(
            binary, config='--psm 6 --oem 3'
        )

        # Сначала ищем 3-значное число
        nums = re.findall(r'\b(\d{1,3})\b', text)
        for n in nums:
            val = int(n)
            if 0 <= val <= 360:
                return val

        # Ищем буквенные направления
        dirs = re.findall(r'\b(N|NE|NW|S|SE|SW|E|W)\b', text, re.IGNORECASE)
        if dirs:
            direction_map = {
                "N": 0, "NE": 45, "E": 90, "SE": 135,
                "S": 180, "SW": 225, "W": 270, "NW": 315
            }
            return direction_map.get(dirs[0].upper(), None)

    except ImportError:
        pass

    return None


def read_all_data(screen_bgr=None):
    """
    Считывает все данные с экрана за один проход
    Возвращает dict с distance, wind, azimuth
    """
    if screen_bgr is None:
        screen_bgr = capture_screen()

    return {
        "distance": find_distance_value(screen_bgr),
        "wind": find_wind_info(screen_bgr),
        "azimuth": find_azimuth(screen_bgr),
    }


if __name__ == "__main__":
    # Тест на скриншоте
    import sys
    img_path = sys.argv[1] if len(sys.argv) > 1 else None
    if img_path:
        img = cv2.imread(img_path)
        data = read_all_data(img)
        print(data)
    else:
        print("Укажите путь к скриншоту: python ocr_reader.py screenshot.png")
