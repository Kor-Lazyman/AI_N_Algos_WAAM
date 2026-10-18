"""Shorten validated layer schedules by spatial allocation and staggered starts.

Every candidate deposits exactly the generated segments. Routes start/end at
home. A waiting robot stays at home, and every accepted candidate is checked by
the official trajectory and collision validators. The original same-action
schedule remains a candidate, so a valid baseline cannot become slower here.
"""
from __future__ import annotations

import numpy as np
from waam_validator.collision.geometry2d import check_arm_envelope_xy_batch


def concurrency(rows, modes):
    events = []
    for own in rows:
        for a, b in zip(own, own[1:]):
            if a[4] in modes:
                events.extend(((a[0], 1), (b[0], -1)))
    durations = [0.0] * 4
    count, previous = 0, 0.0
    for time, delta in sorted(events):
        durations[count] += time - previous
        count += delta
        previous = time
    return durations


def activity_metrics(rows, duration):
    deposition = concurrency(rows, {"D"})
    times = [{mode: sum(b[0]-a[0] for a, b in zip(own, own[1:]) if a[4] == mode)
              for mode in ("D", "T", "W")} for own in rows]
    return dict(robot_deposition_s=[v["D"] for v in times],
                robot_travel_s=[v["T"] for v in times], robot_wait_s=[v["W"] for v in times],
                robot_deposition_utilization=[v["D"]/max(duration, 1e-9) for v in times],
                mean_deposition_utilization=sum(v["D"] for v in times)/max(3*duration, 1e-9),
                active_deposition_robots=sum(v["D"] > 1e-9 for v in times),
                deposition_single_s=deposition[1], deposition_2plus_s=deposition[2]+deposition[3],
                deposition_3_s=deposition[3], total_wait_s=sum(v["W"] for v in times))


def obvious_collision(env, rows):
    """Rejection shortcut only; passing this is never treated as validation."""
    knots = sorted({row[0] for own in rows for row in own})
    times = np.asarray(sorted(set(knots + [(a+b)/2 for a, b in zip(knots, knots[1:])])), float)
    positions = [np.column_stack([np.interp(times, [row[0] for row in own],
                    [row[axis] for row in own]) for axis in (1, 2, 3)]) for own in rows]
    config = env.config.collision
    for a, b in ((0, 1), (0, 2), (1, 2)):
        ra, rb = env.robots[a], env.robots[b]
        if config.check_tcp_radius:
            threshold = ra.tcp_radius_mm + rb.tcp_radius_mm
            if np.any(np.linalg.norm(positions[a]-positions[b], axis=1) < threshold-config.geometry_epsilon_mm):
                return True
        if config.check_arm_envelope:
            result = check_arm_envelope_xy_batch(env.bases[a, :2], positions[a][:, :2], ra.arm_envelope_radius_mm,
                env.bases[b, :2], positions[b][:, :2], rb.arm_envelope_radius_mm,
                config.arm_clearance_mm, config.geometry_epsilon_mm, config.touching_is_collision)
            if result.collision.any():
                return True
    return False


def reorder(group, home):
    """Nearest endpoint ordering shortens non-deposition travel without removing material."""
    if not group:
        return []
    points = np.asarray(group, dtype=float)
    remaining = np.ones(len(group), dtype=bool)
    position = np.asarray(home[:2])
    result = []
    for _ in group:
        distances = np.sum((points-position)**2, axis=2)
        distances[~remaining] = np.inf
        index, endpoint = np.unravel_index(np.argmin(distances), distances.shape)
        start, end = points[index] if endpoint == 0 else points[index][::-1]
        result.append((tuple(start), tuple(end)))
        position = end
        remaining[index] = False
    return result


def assigned_groups(env, segments, balance):
    groups, loads = [[], [], []], np.zeros(3)
    total = sum(np.linalg.norm(np.asarray(b)-a) for a, b in segments)
    for a, b in segments:
        reachable = env.reachable_robots(a, b)
        if not reachable:
            return None
        center = (np.asarray(a)+b)/2
        robot = min(reachable, key=lambda r: (
            np.linalg.norm(center-env.bases[r, :2])/env.coord_scale
            + balance*loads[r]/max(total/3, 1e-9), r))
        groups[robot].append((a, b))
        loads[robot] += np.linalg.norm(np.asarray(b)-a)
    return groups


