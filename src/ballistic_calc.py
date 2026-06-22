"""
Баллистический калькулятор для Arma Reforger
Расчёт поправок по дальности и ветру в милрадах
"""

import math
import json
import os

# Константы
GRAVITY = 9.81  # м/с²
AIR_DENSITY = 1.225  # кг/м³ (уровень моря, 15°C)

# Баллистические коэффициенты по калибрам
# BC — баллистический коэффициент пули
# MUZZLE_VELOCITY — начальная скорость м/с
# WEIGHT — масса пули в граммах
AMMUNITION = {
    "7.62x51_nato_m80": {
        "name": "7.62x51 NATO M80 Ball",
        "muzzle_velocity": 838,
        "bc": 0.395,  # G1
        "weight": 9.33,
        "drag_model": "g1"
    },
    "7.62x51_nato_m993": {
        "name": "7.62x51 NATO M993 AP",
        "muzzle_velocity": 910,
        "bc": 0.445,  # G1 (выше за счёт AP пули)
        "weight": 11.34,
        "drag_model": "g1"
    },
    "5.56x45_nato_m855": {
        "name": "5.56x45 NATO M855",
        "muzzle_velocity": 940,
        "bc": 0.337,  # G1
        "weight": 4.0,
        "drag_model": "g1"
    },
    ".338_lapua": {
        "name": ".338 Lapua Magnum",
        "muzzle_velocity": 936,
        "bc": 0.620,  # G1
        "weight": 16.2,
        "drag_model": "g1"
    },
    ".50_bmg_m33": {
        "name": ".50 BMG M33 Ball",
        "muzzle_velocity": 854,
        "bc": 0.640,  # G1
        "weight": 42.0,
        "drag_model": "g1"
    },
}

# Скорость звука (зависит от высоты и температуры)
# Arma Reforger: ~343 м/с на уровне моря
SPEED_OF_SOUND = 343.0


class G1DragModel:
    """Упрощённая G1 модель сопротивления воздуха"""

    # Таблица коэффициентов G1 (Mach -> Cd)
    # Упрощённые ключевые точки
    G1_TABLE = [
        (0.0, 0.0000),
        (0.7, 0.0000),
        (0.8, 0.0005),
        (0.9, 0.0015),
        (0.95, 0.0030),
        (1.0, 0.0100),
        (1.05, 0.0180),
        (1.1, 0.0280),
        (1.2, 0.0440),
        (1.3, 0.0550),
        (1.5, 0.0800),
        (2.0, 0.1600),
        (2.5, 0.2500),
        (3.0, 0.3400),
        (3.5, 0.3800),
        (4.0, 0.4000),
    ]

    @classmethod
    def get_drag_coefficient(cls, mach):
        """Интерполяция Cd по таблице G1"""
        for i in range(len(cls.G1_TABLE) - 1):
            m1, cd1 = cls.G1_TABLE[i]
            m2, cd2 = cls.G1_TABLE[i + 1]
            if m1 <= mach <= m2:
                t = (mach - m1) / (m2 - m1)
                return cd1 + t * (cd2 - cd1)
        return cls.G1_TABLE[-1][1]


def parse_wind_direction(wind_str):
    """
    Парсит направление ветра из строки 'NW', 'NE', 'S', 'SW', 'SE', 'E', 'W', 'N'
    Возвращает азимут в градусах (0-360)
    N=0, NE=45, E=90, SE=135, S=180, SW=225, W=270, NW=315
    """
    directions = {
        "N": 0, "NE": 45, "E": 90, "SE": 135,
        "S": 180, "SW": 225, "W": 270, "NW": 315
    }
    clean = wind_str.strip().upper()
    return directions.get(clean, 0)


def parse_azimuth(azimuth_str):
    """
    Парсит азимут: число (0-360) или буквы (N, NE, etc)
    """
    azimuth_str = azimuth_str.strip().upper()
    directions = {
        "N": 0, "NE": 45, "E": 90, "SE": 135,
        "S": 180, "SW": 225, "W": 270, "NW": 315
    }
    if azimuth_str in directions:
        return directions[azimuth_str]
    try:
        val = int(azimuth_str)
        return val % 360
    except (ValueError, TypeError):
        return 0


