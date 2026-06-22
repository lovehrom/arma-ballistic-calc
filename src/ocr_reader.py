"""
OCR модуль для Arma Reforger v2
Использует EasyOCR вместо Tesseract (работает из коробки)
Калиброванные зоны + post-processing OCR ошибок
"""

import cv2
import numpy as np
import re
import sys
from pathlib import Path


def _init_reader():
    """Ленивая инициализация EasyOCR"""
    if not hasattr(_init_reader, '_reader'):
        import easyocr
        _init_reader._reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    return _init_reader._reader


def capture_screen(region=None):
    """Захват скриншота"""
    try:
        import mss
        with mss.mss() as sct:
            if region:
                monitor = {"top": region[1], "left": region[0],
                            "width": region[2], "height": region[3]}
            else:
                monitor = sct.monitors[1]
            img = np.array(sct.grab(monitor))
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    except ImportError:
        import pyautogui
        screenshot = pyautogui.screenshot()
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)


def find_distance(screen_bgr):
    """
    Ищет 3+ значное число дальномера (красные цифры)
    Зона: центр экрана, правая половина
    """
    h, w = screen_bgr.shape[:2]
    reader = _init_reader()

    # Зона поиска: центр правая половина
    roi = screen_bgr[h//4:3*h//4, w//2:w]

    # HSV маска для красного цвета
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    m1 = cv2.inRange(hsv, np.array([0, 100, 100]), np.array([10, 255, 255]))
    m2 = cv2.inRange(hsv, np.array([160, 100, 100]), np.array([180, 255, 255]))
    red_mask = cv2.bitwise_or(m1, m2)

    results = reader.readtext(red_mask, detail=0)
    nums = re.findall(r'\d{3,}', ' '.join(results))

    return int(nums[0]) if nums else None


def find_wind(screen_bgr):
    """
    Ищет информацию о ветре в зоне над компасом
    Формат: "5.0 m/s NW"
    """
    h, w = screen_bgr.shape[:2]
    reader = _init_reader()

    # Зона ветра: над компасом, центральная область
    roi = screen_bgr[int(h*0.89):int(h*0.97), int(w*0.37):int(w*0.59)]

    results = reader.readtext(roi, detail=0)
    text = ' '.join(results)

    # Post-processing OCR ошибок
    text = (text
        .replace('Mind', 'Wind')
        .replace('Wmd', 'Wind')
        .replace('M/s', 'm/s')
        .replace('M/S', 'm/s'))

    # Парсинг направления ветра
    match = re.search(r'([\d.]+)\s*m/s\s*(N(?:E|W)?|S(?:E|W)?|E|W)', text, re.IGNORECASE)
    if not match:
        match = re.search(r'([\d.]+)\s*m/s\s*\b([NSEW]+)', text, re.IGNORECASE)

    if match:
        return {
            "speed": float(match.group(1)),
            "direction": match.group(2).upper()
        }
    return None


def find_azimuth(screen_bgr):
    """
    Ищет азимут на компасе
    Увеличивает зону 3x и берёт число ближе всего к центру
    """
    h, w = screen_bgr.shape[:2]
    reader = _init_reader()

    # Зона компаса: нижняя центральная полоса
    comp_roi = screen_bgr[int(h*0.90):int(h*0.99), int(w*0.35):int(w*0.65)]
    comp_big = cv2.resize(comp_roi, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

    # Центр = направление взгляда игрока
    comp_cx = comp_big.shape[1] // 2

    results = reader.readtext(comp_big, detail=1)  # [(bbox, text, conf)]

    best_num = None
    best_dist = float('inf')

    for item in results:
        bbox, text, conf = item
        for m in re.finditer(r'\b(\d{2,3})\b', text):
            val = int(m.group(1))
            if 0 <= val <= 360:
                x_center = (bbox[0][0] + bbox[2][0]) / 2
                dist_to_center = abs(x_center - comp_cx)
                if dist_to_center < best_dist:
                    best_dist = dist_to_center
                    best_num = val

    return best_num


def read_all(screen_bgr=None):
    """Считывает все данные с экрана за один проход"""
    if screen_bgr is None:
        screen_bgr = capture_screen()
    return {
        "distance": find_distance(screen_bgr),
        "wind": find_wind(screen_bgr),
        "azimuth": find_azimuth(screen_bgr),
    }


if __name__ == "__main__":
    img_path = sys.argv[1] if len(sys.argv) > 1 else None
    if img_path:
        img = cv2.imread(img_path)
        data = read_all(img)
        for k, v in data.items():
            print(f"  {k}: {v}")
    else:
        print("Usage: python ocr_reader.py screenshot.jpg")