def compose(env, routes, starts):
    rows = []
    for r, route in enumerate(routes):
        if route is None:
            rows.append([[0.0, *env.homes[r], "W"]])
            continue
        delay = starts[r]
        own = [[float(row[0]+delay), *row[1:]] for row in route]
        if delay > 1e-9:
            own.insert(0, [0.0, *env.homes[r], "W"])
        rows.append(own)
    duration = max(own[-1][0] for own in rows)
    for own in rows:
        if own[-1][0] < duration:
            own.append([duration, *own[-1][1:4], "W"])
    return rows, duration


def schedule_layer(env, segments, original_groups, z, order):
    checks, quick_rejections = 0, 0

    def valid(rows):
        nonlocal checks, quick_rejections
        if obvious_collision(env, rows):
            quick_rejections += 1
            return False
        checks += 1
        return env._check_local(rows)[0]

    # Exactly the original concurrent -> serial fallback, as an upper bound.
    baseline, base_duration = env._local_rows(original_groups, z, False, order)
    ok, reason = env._check_local(baseline)
    checks += 1
    if not ok and reason == "collision":
        baseline, base_duration = env._local_rows(original_groups, z, True, order)
        ok, reason = env._check_local(baseline)
        checks += 1
    best = (baseline, base_duration, original_groups, "original", [0., 0., 0.]) if ok else None

    candidates = [("policy_bands", original_groups),
                  ("nearest_base", assigned_groups(env, segments, 0.0)),
                  ("balanced_nearest", assigned_groups(env, segments, 0.35))]
    seen = set()
    for label, groups in candidates:
        if groups is None:
            continue
        signature = tuple(tuple((tuple(a), tuple(b)) for a, b in group) for group in groups)
        if signature in seen:
            continue
        seen.add(signature)
        groups = [reorder(group, env.homes[r]) for r, group in enumerate(groups)]
        simultaneous, _ = env._local_rows(groups, z, False, order)
        # Remove end-barrier padding; routes wait only at home until launch.
        routes = []
        for r, own in enumerate(simultaneous):
            route = [list(row) for row in own]
            while len(route) > 1 and route[-2][4] == "W":
                route.pop()
            routes.append(route if groups[r] else None)
        rows, duration = compose(env, routes, [0., 0., 0.])
        if (best is None or duration < best[1]-1e-8) and valid(rows):
            best = rows, duration, groups, label+"_concurrent", [0., 0., 0.]
            # All routes start at zero: no offset can shorten these routes.
            continue
        active = [r for r in order if routes[r] is not None]
        priorities = [active, sorted(active, key=lambda r: (-routes[r][-1][0], r))]
        for priority in dict.fromkeys(tuple(p) for p in priorities):
            placed, starts = [None]*3, [0.]*3
            elapsed = 0.
            feasible = True
            for r in priority:
                found = False
                # Fixed bounded search; feasibility need not be monotone in delay.
                for delay in np.linspace(0., elapsed, 17) if elapsed > 0 else [0.]:
                    trial = list(placed)
                    trial[r] = routes[r]
                    delays = list(starts)
                    delays[r] = float(delay)
                    rows, duration = compose(env, trial, delays)
                    if best is not None and duration >= best[1]-1e-8:
                        continue
                    if valid(rows):
                        placed, starts, elapsed = trial, delays, duration
                        found = True
                        break
                if not found:
                    feasible = False
                    break
            if feasible:
                rows, duration = compose(env, placed, starts)
                if best is None or duration < best[1]-1e-8:
                    best = rows, duration, groups, label+"_staggered", starts
    if best is None:
        return None, None, original_groups, dict(failure_reason=reason or "no_safe_schedule")
    rows, duration, groups, method, starts = best
    metrics = activity_metrics(rows, duration)
    metrics.update(schedule_method=method, schedule_checks=checks, quick_rejections=quick_rejections,
                   start_offsets_s=starts if method != "original" else None,
                   baseline_duration_s=base_duration if ok else None,
                   scheduler_reduction_s=base_duration-duration if ok else None,
                   serial_fallback=metrics["deposition_2plus_s"] <= 1e-9)
    return rows, duration, groups, metrics