def calculate_trajectory(distance, ammo_key, wind_speed=0, wind_dir=0, fire_azimuth=0):
    """
    Симуляция траектории с учётом ветра

    distance — дальность до цели (м)
    ammo_key — ключ из AMMUNITION
    wind_speed — скорость ветра (м/с)
    wind_dir — направление ветра в градусах (откуда дует)
    fire_azimuth — азимут стрельбы в градусах (куда смотрит игрок)

    Возвращает dict с поправками в мрадах
    """
    ammo = AMMUNITION.get(ammo_key, AMMUNITION["7.62x51_nato_m993"])
    v0 = ammo["muzzle_velocity"]
    bc = ammo["bc"]

    # Угол между направлением ветра и направлением стрельбы
    # wind_dir — откуда дует ветер
    # fire_azimuth — куда стреляем
    # relative_angle — угол между ветром и линией стрельбы
    relative_angle = math.radians((wind_dir - fire_azimuth + 180) % 360)

    # Разложение ветра на продольную и поперечную составляющие
    headwind = wind_speed * math.cos(relative_angle)  # + попутный, - встречный
    crosswind = wind_speed * math.sin(relative_angle)   # + справа, - слева

    dt = 0.001  # шаг симуляции (секунды)
    max_time = 5.0  # максимальное время полёта

    x = 0.0  # горизонтальная дальность
    y = 0.0  # высота
    z = 0.0  # боковое смещение
    vx = v0
    vy = 0.0  # стреляем горизонтально, прицел компенсирует
    vz = 0.0

    # В Arma прицел выставлен на 0, стреляем горизонтально
    # Но для расчёта поправки считаем что стреляем горизонтально
    # и смотрим на сколько упадёт пуля

    while x < distance and dt * 1000 < max_time:
        speed = math.sqrt(vx ** 2 + vy ** 2 + vz ** 2)
        if speed < 10:
            break

        # Число Маха
        mach = speed / SPEED_OF_SOUND

        # Коэффициент лобового сопротивления
        cd = G1DragModel.get_drag_coefficient(mach)

        # Ускорение от сопротивления воздуха
        # a = (cd * ρ * A * v²) / (2 * m)
        # Упрощаем через BC: deceleration = v² / (bc * K)
        # K = 8 * ρ / (π * d² * BC) — нормированный коэффициент
        # Для G1: коэффициент замедления ≈ cd * v² / (bc * factor)
        drag_factor = cd / bc * 500  # эмпирический нормировочный множитель

        # Ускорение сопротивления по компонентам
        ax = -drag_factor * vx * speed * dt
        ay = -GRAVITY * dt - drag_factor * vy * speed * dt + headwind * 0.1 * dt
        az = -drag_factor * vz * speed * dt + crosswind * 0.5 * dt

        vx += ax
        vy += ay
        vz += az

        x += vx * dt
        y += vy * dt
        z += vz * dt

    # Время полёта
    if vx > 0:
        time_of_flight = distance / v0 * 1.2  # приближение
    else:
        time_of_flight = max_time

    # Поправка на дальность (Elevation) в мрадах
    # 1 мрад = расстояние / 1000
    # Если пуля упала на Y метров за DISTANCE метров:
    elevation_mrad = (y / distance) * 1000 if distance > 0 else 0

    # Поправка на ветер (Windage) в мрадах
    # Боковой снос за время полёта
    windage_mrad = (z / distance) * 1000 if distance > 0 else 0

    return {
        "distance": distance,
        "elevation_mrad": round(elevation_mrad, 2),  # поправка на дальность
        "windage_mrad": round(windage_mrad, 2),       # поправка на ветер
        "drop_meters": round(abs(y), 2),                # падение пули в метрах
        "crosswind": round(crosswind, 2),               # поперечная составляющая ветра
        "headwind": round(headwind, 2),                 # продольная составляющая
        "ammo": ammo["name"],
        "time_of_flight": round(time_of_flight, 3),
    }


if __name__ == "__main__":
    # Тест
    result = calculate_trajectory(
        distance=719,
        ammo_key="7.62x51_nato_m993",
        wind_speed=5.0,
        wind_dir=315,  # NW
        fire_azimuth=90  # стреляем на восток
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
