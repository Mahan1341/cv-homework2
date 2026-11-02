"""Регрессия: неверное разбиение прямых нельзя исправлять сортировкой углов."""
import numpy as np

import docscan as ds


def test_quad_from_lines_keeps_the_actual_intersection_cycle():
    # Здесь точки схода попадают внутрь кадра. Проверка одних границ кадра
    # недостаточна: ошибочное разбиение даёт пересекающийся цикл («бабочку»).
    quad = np.float32([
        [205.62114, 53.62203],
        [631.83612, 349.98984],
        [291.6055, 429.72134],
        [193.77942, 123.41159],
    ])
    lines = [ds.line_through(p, q) for p, q in zip(quad, np.roll(quad, -1, axis=0))]
    found = ds.quad_from_lines(lines, (480, 640))
    assert found is not None
    assert np.allclose(found, ds.order_corners(quad), atol=1e-3)
    assert ds.quad_iou(found, quad, (480, 640)) > 0.99
