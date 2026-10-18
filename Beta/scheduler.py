"""동시 적층 배치: 충돌하는 다음 작업 대신 다른 미완료 작업을 탐색한다."""
from __future__ import annotations
import numpy as np
from waam_validator.collision.geometry2d import check_arm_envelope_xy_batch


def obvious_collision(env, rows):
    """Reject collisions already visible at motion knots/midpoints.

    This is only a rejection shortcut. Every accepted candidate still goes
    through the complete configured Validator sampling and trajectory checks.
    """
    knots = sorted({row[0] for own in rows for row in own})
    times = np.asarray(sorted(set(knots + [(a+b)/2 for a, b in zip(knots, knots[1:])])), float)
    positions = []
    for own in rows:
        positions.append(np.column_stack([np.interp(times, [row[0] for row in own],
                                           [row[axis] for row in own]) for axis in (1, 2, 3)]))
    config = env.config.collision
    for a, b in ((0, 1), (0, 2), (1, 2)):
        ra, rb = env.robots[a], env.robots[b]
        if config.check_tcp_radius:
            required = ra.tcp_radius_mm + rb.tcp_radius_mm
            # Strictly below the collision threshold: conservative even when
            # touching is allowed in a custom config.
            if np.any(np.linalg.norm(positions[a]-positions[b], axis=1) < required-config.geometry_epsilon_mm):
                return True
        if config.check_arm_envelope:
            result = check_arm_envelope_xy_batch(env.bases[a, :2], positions[a][:, :2], ra.arm_envelope_radius_mm,
                env.bases[b, :2], positions[b][:, :2], rb.arm_envelope_radius_mm,
                config.arm_clearance_mm, config.geometry_epsilon_mm, config.touching_is_collision)
            if result.collision.any():
                return True
    return False


def concurrency(rows, modes):
    events = []
    for own in rows:
        for a, b in zip(own, own[1:]):
            if a[4] in modes:
                events.extend([(a[0], 1), (b[0], -1)])
    durations = [0.0]*4
    active, previous = 0, 0.0
    for time, delta in sorted(events):
        durations[active] += time-previous
        active += delta
        previous = time
    return durations


def work_items(segments):
    """연결된 선분은 최대 6개씩 묶어 잦은 귀환을 줄인다."""
    result = []
    for segment in segments:
        if result and len(result[-1]) < 6 and np.linalg.norm(np.asarray(result[-1][-1][1])-segment[0]) < 1e-5:
            result[-1].append(segment)
        else:
            result.append([segment])
    return result


def schedule_layer(env, groups, z):
    """각 배치의 모든 로봇은 home에서 출발하고 귀환한다.

    도달 영역 소유권은 slicing 때 고정되어 있다. 공간적으로 충돌하는
    작업은 base와 작업 중심이 가까운 로봇을 먼저 고려한다. 다른 로봇은
    자기 미완료 목록 전체에서 동시 실행 가능한 작업을 찾아 교체한다.
    안전한 다른 작업이 없을 때만 그 배치를 기다린다.
    """
    pending = [[(i, item) for i, item in enumerate(work_items(group))] for group in groups]
    rows = [[[0.0, *home, "W"]] for home in env.homes]
    elapsed = 0.0
    batches = []
    checks = reordered = 0
    while any(pending):
        def priority(r):
            center = np.mean([point for segment in pending[r][0][1] for point in segment], axis=0)
            return float(np.linalg.norm(center-env.bases[r, :2])), env.robots[r].id
        order = sorted((r for r in range(3) if pending[r]), key=priority)
        selected = [[], [], []]
        choices = []
        selected_rows, duration = None, 0.0
        for r in order:
            # First slot may be near a busy seam; try every alternative before waiting.
            for position, (task_id, item) in enumerate(pending[r]):
                candidate = [list(own) for own in selected]
                candidate[r] = item
                candidate_rows, candidate_duration = env._local_rows(candidate, z, False, (0, 1, 2))
                checks += 1
                if obvious_collision(env, candidate_rows):
                    continue
                valid, reason = env._check_local(candidate_rows)
                if valid:
                    selected = candidate
                    selected_rows, duration = candidate_rows, candidate_duration
                    choices.append((r, position, task_id))
                    reordered += int(position > 0)
                    break
        if not choices:
            return None, None, dict(failure_reason="no_safe_territory_task", schedule_checks=checks)
        for r, position, _ in choices:
            pending[r].pop(position)
        for r, own in enumerate(selected_rows):
            rows[r][-1][4] = own[0][4]
            rows[r].extend([[row[0]+elapsed, *row[1:]] for row in own[1:]])
        batches.append(dict(start_s=elapsed, end_s=elapsed+duration,
            jobs=[dict(robot_id=env.robots[r].id, task_id=task_id, skipped_candidates=pos)
                  for r, pos, task_id in choices]))
        elapsed += duration
    busy = concurrency(rows, {"T", "D"})
    compacted_serial = False
    # If every tested batch ended up serial, avoid a pointless home round trip
    # after each small task. Keep each robot's whole territorial path together.
    # This replacement is also accepted only after the full collision check.
    if busy[2] + busy[3] <= 1e-9:
        serial_rows, serial_duration = env._local_rows(groups, z, True, (0, 1, 2))
        if serial_duration < elapsed and env._check_local(serial_rows)[0]:
            rows, elapsed = serial_rows, serial_duration
            compacted_serial = True
            jobs = []
            for r, own in enumerate(rows):
                active = [(a[0], b[0]) for a, b in zip(own, own[1:]) if a[4] in ('T', 'D')]
                if active:
                    jobs.append(dict(robot_id=env.robots[r].id, task_id='whole_region',
                                     start_s=active[0][0], end_s=active[-1][1]))
            batches = [dict(start_s=0.0, end_s=elapsed, serial_compaction=True, jobs=jobs)]
            busy = concurrency(rows, {"T", "D"})
    deposition = concurrency(rows, {"D"})
    return rows, elapsed, dict(schedule_checks=checks, reordered_tasks=reordered, compacted_serial=compacted_serial,
        batch_count=len(batches), batches=batches,
        simultaneous_2plus_s=busy[2]+busy[3], simultaneous_3_s=busy[3],
        deposition_2plus_s=deposition[2]+deposition[3], deposition_3_s=deposition[3])
