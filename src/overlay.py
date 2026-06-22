"""
Overlay для Arma Reforger — отображение поправок поверх игры
Pygame: always-on-top, прозрачный фон
"""

import pygame
import sys
import math

# Цвета
BG_COLOR = (0, 0, 0, 160)      # Полупрозрачный чёрный
TEXT_COLOR = (255, 255, 255)    # Белый
ELEV_COLOR = (100, 255, 100)  # Зелёный для elevation
WIND_COLOR = (100, 200, 255)  # Голубой для windage
WARN_COLOR = (255, 200, 50)   # Жёлтый предупреждение
ERROR_COLOR = (255, 80, 80)    # Красный ошибка

# Позиция overlay (левый верхний угол)
OVERLAY_X = 20
OVERLAY_Y = 20
OVERLAY_W = 280
OVERLAY_H = 140
OVERLAY_DURATION_MS = 3000  # 3 секунды


class Overlay:
    def __init__(self):
        pygame.init()

        # Размер окна = размер overlay
        self.screen = pygame.display.set_mode(
            (OVERLAY_W, OVERLAY_H),
            pygame.NOFRAME | pygame.SRCALPHA | pygame.DOUBLEBUF
        )
        self.clock = pygame.time.Clock()

        # Шрифты
        self.font_title = pygame.font.SysFont("consolas", 18, bold=True)
        self.font_large = pygame.font.SysFont("consolas", 28, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 14)
        self.font_label = pygame.font.SysFont("consolas", 16, bold=True)

        # Состояние
        self.data = None
        self.show_time = 0
        self.visible = False

        # Установить always-on-top через win32gui
        self._set_always_on_top()

    def _set_always_on_top(self):
        """Установка окна поверх всех окон"""
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = pygame.display.get_window()
            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010

            # Переместить окно в заданную позицию
            ctypes.windll.user32.SetWindowPos(
                hwnd, HWND_TOPMOST,
                OVERLAY_X, OVERLAY_Y, OVERLAY_W, OVERLAY_H,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
            )

            # Сделать окно кликабельным для мыши (не пропускает клики в игру)
            # Раскомментировать если нужно чтобы overlay не перехватывал мышь:
            # extended_style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            # ctypes.windll.user32.SetWindowLongW(
            #     hwnd, -20,
            #     extended_style | 0x00000020  # WS_EX_TRANSPARENT
            # )
        except Exception as e:
            print(f"Warning: Не удалось установить always-on-top: {e}")

    def show(self, data):
        """Показать overlay с данными"""
        self.data = data
        self.visible = True
        self.show_time = pygame.time.get_ticks()

    def hide(self):
        """Скрыть overlay"""
        self.visible = False
        self.screen.fill((0, 0, 0, 0))

    def _draw_rounded_rect(self, surface, color, rect, radius=10):
        """Рисуем прямоугольник со скруглёнными углами"""
        x, y, w, h = rect
        # Прямоугольник
        pygame.draw.rect(surface, color, (x + radius, y, w - 2 * radius, h))
        pygame.draw.rect(surface, color, (x, y + radius, w, h - 2 * radius))
        # Круги по углам
        pygame.draw.circle(surface, color, (x + radius, y + radius), radius)
        pygame.draw.circle(surface, color, (x + w - radius, y + radius), radius)
        pygame.draw.circle(surface, color, (x + radius, y + h - radius), radius)
        pygame.draw.circle(surface, color, (x + w - radius, y + h - radius), radius)

    def render(self):
        """Отрисовка overlay"""
        if not self.visible or not self.data:
            self.screen.fill((0, 0, 0, 0))
            return

        # Прозрачный фон
        self.screen.fill((0, 0, 0, 0))

        # Рамка
        border_color = (255, 255, 255, 60)
        self._draw_rounded_rect(self.screen, BG_COLOR, (0, 0, OVERLAY_W, OVERLAY_H), 8)

        y_offset = 12

        # Заголовок
        title_surf = self.font_title.render("BALLISTIC CALC", True, TEXT_COLOR)
        self.screen.blit(title_surf, (OVERLAY_W // 2 - title_surf.get_width() // 2, y_offset))
        y_offset += 28

        # Разделитель
        pygame.draw.line(self.screen, (255, 255, 255, 80), (15, y_offset), (OVERLAY_W - 15, y_offset))
        y_offset += 10

        # Дальность
        dist = self.data.get("distance")
        if dist:
            dist_text = f"Дистанция: {dist}м"
            dist_surf = self.font_small.render(dist_text, True, TEXT_COLOR)
            self.screen.blit(dist_surf, (15, y_offset))
        else:
            dist_surf = self.font_small.render("Дистанция: ???", True, WARN_COLOR)
            self.screen.blit(dist_surf, (15, y_offset))
        y_offset += 22

        # Поправка на дальность (Elevation)
        elevation = self.data.get("elevation_mrad", 0)
        elev_label = self.font_label.render("↑ Elevation:", True, ELEV_COLOR)
        self.screen.blit(elev_label, (15, y_offset))
        elev_val = self.font_large.render(f"{elevation:+.1f}", True, ELEV_COLOR)
        self.screen.blit(elev_val, (OVERLAY_W - 80, y_offset - 4))
        y_offset += 30

        # Поправка на ветер (Windage)
        windage = self.data.get("windage_mrad", 0)
        wind_label = self.font_label.render("→ Windage:", True, WIND_COLOR)
        self.screen.blit(wind_label, (15, y_offset))
        wind_val = self.font_large.render(f"{windage:+.1f}", True, WIND_COLOR)
        self.screen.blit(wind_val, (OVERLAY_W - 80, y_offset - 4))
        y_offset += 25

        # Подсказка
        hint_surf = self.font_small.render("мрад", True, (150, 150, 150))
        self.screen.blit(hint_surf, (OVERLAY_W - 45, y_offset - 15))

    def run(self):
        """Главный цикл overlay"""
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            # Автоскрытие через OVERLAY_DURATION_MS
            if self.visible:
                elapsed = pygame.time.get_ticks() - self.show_time
                if elapsed > OVERLAY_DURATION_MS:
                    self.hide()

            self.render()
            pygame.display.flip()
            self.clock.tick(30)  # 30 FPS

        pygame.quit()


if __name__ == "__main__":
    # Тест: показать overlay с тестовыми данными
    overlay = Overlay()
    test_data = {
        "distance": 719,
        "elevation_mrad": 4.7,
        "windage_mrad": 1.2,
        "wind_speed": 5.0,
        "wind_dir": "NW",
        "azimuth": 90,
    }
    overlay.show(test_data)
    overlay.run()
