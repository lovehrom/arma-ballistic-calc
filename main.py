"""
Главный модуль Arma Ballistic Calculator
Связывает OCR, баллистический калькулятор и overlay
"""

import sys
import time
import threading
from pathlib import Path

# Добавляем src в путь
sys.path.insert(0, str(Path(__file__).parent))

from src.ballistic_calc import calculate_trajectory, parse_wind_direction, parse_azimuth
from src.ocr_reader import read_all_data, capture_screen
from src.overlay import Overlay


# Настройки
HOLD_DURATION = 3.0       # Секунды удержания R до подготовки
READ_DELAY = 2.0         # Секунды после отпускания R до чтения
OVERLAY_DURATION = 3.0   # Секунды показа overlay
OVERLAY_W = 280
OVERLAY_H = 140
OVERLAY_X = 20
OVERLAY_Y = 20

# Калибр по умолчанию
DEFAULT_AMMO = "7.62x51_nato_m993"


class BallisticAssistant:
    def __init__(self, ammo_key=DEFAULT_AMMO):
        self.ammo_key = ammo_key
        self.r_pressed = False
        self.r_press_time = 0
        self.state = "idle"  # idle, waiting, reading, showing
        self.state_time = 0
        self.result = None

    def update(self, overlay):
        """Обновление состояния машины состояний"""
        now = time.time()

        if self.state == "idle":
            # Ждём нажатие R
            pass

        elif self.state == "waiting":
            # R зажат, ждём 3 секунды
            if not self.r_pressed:
                # R отпущен раньше времени — сброс
                self.state = "idle"
                return
            elapsed = now - self.r_press_time
            if elapsed >= HOLD_DURATION:
                self.state = "reading"
                self.state_time = now

        elif self.state == "reading":
            # R отпущен, ждём READ_DELAY секунд
            elapsed = now - self.state_time
            if elapsed >= READ_DELAY:
                self._capture_and_calculate()
                self.state = "showing"
                self.state_time = now

        elif self.state == "showing":
            # Показываем overlay
            elapsed = now - self.state_time
            if elapsed >= OVERLAY_DURATION:
                overlay.hide()
                self.state = "idle"
                self.result = None

    def on_key_press(self, key):
        """Обработка нажатия клавиши"""
        if key == "r" and self.state == "idle":
            self.r_pressed = True
            self.r_press_time = time.time()
            self.state = "waiting"

    def on_key_release(self, key):
        """Обработка отпускания клавиши"""
        if key == "r":
            if self.state == "waiting":
                # R отпущен — переходим к чтению через READ_DELAY
                self.state = "reading"
                self.state_time = time.time()
            self.r_pressed = False

    def _capture_and_calculate(self):
        """Захват экрана, OCR, расчёт"""
        # Захват экрана
        screen = capture_screen()

        # OCR — считываем все данные
        data = read_all_data(screen)

        distance = data.get("distance")
        wind = data.get("wind")
        azimuth = data.get("azimuth")

        if not distance:
            # Не смогли определить дальность
            self.result = {
                "distance": None,
                "elevation_mrad": 0,
                "windage_mrad": 0,
                "error": "Не удалось определить дальность"
            }
            return

        # Парсим данные
        wind_speed = wind["speed"] if wind else 0
        wind_dir_deg = parse_wind_direction(wind["direction"]) if wind else 0
        azimuth_deg = azimuth if azimuth else 0

        # Расчёт
        result = calculate_trajectory(
            distance=distance,
            ammo_key=self.ammo_key,
            wind_speed=wind_speed,
            wind_dir=wind_dir_deg,
            fire_azimuth=azimuth_deg
        )

        result["wind_speed"] = wind_speed
        result["wind_dir"] = wind.get("direction", "?") if wind else "?"
        result["azimuth"] = azimuth_deg

        self.result = result

    def set_ammo(self, ammo_key):
        """Смена калибра"""
        self.ammo_key = ammo_key


def main():
    """Точка входа"""
    print("=" * 50)
    print("Arma Ballistic Calculator")
    print(f"Калибр: {DEFAULT_AMMO}")
    print("=" * 50)
    print("Управление:")
    print("  Zажать R (3с) → отпустить → расчёт через 2с → overlay")
    print("  1-5 — выбор калибра")
    print("  Q — выход")
    print()

    # Создаём overlay
    overlay = Overlay()
    assistant = BallisticAssistant()

    # Клавишный хук через pynput
    try:
        from pynput import keyboard

        def on_press(key):
            try:
                if key.char == "r":
                    assistant.on_key_press("r")
                elif key.char == "q":
                    # Выход
                    pygame.quit()
                    sys.exit(0)
                elif key.char == "1":
                    assistant.set_ammo("7.62x51_nato_m80")
                    print(f"Калибр: 7.62x51 NATO M80 Ball")
                elif key.char == "2":
                    assistant.set_ammo("7.62x51_nato_m993")
                    print(f"Калибр: 7.62x51 NATO M993 AP")
                elif key.char == "3":
                    assistant.set_ammo("5.56x45_nato_m855")
                    print(f"Калибр: 5.56x45 NATO M855")
                elif key.char == "4":
                    assistant.set_ammo(".338_lapua")
                    print(f"Калибр: .338 Lapua Magnum")
                elif key.char == "5":
                    assistant.set_ammo(".50_bmg_m33")
                    print(f"Калибр: .50 BMG M33 Ball")
            except AttributeError:
                pass

        def on_release(key):
            try:
                if key.char == "r":
                    assistant.on_key_release("r")
            except AttributeError:
                pass

        listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.start()

    except ImportError:
        print("ERROR: pynput не установлен. Установите: pip install pynput")
        print("Используем fallback через pygame events...")
        listener = None

    # Главный цикл
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        # Обновление логики
        assistant.update(overlay)

        # Показать overlay если есть результат
        if assistant.state == "showing" and assistant.result:
            overlay.show(assistant.result)
            overlay.render()
            pygame.display.flip()
        elif assistant.state == "idle":
            overlay.render()
            pygame.display.flip()

        overlay.clock.tick(30)

    pygame.quit()
    if listener:
        listener.stop()


if __name__ == "__main__":
    main()
