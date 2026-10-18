"""슬라이싱 단계의 최근접 도달 가능 로봇 영역 및 직접 좌표 행동."""
from __future__ import annotations

import numpy as np
from shapely import get_precision
from shapely.geometry import Point, Polygon, LineString
from shapely.ops import unary_union

from validator_adapter import parts

MAX_STROKES = 128
ACTION_SIZE = 3 * MAX_STROKES * 5
ACTION_DESCRIPTION = dict(
    shape=[3, MAX_STROKES, 5],
    fields=["start_x", "start_y", "end_x", "end_y", "enabled"],
    coordinates="[-1,1] mapped to the layer XY bounds; enabled > 0",
    ownership="nearest reachable robot base in XY, then robot ID",
)


def nearer_halfplane(bounds, own, other):
    """Clip a bounding rectangle by |p-own|² <= |p-other|²."""
    xmin, ymin, xmax, ymax = bounds
    points = [np.array(p, float) for p in ((xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax))]
    normal = np.asarray(other) - own
    limit = (np.dot(other, other) - np.dot(own, own)) / 2
    clipped = []
    for a, b in zip(points, points[1:] + points[:1]):
        fa, fb = np.dot(normal, a) - limit, np.dot(normal, b) - limit
        if fa <= 0:
            clipped.append(a)
        if (fa <= 0) != (fb <= 0):
            clipped.append(a + (b-a) * fa / (fa-fb))
    return Polygon(clipped) if len(clipped) >= 3 else Polygon()


def partition_layer(target, robots):
    """각 점은 도달 가능한 로봇 중 가장 가까운 base에 배정한다.

    도달 원은 내부 근사 다각형이다. 작은 미배정 면적도 결과에 기록하며,
    환경은 허용오차를 넘는 미배정 영역을 도달 불가로 처리한다.
    """
    bases = [np.asarray(robot.base_xyz_mm[:2], float) for robot in robots]
    reach = [Point(base).buffer(robot.xy_reach_radius_mm, quad_segs=256)
             for base, robot in zip(bases, robots)]
    result = []
    for r, base in enumerate(bases):
        region = target.intersection(reach[r])
        for other, other_base in enumerate(bases):
            if r == other:
                continue
            if np.array_equal(base, other_base):
                # 동일 위치의 base도 영역을 중복 소유하지 않게 한다.
                if robots[other].id < robots[r].id:
                    region = region.difference(reach[other])
            else:
                competitor = reach[other].intersection(nearer_halfplane(target.bounds, other_base, base))
                region = region.difference(competitor)
        result.append(region)
    uncovered = target.difference(unary_union(result)).area
    return result, float(uncovered)


def nearest_owner(point, robots):
    eligible = []
    for r, robot in enumerate(robots):
        distance = float(np.linalg.norm(np.asarray(point) - robot.base_xyz_mm[:2]))
        if distance <= robot.xy_reach_radius_mm + 1e-6:
            eligible.append((round(distance, 8), robot.id, r))
    return min(eligible)[2] if eligible else None


def clip_owned_line(line, region, robot_index, robots):
    """선분을 자기 영역으로 자른다. 공유 경계선의 소유권도 한 대로 고정한다."""
    selected = []
    for part in parts(line.intersection(region), "LineString"):
        if part.length <= 1e-5:
            continue
        if nearest_owner(part.interpolate(0.5, normalized=True).coords[0], robots) != robot_index:
            continue
        coords = list(part.coords)
        if line.project(Point(coords[0])) > line.project(Point(coords[-1])):
            coords.reverse()
        a, b = (tuple(np.asarray(p[:2], np.float32).astype(float)) for p in (coords[0], coords[-1]))
        if np.linalg.norm(np.asarray(a)-b) > 1e-5:
            selected.append((a, b))
    return sorted(selected, key=lambda segment: line.project(Point(segment[0])))


def direct_groups(action, target, regions, robots, bead_width, resolution):
    """PPO가 출력한 전체 레이어 좌표를 실행할 수 있는 적층 선분으로 변환한다.

    자동 채움/윤곽선을 추가하지 않는다. 목표 바깥 및 다른 로봇 영역만 잘라낸다.
    """
    values = np.asarray(action, np.float32).reshape(3, MAX_STROKES, 5)
    xmin, ymin, xmax, ymax = target.bounds
    origin, extent = np.array([xmin, ymin]), np.array([xmax-xmin, ymax-ymin])
    # float32 action -> millimetres round trips can put an exact contour a few
    # micrometres outside the inset. Preserve it with a numeric-only tolerance.
    tolerance = max(1e-5, 2*get_precision(target),
                    np.finfo(np.float32).eps * max(1.0, max(abs(v) for v in target.bounds)) * 4)
    printable = target.buffer(-0.49 * bead_width + tolerance, quad_segs=resolution)
    groups = [[], [], []]
    for r in range(3):
        owned = regions[r].intersection(printable)
        for sx, sy, ex, ey, enabled in values[r]:
            if enabled <= 0:
                continue
            a = origin + (np.array([sx, sy])+1)*extent/2
            b = origin + (np.array([ex, ey])+1)*extent/2
            if np.linalg.norm(b-a) > 1e-5:
                groups[r].extend(clip_owned_line(LineString([a, b]), owned, r, robots))
    return groups


def reference_action(env):
    """미학습 데모용 좌표 행동. PPO의 학습된 출력으로 해석하면 안 된다."""
    from layer_assignment_env import generate_layer_segments
    layer, target = env.layers[env.index]
    # 데모 좌표에만 작은 폴리곤 단순화를 적용한다. 실제 target/영역/평가
    # 형상은 원본이며, PPO가 출력한 좌표에는 이 단순화를 적용하지 않는다.
    planning_target = target.simplify(env.config.process.bead_width_mm * 0.05, preserve_topology=True)
    segments = generate_layer_segments(planning_target, env.config.process.bead_width_mm,
        min(2, env.config.shape_validation.polygon_buffer_resolution), [0, 1, 0, 0, 0, 0, 0],
        max_segment_mm=float('inf'))
    regions = env.territories[layer]
    xmin, ymin, xmax, ymax = target.bounds
    origin, extent = np.array([xmin, ymin]), np.array([xmax-xmin, ymax-ymin])
    action = np.zeros((3, MAX_STROKES, 5), np.float32)
    action[:, :, 4] = -1
    for r in range(3):
        own = [(a, b) for a, b in segments if LineString([a, b]).intersection(regions[r]).length > 1e-5]
        if len(own) > MAX_STROKES:
            raise ValueError(f"Reference path needs {len(own)} slots for robot {r+1}; limit={MAX_STROKES}")
        for i, (a, b) in enumerate(own):
            action[r, i] = [*(2*(np.asarray(a)-origin)/extent-1), *(2*(np.asarray(b)-origin)/extent-1), 1]
    return np.clip(action.reshape(-1), -1, 1)
