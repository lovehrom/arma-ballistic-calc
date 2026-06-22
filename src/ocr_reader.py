"""
OCR модуль для Arma Reforger v3 — калиброванные зоны
EasyOCR с точными ROI + post-processing
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
    """Захват скриншота экрана"""
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
    Зона: центр-правая часть экрана (45%-85% ширины, 25%-75% высоты)
    Метод: HSV красная маска + EasyOCR
    """
    h, w = screen_bgr.shape[:2]
    reader = _init_reader()

    # Основная зона поиска — правая половина центра
    roi = screen_bgr[int(h * 0.25):int(h * 0.75), int(w * 0.45):int(w * 0.85)]

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    m1 = cv2.inRange(hsv, np.array([0, 100, 100]), np.array([10, 255, 255]))
    m2 = cv2.inRange(hsv, np.array([160, 100, 100]), np.array([180, 255, 255]))
    red_mask = cv2.bitwise_or(m1, m2)

    results = reader.readtext(red_mask, detail=0)
    nums = re.findall(r'\d{3,}', ' '.join(results))

    # Fallback: вся правая половина если не нашли
    if not nums:
        roi2 = screen_bgr[int(h * 0.25):int(h * 0.75), int(w * 0.50):w]
        hsv2 = cv2.cvtColor(roi2, cv2.COLOR_BGR2HSV)
        m3 = cv2.inRange(hsv2, np.array([0, 100, 100]), np.array([10, 255, 255]))
        m4 = cv2.inRange(hsv2, np.array([160, 100, 100]), np.array([180, 255, 255]))
        mask2 = cv2.bitwise_or(m3, m4)
        results2 = reader.readtext(mask2, detail=0)
        nums = re.findall(r'\d{3,}', ' '.join(results2))

    return int(nums[0]) if nums else None


def find_wind(screen_bgr):
    """
    Ищет ветер: "5.0 m/s NW"
    Зона: нижняя часть экрана над компасом
    Калибровка: y 93%-97%, x 43%-57%
    """
    h, w = screen_bgr.shape[:2]
    reader = _init_reader()

    # Зона ветра (калиброванная)
    roi = screen_bgr[int(h * 0.93):int(h * 0.97), int(w * 0.43):int(w * 0.57)]

    results = reader.readtext(roi, detail=0)
    text = ' '.join(results)

    # Post-processing типичных OCR ошибок
    text = (text
        .replace('Mind', 'Wind')
        .replace('Wmd', 'Wind')
        .replace('M/s', 'm/s')
        .replace('M/S', 'm/s')
        .replace('MV/s', 'm/s'))

    # Парсинг: speed + direction (N, NE, NW, S, SE, SW, E, W)
    match = re.search(
        r'([\d.]+)\s*m/s\s*(N(?:E|W)?|S(?:E|W)?|E|W)',
        text, re.IGNORECASE
    )

    # Fallback: если зона слишком узкая и не нашло — расширяем
    if not match:
        roi2 = screen_bgr[int(h * 0.91):int(h * 0.98), int(w * 0.30):int(w * 0.65)]
        results2 = reader.readtext(roi2, detail=0)
        text2 = ' '.join(results2)
        text2 = (text2
            .replace('Mind', 'Wind')
            .replace('M/s', 'm/s')
            .replace('MV/s', 'm/s'))
        match = re.search(
            r'([\d.]+)\s*m/s\s*(N(?:E|W)?|S(?:E|W)?|E|W)',
            text2, re.IGNORECASE
        )

    if match:
        return {
            "speed": float(match.group(1)),
            "direction": match.group(2).upper()
        }
    return None


def find_azimuth(screen_bgr):
    """
    Ищет азимут на компасе — число ближе всего к центру
    Зона: нижняя полоса компаса (95%-99% высоты, 45%-55% ширины)
    Увеличиваем x5 для точности
    """
    h, w = screen_bgr.shape[:2]
    reader = _init_reader()

    # Зона компаса — центральная полоса, x3 масштаб
    roi = screen_bgr[int(h * 0.95):int(h * 0.99), int(w * 0.40):int(w * 0.60)]
    roi_big = cv2.resize(roi, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

    comp_cx = roi_big.shape[1] // 2
    results = reader.readtext(roi_big, detail=1)

    best_num = None
    best_dist = float('inf')

    for item in results:
        bbox, text, conf = item
        for m in re.finditer(r'\b(\d{2,3})\b', text):
            val = int(m.group(1))
            if 0 <= val <= 360:
                x_center = (bbox[0][0] + bbox[2][0]) / 2
                dist = abs(x_center - comp_cx)
                if dist < best_dist:
                    best_dist = dist
                    best_num = val

    # Fallback: расширенная зона x3
    if best_num is None:
        roi2 = screen_bgr[int(h * 0.90):int(h * 0.99), int(w * 0.35):int(w * 0.65)]
        roi2_big = cv2.resize(roi2, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        comp_cx2 = roi2_big.shape[1] // 2
        results2 = reader.readtext(roi2_big, detail=1)
        for item in results2:
            bbox, text, conf = item
            for m in re.finditer(r'\b(\d{2,3})\b', text):
                val = int(m.group(1))
                if 0 <= val <= 360:
                    x_center = (bbox[0][0] + bbox[2][0]) / 2
                    dist = abs(x_center - comp_cx2)
                    if dist < best_dist:
                        best_dist = dist
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
