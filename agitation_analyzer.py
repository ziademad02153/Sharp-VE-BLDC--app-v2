# HIL MOTOR AGITATION ANALYZER - SHARP SPEC VALIDATION MODULE v4.0 (Sharp VE BLDC 11,13kg V4.xlsx)
# Per-stroke precision analysis with full calculation evidence. FAIL-only output.

TIMINGS = {
    "Group1": {
        "1": { "m2": (0.7, 1.0), "m3": (0.8, 1.0), "m4": (0.9, 1.0) },
        "2": { "m2": (1.1, 1.0), "m3": (1.2, 1.0), "m4": (1.3, 1.0) },
        "3": { "m2": (1.5, 1.0), "m3": (1.8, 1.5), "m4": (2.2, 1.5) },
        "4": { "m2": (2.2, 1.7), "m3": (4.0, 2.5), "m4": (4.0, 2.5) }
    },
    "Group2": {
        "1": { "m2": (1.0, 1.0), "m3": (1.1, 1.0), "m4": (1.2, 1.0) },
        "2": { "m2": (1.3, 1.0), "m3": (1.4, 1.0), "m4": (1.5, 1.0) },
        "3": { "m2": (1.7, 1.0), "m3": (1.9, 1.5), "m4": (2.3, 1.5) },
        "4": { "m2": (1.8, 1.0), "m3": (2.1, 1.5), "m4": (2.5, 2.0) }
    },
    "Group3": {
        "1": { "m2": (0.5, 2.0), "m3": (0.5, 2.0), "m4": (0.5, 2.0) },
        "2": { "m2": (0.5, 2.0), "m3": (0.5, 2.0), "m4": (0.5, 2.0) },
        "3": { "m2": (0.5, 2.0), "m3": (0.5, 2.0), "m4": (0.5, 2.0) },
        "4": { "m2": (0.5, 2.0), "m3": (0.5, 2.0), "m4": (0.5, 2.0) }
    },
    "Blanket": { "on": 3.8, "off": 0.7 },
    "Blanket_MU": { "on": 1.0, "off": 0.7 },
    "Tub Clean": { "on": 1.5, "off": 1.0 },
    "MU": { "on": 0.3, "off": 0.7 },
    "Soak": { "on": 2.4, "off": 2.6 }
}

COURSE_GROUPS = {
    "Group 1": ["Regular", "Quick", "Baby Care", "Quick Rinse"],
    "Group 2": ["Jeans", "Cotton", "Heavy"],
    "Group 3": ["Wool", "Delicates", "Sports Wear"]
}

FILL_TIMEOUT_SEC = 1200   # 20 minutes max fill time (E5 threshold)
TOLERANCE        = 0.10   # 100 ms tolerance per Sharp spec
TOLERANCE_WASH   = 60.0   # 60 seconds tolerance for total wash duration


def analyze_telemetry(raw_data_log, program_name, level_str,
                      wash_override=None, rinse_override=None, spin_override=None):
    """
    Parses HIL telemetry and returns ONLY FAIL defect entries.
    Each entry contains a full step-by-step calculation in Technical_Evidence.
    Defect entries include: Row_Index, Test_Name, Status, Severity, Priority,
                            Expected_Sec, Actual_Sec, Technical_Evidence
    """
    defects = []
    course_group = "Unknown"

    # ── 1. Determine expected timings ─────────────────────────────────────────
    if program_name == "Blanket":
        spec_set = {
            "m2": (2.4, 1.6),
            "m3": (2.4, 1.6),
            "m4": (3.8, 0.7)
        }
        level_key = "4"
    elif program_name == "Tub Clean":
        spec_set = {
            "m2": (3.4, 4.6),
            "m3": (3.4, 4.6),
            "m4": (1.5, 1.0)
        }
        level_key = "4"
    elif program_name == "Soak":
        spec_set = {
            "m2": (2.4, 2.6),
            "m3": (2.4, 2.6),
            "m4": (2.4, 2.6)
        }
        level_key = "2"
    else:
        course_group = "Group1"
        for g_name, progs in COURSE_GROUPS.items():
            if program_name in progs:
                course_group = g_name.replace(" ", "")
                break

        level_key = "2"
        if isinstance(level_str, int):
            level_key = str(level_str)
        elif isinstance(level_str, str):
            level_key = level_str.replace("LEV-", "").strip()

        spec_set = TIMINGS.get(course_group, TIMINGS["Group1"]).get(
            level_key, TIMINGS["Group1"]["2"]
        )

    # Load dynamic sequence variables from sharp_spec.json
    import json
    import os
    try:
        spec_path = os.path.join(os.path.dirname(__file__), 'sharp_spec.json')
        with open(spec_path, 'r', encoding='utf-8') as f:
            full_spec = json.load(f)
            seq_data = full_spec.get('sequence_chart', {}).get(program_name, {}).get(f"LEV-{level_key}", {})
            spec_set['rinse_wash_sec'] = seq_data.get('rinse_wash_sec', 240)
            spec_set['rinse_count'] = seq_data.get('rinse_count', 2)
            spec_set['expected_wash_sec'] = seq_data.get('main_wash_sec', 1080)
    except Exception:
        spec_set['rinse_wash_sec'] = 240
        spec_set['rinse_count'] = 2
        spec_set['expected_wash_sec'] = 1080

    if program_name == "Blanket":
        global_mu_spec = (TIMINGS["Blanket_MU"]["on"], TIMINGS["Blanket_MU"]["off"])
    else:
        if level_key in ["3", "4"]:
            global_mu_spec = (TIMINGS["MU"]["on"], 0.5)
        else:
            global_mu_spec = (TIMINGS["MU"]["on"], TIMINGS["MU"]["off"])

    # ── 2. Split raw data into motor-active strokes ───────────────────────────
    raw_strokes = []
    current = []
    for row in raw_data_log:
        if row[7] > 2.0:  # Use Motor_V (row[7]) instead of RPM
            current.append(row)
        else:
            if current:
                raw_strokes.append(current)
                current = []
    if current:
        raw_strokes.append(current)

    # Remove SPIN/DRAIN strokes (pump or gearmotor voltage > 2 V)
    raw_strokes = [s for s in raw_strokes if not any(r[8] > 2.0 or r[6] > 2.0 for r in s)]

    if not raw_strokes:
        return defects, {}

    # ── 3. Calibrate each stroke (ON time, OFF time, next_start_row) ──────────
    calibrated = []
    for idx, stroke in enumerate(raw_strokes):
        start_row   = stroke[0][0]
        end_row     = stroke[-1][0]
        peak_v      = max(r[7] for r in stroke)

        # Ignore tiny noise blips
        if peak_v < 2.0:
            continue

        on_rows  = end_row - start_row + 1
        elec_on  = round(on_rows * 0.1, 2)

        cold_avg = sum(r[3] for r in stroke) / len(stroke)
        hot_avg  = sum(r[4] for r in stroke) / len(stroke)

        calibrated.append({
            "start_row":      start_row,
            "end_row":        end_row,
            "on_rows":        on_rows,
            "elec_on":        elec_on,
            "is_water_active": (cold_avg > 1.0 or hot_avg > 1.0),
            "peak_v":         peak_v
        })

    # ── 4. Noise filter ───────────────────────────────────────────────────────
    filtered = []
    for idx, s in enumerate(calibrated):
        if s["elec_on"] < 0.25 or s["peak_v"] < 2.0:
            continue
        filtered.append(s)

    # Recalculate OFF / next_start_row after filtering
    for i in range(len(filtered) - 1):
        filtered[i]["next_start_row"] = filtered[i+1]["start_row"]
        filtered[i]["elec_off"] = round((filtered[i+1]["start_row"] - filtered[i]["end_row"] - 1) * 0.1, 2)
    if filtered:
        filtered[-1]["elec_off"] = None
        filtered[-1]["next_start_row"] = None

    calibrated = filtered

    # ── 5. Water Fill Duration + E5 Detection ─────────────────────────────────
    first_fill_row = None
    fill_end_row   = None

    debounce_count = 0
    for r in raw_data_log:
        if first_fill_row is None and (r[3] > 4.0 or r[4] > 4.0):
            first_fill_row = r[0]
        if first_fill_row and fill_end_row is None:
            if r[3] < 2.0 and r[4] < 2.0:
                debounce_count += 1
                if debounce_count >= 20:
                    fill_end_row = r[0] - 20
                    break
            else:
                debounce_count = 0

    if first_fill_row is not None:
        actual_end   = fill_end_row if fill_end_row else raw_data_log[-1][0]
        fill_rows    = actual_end - first_fill_row + 1
        fill_sec     = round(fill_rows * 0.1, 1)
        fill_min     = round(fill_sec / 60, 2)
        timeout_min  = FILL_TIMEOUT_SEC // 60

        is_e5 = fill_end_row is None  # pressure switch never triggered

        if is_e5 or fill_sec > FILL_TIMEOUT_SEC:
            label    = "E5 Timeout - Level Never Reached" if is_e5 else "Fill Duration Overrun"
            severity = "Critical"
            delta    = round(fill_sec - FILL_TIMEOUT_SEC, 1)
            defects.append({
                "Row_Index":          f"{first_fill_row}-{actual_end}",
                "Test_Name":          "M1 Water Fill - E5 Error",
                "Status":             "FAIL",
                "Severity":           "Critical",
                "Priority":           "High",
                "Expected_Sec":       f"Max {FILL_TIMEOUT_SEC}s ({timeout_min} min)",
                "Actual_Sec":         f"{fill_sec}s ({fill_min} min)",
                "Technical_Evidence": (
                    f"Number of rows: ({actual_end} - {first_fill_row} + 1) = {fill_rows} rows\n"
                    f"Time in seconds: {fill_rows} × 0.1 = {fill_sec}s\n"
                    f"Time in minutes: {fill_sec} ÷ 60 = {fill_min} min\n"
                    f"Max allowed: {timeout_min} min ({FILL_TIMEOUT_SEC}s)\n"
                    f"Delta: {fill_sec} - {FILL_TIMEOUT_SEC} = {delta:+.1f}s\n"
                    f"Verdict: {label}"
                )
            })

        else:
            defects.append({
                "Row_Index":          f"{first_fill_row}-{actual_end}",
                "Test_Name":          "Phase Tracking: Initial Water Fill",
                "Status":             "PASS",
                "Severity":           "Low",
                "Priority":           "Low",
                "Expected_Sec":       f"Max {FILL_TIMEOUT_SEC}s",
                "Actual_Sec":         f"{fill_sec}s",
                "Technical_Evidence": f"Initial Water Fill completed successfully.\nDuration: {fill_sec}s."
            })

    # ── 9. Spin Profile Validation ─────────────────────────────────────────────
    rpm_lookup = {r[0]: r[2] for r in raw_data_log}
    
    in_spin = False
    spin_start = 0
    raw_spin_blocks = []
    
    for r in raw_data_log:
        rpm = r[2]
        if rpm > 150 and not in_spin:
            in_spin = True
            spin_start = r[0]
        elif rpm <= 10 and in_spin:
            in_spin = False
            duration_rows = r[0] - spin_start
            duration_sec = duration_rows * 0.1
            if duration_sec > 5.0: # Capture any spin > 5s
                raw_spin_blocks.append({
                    "start": spin_start,
                    "end": r[0],
                    "duration_sec": duration_sec
                })

    # Group into logical phases based on water fills
    logical_phases = []
    if raw_spin_blocks:
        current_phase = [raw_spin_blocks[0]]
        
        for i in range(1, len(raw_spin_blocks)):
            prev_block = raw_spin_blocks[i-1]
            curr_block = raw_spin_blocks[i]
            
            # Check if water filled between prev_block["end"] and curr_block["start"]
            water_filled = False
            for row in raw_data_log:
                if prev_block["end"] <= row[0] <= curr_block["start"]:
                    if row[3] > 0.5 or row[4] > 0.5 or row[5] > 0.5:
                        water_filled = True
                        break
                elif row[0] > curr_block["start"]:
                    break
                    
            if water_filled:
                logical_phases.append(current_phase)
                current_phase = [curr_block]
            else:
                current_phase.append(curr_block)
                
        logical_phases.append(current_phase)

    # Pick the longest attempt per logical phase
    spin_blocks = []
    for phase in logical_phases:
        longest_block = max(phase, key=lambda b: b["duration_sec"])
        if longest_block["duration_sec"] > 30.0:
            spin_blocks.append(longest_block)

    # ── 6\. Chronological Wash Phase Tracking \(M2 -> M3 -> M4 -> MU\) ───────────
    all_valid_strokes = [s for s in calibrated if fill_end_row is None or s["start_row"] > fill_end_row]
    first_spin_start = spin_blocks[0]["start"] if spin_blocks else float('inf')
    valid_strokes = [s for s in all_valid_strokes if s["end_row"] < first_spin_start]

    # Expected wash duration
    expected_wash_sec = None
    if wash_override and wash_override != "Default":
        try:
            expected_wash_sec = float(wash_override.split(" ")[0]) * 60
        except Exception:
            pass
    else:
        try:
            import json, os
            spec_path = os.path.join(os.path.dirname(__file__), "sharp_spec.json")
            with open(spec_path, "r", encoding="utf-8") as f:
                spec_data = json.load(f)
            expected_wash_sec = float(spec_data.get("sequence_chart", {}).get(program_name, {}).get(level_str, {}).get("main_wash_sec", 0))
            if expected_wash_sec == 0:
                expected_wash_sec = None
        except Exception:
            pass

    # Find drain row (to stop wash phases)
    first_motor_row = valid_strokes[0]["start_row"] if valid_strokes else None
    first_drain_row = None
    for r in raw_data_log:
        if first_motor_row and r[0] > first_motor_row + 100 and r[8] > 2.0:
            first_drain_row = r[0]
            break

    drain_ref = first_drain_row if first_drain_row else 9_999_999
    spin_rows = [r[0] for r in raw_data_log if r[2] > 150.0]
    last_spin_row = spin_rows[-1] if spin_rows else 0

    active_wash_time = 0.0
    m2, m3, m4, mu, aw = [], [], [], [], []
    
    m2_start, m2_end = None, None
    m3_start, m3_end = None, None
    m4_start, m4_end = None, None
    mu_start, mu_end = None, None
    
    # Track pattern to split M4 and MU
    m4_finished_pattern_wise = False
    consecutive_mu_strokes = 0
    
    for idx, s in enumerate(valid_strokes):
        if last_spin_row > 0 and s["start_row"] > last_spin_row:
            if s["elec_on"] >= 0.3:
                aw.append(s)
            continue

        if s["elec_on"] > 10.0:
            continue
            
        if s["start_row"] >= drain_ref:
            continue
            
        # Accumulate active wash time (for M2 and M3)
        active_wash_time += s["elec_on"]
        off_time = s.get("elec_off", 0.0)
        if off_time is not None and off_time <= 5.0:
            active_wash_time += off_time
            
        # Determine M2 and M3 subtotal cutoffs dynamically per V4 spec for ALL groups
        is_lvl4 = (level_str in ["LEV-4", "4", "11_13"] or level_key == "4")
        cg_clean = str(course_group).replace(" ", "")
        is_grp1 = (cg_clean == "Group1" or program_name in COURSE_GROUPS.get("Group 1", []))
        is_grp2 = (cg_clean == "Group2" or program_name in COURSE_GROUPS.get("Group 2", []))
        is_grp3 = (cg_clean == "Group3" or program_name in COURSE_GROUPS.get("Group 3", []))

        if is_grp1:
            m2_limit = 360.0 if is_lvl4 else 60.0
            m3_limit = m2_limit + (720.0 if is_lvl4 else 120.0)
        elif is_grp2:
            m2_limit = 60.0
            m3_limit = m2_limit + 180.0
        elif is_grp3:
            m2_limit = 60.0
            m3_limit = m2_limit + 180.0
        else:
            m2_limit = 60.0
            m3_limit = 240.0

        # Classify based on active wash time for M2 and M3
        if active_wash_time <= m2_limit:
            m2.append(s)
            if not m2_start: m2_start = s["start_row"]
            m2_end = s["end_row"]
        elif active_wash_time <= m3_limit:
            m3.append(s)
            if not m3_start: m3_start = s["start_row"]
            m3_end = s["end_row"]
        else:
            # We are past M3. It is either M4 or MU.
            # Determine dynamically using Pattern Recognition!
            if not m4_finished_pattern_wise:
                # Is this an MU pattern stroke? (~0.3s ON, ~0.7s OFF)
                # But wait, it must NOT be interrupted by a water valve!
                is_interrupted = False
                end_idx = s["end_row"]
                # Scan raw data around end_row to see if valve opened
                for r in raw_data_log:
                    if r[0] < end_idx - 5: continue
                    if r[0] > end_idx + 100: break
                    if r[3] > 4.0 or r[4] > 4.0:
                        is_interrupted = True
                        break
                        
                if not is_interrupted and s["elec_on"] <= 0.5 and off_time is not None and 0.5 <= off_time <= 1.5:
                    consecutive_mu_strokes += 1
                else:
                    consecutive_mu_strokes = 0
                    
                # If we see 3 consecutive MU pattern strokes, we declare M4 finished retroactively!
                if consecutive_mu_strokes >= 3:
                    m4_finished_pattern_wise = True
                    # Move those 3 strokes from M4 to MU
                    for _ in range(2):
                        popped_stroke = m4.pop()
                        mu.insert(0, popped_stroke)
                    mu.insert(0, s)
                    if not mu_start: mu_start = mu[0]["start_row"]
                    mu_end = s["end_row"]
                    m4_end = m4[-1]["end_row"] if m4 else m3_end
                    continue
                else:
                    m4.append(s)
                    if not m4_start: m4_start = s["start_row"]
                    m4_end = s["end_row"]
            else:
                # M4 already finished, everything else is MU
                mu.append(s)
                if not mu_start: mu_start = s["start_row"]
                mu_end = s["end_row"]

    # Helper for appending Phase Tracking PASS records
    def append_phase_tracking(name, start, end, expected_sec):
        if not start or end is None: return
        dur_sec = round((end - start) * 0.1, 1)
        dur_min = round(dur_sec / 60, 2)
        defects.append({
            "Row_Index":          f"{start}-{end}",
            "Test_Name":          f"Phase Tracking: {name}",
            "Status":             "PASS",
            "Severity":           "Low",
            "Priority":           "Low",
            "Expected_Sec":       expected_sec,
            "Actual_Sec":         f"{dur_sec}s ({dur_min} min) Clock Time",
            "Technical_Evidence": f"Phase {name} successfully identified.\nStart Row: {start}\nEnd Row: {end}\nClock Duration: {dur_sec}s."
        })

    # Append Phase Tracking (Pre-Wash vs Main Wash)
    append_phase_tracking("Pre-Wash M2", m2_start, m2_end, "60s (Active)")
    append_phase_tracking("Pre-Wash M3", m3_start, m3_end, "180s (Active)")
    if m4_start: append_phase_tracking("Main Wash M4", m4_start, m4_end, "720s+ (Active)")
    if mu_start: append_phase_tracking("MU Untangle", mu_start, mu_end, "N/A")

    # ── 7. Per-stroke validation ───────────────────────────────────────────────
    def validate_movement(movement_strokes, phase_name, expected_specs):
        '''Returns a list of FAIL dicts — one per failing ON or OFF measurement.'''
        result = []

        if not movement_strokes:
            result.append({
                "Row_Index":          "N/A",
                "Test_Name":          f"{phase_name} Agitation - Dead Motor",
                "Status":             "FAIL",
                "Severity":           "Critical",
                "Priority":           "High",
                "Expected_Sec":       f"ON: {expected_specs[0]}s | OFF: {expected_specs[1]}s",
                "Actual_Sec":         "0 strokes detected",
                "Technical_Evidence": (
                    f"DEAD MOTOR: No {phase_name} strokes detected during expected phase window.\n"
                    f"Expected: Motor must agitate per spec (ON: {expected_specs[0]}s / OFF: {expected_specs[1]}s)\n"
                    f"Source: Sharp HIL Specification (Course: {program_name}, Level: LEV-{level_key}, Phase: {phase_name})"
                )
            })
            return result

        exp_on, exp_off = expected_specs

        for idx, s in enumerate(movement_strokes):
            stroke_num = idx + 1

            actual_on = s["elec_on"]
            actual_off = s.get("elec_off")
            
            # ── Check for Water Valve Interruption ──
            is_interrupted = False
            end_idx = s["end_row"]
            for r in raw_data_log:
                if r[0] < end_idx - 10: continue
                if r[0] > end_idx + 100: break
                if r[3] > 4.0 or r[4] > 4.0:
                    is_interrupted = True
                    break

            # ── Mechanical Inertia Compensation (Cycle Time) ──
            cycle_pass = False
            if actual_off is not None and actual_off < 15.0:
                actual_cycle = actual_on + actual_off
                exp_cycle = exp_on + exp_off
                if round(abs(actual_cycle - exp_cycle), 2) <= TOLERANCE:
                    cycle_pass = True

            # ── ON Time check ──
            on_rows   = s["on_rows"]
            on_delta  = round(actual_on - exp_on, 2)

            if not cycle_pass and abs(on_delta) > TOLERANCE:
                if is_interrupted and on_delta < 0:
                    # Ignore deficit if interrupted by water valve!
                    pass
                else:
                    direction = "Overrun" if on_delta > 0 else "Deficit"
                    result.append({
                        "Row_Index":          f"{s['start_row']}-{s['end_row']}",
                        "Test_Name":          f"{phase_name} Stroke #{stroke_num} - ON Time",
                        "Status":             "FAIL",
                        "Severity":           "Medium",
                        "Priority":           "Medium",
                        "Expected_Sec":       f"{exp_on}s",
                        "Actual_Sec":         f"{actual_on}s",
                        "Delta_Sec":          f"{on_delta:+.2f}s",
                        "Technical_Evidence": (
                            f"Number of rows: ({s['end_row']} - {s['start_row']} + 1) = {on_rows} rows\n"
                            f"Time in seconds: {on_rows} * 0.1 = {actual_on}s\n"
                            f"Expected ON: {exp_on}s\n"
                            f"Delta: {actual_on} - {exp_on} = {on_delta:+.2f}s ({direction})"
                        )
                    })

            # ── OFF Time check ──
            actual_off = s.get("elec_off")
            if actual_off is not None and actual_off < 15.0:
                off_delta = round(actual_off - exp_off, 2)

                if not cycle_pass and abs(off_delta) > TOLERANCE:
                    if is_interrupted and off_delta < 0:
                        # Ignore deficit if interrupted by water valve!
                        pass
                    else:
                        direction  = "Overrun" if off_delta > 0 else "Deficit"
                        ns         = s["next_start_row"] if s["next_start_row"] else s["end_row"]
                        off_rows   = round(actual_off / 0.1)
                        result.append({
                            "Row_Index":          f"{s['end_row']}-{ns}",
                            "Test_Name":          f"{phase_name} Stroke #{stroke_num} - OFF Time",
                            "Status":             "FAIL",
                            "Severity":           "Medium",
                            "Priority":           "Medium",
                            "Expected_Sec":       f"{exp_off}s",
                            "Actual_Sec":         f"{actual_off}s",
                            "Delta_Sec":          f"{off_delta:+.2f}s",
                            "Technical_Evidence": (
                                f"Number of rows: ({ns} - {s['end_row']} - 1) = {off_rows} rows\n"
                                f"Time in seconds: {off_rows} × 0.1 = {actual_off}s\n"
                                f"Expected OFF: {exp_off}s\n"
                                f"Delta: {actual_off} - {exp_off} = {off_delta:+.2f}s ({direction})"
                            )
                        })
                        
        if not result and movement_strokes:
            start_row = movement_strokes[0]["start_row"]
            end_row = movement_strokes[-1]["end_row"]
            dur_sec = round((end_row - start_row) * 0.1, 1)
            result.append({
                "Row_Index": f"{start_row}-{end_row}",
                "Test_Name": f"{phase_name} Phase Validation",
                "Status": "PASS", "Severity": "Low", "Priority": "Low",
                "Expected_Sec": f"ON: {expected_specs[0]}s | OFF: {expected_specs[1]}s",
                "Actual_Sec": f"{len(movement_strokes)} strokes",
                "Delta_Sec": "0.00s",
                "Technical_Evidence": f"All {len(movement_strokes)} strokes passed the validation (within ±{TOLERANCE}s tolerance).\nPhase Duration: {dur_sec}s."
            })

        return result

    # ── 8. Run validations in order ───────────────────────────────────────────
    skip_m2_m3 = (program_name == "Quick")

    if skip_m2_m3:
        m4 = sorted(m2 + m3 + m4, key=lambda s: s["start_row"])
        m2, m3 = [], []
    else:
        defects.extend(validate_movement(m2, "M2", spec_set["m2"]))
        defects.extend(validate_movement(m3, "M3", spec_set["m3"]))

    defects.extend(validate_movement(m4, "M4", spec_set["m4"]))

    if program_name == "Blanket":
        defects.extend(validate_movement(mu, "MU", (TIMINGS["Blanket_MU"]["on"], TIMINGS["Blanket_MU"]["off"])))
    elif course_group != "Group3":
        defects.extend(validate_movement(mu, "MU", (TIMINGS["MU"]["on"], TIMINGS["MU"]["off"])))

    if aw:
        defects.extend(validate_movement(aw, "Anti-Wrinkle", (0.8, 1.0)))

    if m4 and expected_wash_sec:
        first_m4 = m4_start
        last_m4 = m4_end
        m4_clock_sec  = round((last_m4 - first_m4) * 0.1, 1)
        
        m4_active_time = sum(s["elec_on"] + ((s.get("elec_off") or 0.0) if (s.get("elec_off") or 0.0) <= 5.0 else 0.0) for s in m4)
        
        delta = round(m4_active_time - expected_wash_sec, 1)
        
        if abs(delta) > TOLERANCE_WASH:
            direction = "Overrun" if delta > 0 else "Deficit"
            defects.append({
                "Row_Index":          f"{first_m4}-{last_m4}",
                "Test_Name":          "M4 - Total Wash Time",
                "Status":             "FAIL",
                "Severity":           "High",
                "Priority":           "Medium",
                "Expected_Sec":       f"{expected_wash_sec}s (Active)",
                "Actual_Sec":         f"{round(m4_active_time, 1)}s (Active)",
                "Delta_Sec":          f"{delta:+.1f}s",
                "Technical_Evidence": (
                    f"M4 Wash Phase from row {first_m4} to {last_m4}.\n"
                    f"Clock Duration: {m4_clock_sec}s\n"
                    f"Active Wash Time: {round(m4_active_time, 1)}s\n"
                    f"Expected Active Time: {expected_wash_sec}s\n"
                    f"Delta: {delta:+.1f}s ({direction})"
                )
            })
        else:
            defects.append({
                "Row_Index":          f"{first_m4}-{last_m4}",
                "Test_Name":          "M4 - Total Wash Time",
                "Status":             "PASS",
                "Severity":           "Low",
                "Priority":           "Low",
                "Expected_Sec":       f"{expected_wash_sec}s (Active)",
                "Actual_Sec":         f"{round(m4_active_time, 1)}s (Active)",
                "Delta_Sec":          f"{delta:+.1f}s",
                "Technical_Evidence": (
                    f"M4 Wash Phase successfully matched expected duration.\n"
                    f"Active Wash Time: {round(m4_active_time, 1)}s (Expected: {expected_wash_sec}s)"
                )
            })

    # ── 7. Rinse Phase Tracking ───
    expected_rinse_sec = spec_set.get('rinse_wash_sec', 240)
    
    for i in range(len(spin_blocks)):
        if i == len(spin_blocks) - 1:
            continue # No rinse after final spin
            
        spin_end = spin_blocks[i]["end"]
        next_spin_start = spin_blocks[i+1]["start"]
        
        rinse_strokes = [s for s in all_valid_strokes if spin_end < s["start_row"] < next_spin_start]
        if not rinse_strokes:
            continue
            
        is_final_rinse = (i == len(spin_blocks) - 2)
        rinse_name = "Final Rinse (Static W)" if is_final_rinse else f"Rinse #{i+1} (Static S)"
        
        # 7.1 Softener Valve Check
        softener_was_on = False
        softener_start = 0
        softener_end = 0
        for r in raw_data_log:
            if spin_end < r[0] < rinse_strokes[0]["start_row"]:
                if r[3] > 0.5 or r[4] > 0.5: # Water filling
                    if r[5] > 2.0: # Softener > 2V
                        if not softener_was_on:
                            softener_was_on = True
                            softener_start = r[0]
                        softener_end = r[0]
                        
        if is_final_rinse:
            if not softener_was_on:
                defects.append({
                    "Row_Index": f"{spin_end}-{rinse_strokes[0]['start_row']}",
                    "Test_Name": f"{rinse_name} - Softener Valve Check",
                    "Status": "FAIL", "Severity": "High", "Priority": "High",
                    "Expected_Sec": "> 2V (ON)", "Actual_Sec": "OFF",
                    "Technical_Evidence": "Softener valve did not open during the water fill for the final rinse."
                })
            else:
                dur_sec = round((softener_end - softener_start) * 0.1, 1)
                defects.append({
                    "Row_Index": f"{softener_start}-{softener_end}",
                    "Test_Name": f"{rinse_name} - Softener Valve Check",
                    "Status": "PASS", "Severity": "Low", "Priority": "Low",
                    "Expected_Sec": "> 2V (ON)", "Actual_Sec": "ON",
                    "Delta_Sec": "",
                    "Technical_Evidence": f"Softener valve successfully opened during final rinse water fill.\nDuration: {dur_sec}s."
                })
        else:
            if softener_was_on:
                defects.append({
                    "Row_Index": f"{spin_end}-{rinse_strokes[0]['start_row']}",
                    "Test_Name": f"{rinse_name} - Softener Valve Check",
                    "Status": "FAIL", "Severity": "High", "Priority": "High",
                    "Expected_Sec": "OFF (Cold Only)", "Actual_Sec": "> 2V (ON)",
                    "Technical_Evidence": "Softener valve incorrectly opened during an intermediate rinse (Static Rinse S)."
                })
                
        # 7.2 Duration Check
        active_time = sum(s["elec_on"] + ((s.get("elec_off") or 0.0) if (s.get("elec_off") or 0.0) <= 5.0 else 0.0) for s in rinse_strokes)
        delta = round(active_time - expected_rinse_sec, 1)
        
        TOLERANCE_RINSE = 5.0  # Configurable tight tolerance for Rinse Phase
        
        if abs(delta) > TOLERANCE_RINSE:
            direction = "Overrun" if delta > 0 else "Deficit"
            defects.append({
                "Row_Index": f"{rinse_strokes[0]['start_row']}-{rinse_strokes[-1]['end_row']}",
                "Test_Name": f"{rinse_name} - Total Duration Validation",
                "Status": "FAIL", "Severity": "High", "Priority": "Medium",
                "Expected_Sec": f"{expected_rinse_sec}s (Active)", "Actual_Sec": f"{round(active_time, 1)}s (Active)",
                "Delta_Sec": f"{delta:+.1f}s",
                "Technical_Evidence": f"Expected: {expected_rinse_sec}s. Actual active time: {round(active_time, 1)}s. Delta: {delta:+.1f}s ({direction})"
            })
        else:
            defects.append({
                "Row_Index": f"{rinse_strokes[0]['start_row']}-{rinse_strokes[-1]['end_row']}",
                "Test_Name": f"{rinse_name} - Total Duration Validation",
                "Status": "PASS", "Severity": "Low", "Priority": "Low",
                "Expected_Sec": f"{expected_rinse_sec}s (Active)", "Actual_Sec": f"{round(active_time, 1)}s (Active)",
                "Delta_Sec": f"{delta:+.1f}s",
                "Technical_Evidence": f"Rinse Phase successfully matched expected duration.\nActive Rinse Time: {round(active_time, 1)}s (Expected: {expected_rinse_sec}s)"
            })

            
        # 7.3 Pattern-based Separation of MR (M4) and MU in Rinse
        rinse_m4 = []
        rinse_mu = []
        expected_mu_on = global_mu_spec[0]
        expected_m4_on = spec_set["m4"][0]
        
        for s in rinse_strokes:
            # Classify stroke by seeing which spec it is closer to
            if abs(s["elec_on"] - expected_mu_on) < abs(s["elec_on"] - expected_m4_on):
                rinse_mu.append(s)
            else:
                rinse_m4.append(s)
        
        if is_final_rinse:
            last_row = rinse_strokes[-1]["end_row"]
            untangle_start = last_row - 600
            
            untangle_strokes = [s for s in rinse_mu if s["start_row"] >= untangle_start]
            early_mu = [s for s in rinse_mu if s["end_row"] < untangle_start]
            
            if not untangle_strokes:
                defects.append({
                    "Row_Index": f"{untangle_start}-{last_row}",
                    "Test_Name": f"{rinse_name} - Untangle 60s Check",
                    "Status": "FAIL", "Severity": "High", "Priority": "High",
                    "Expected_Sec": "60s MU Motion", "Actual_Sec": "None",
                    "Technical_Evidence": "No MU agitation detected in the final 60 seconds of the rinse."
                })
            else:
                defects.extend(validate_movement(untangle_strokes, f"{rinse_name} Untangle MU", global_mu_spec))
                
            if early_mu:
                defects.extend(validate_movement(early_mu, f"{rinse_name} MU", global_mu_spec))
                
            if rinse_m4:
                defects.extend(validate_movement(rinse_m4, f"{rinse_name} MR (M4)", spec_set["m4"]))
        else:
            if rinse_mu:
                defects.extend(validate_movement(rinse_mu, f"{rinse_name} MU", global_mu_spec))
            if rinse_m4:
                defects.extend(validate_movement(rinse_m4, f"{rinse_name} MR (M4)", spec_set["m4"]))
                

    # Determine milestones based on Program
    is_gentle = program_name in ["Delicates", "Wool", "Sports Wear"]

    for i, block in enumerate(spin_blocks):
        is_last = (i == len(spin_blocks) - 1)
        if i == 0:
            spin_name = "Balance Spin"
        elif is_last:
            spin_name = "Final Spin"
        else:
            # If there's only 1 intermediate spin, don't number it. Otherwise number it 1, 2, 3...
            if len(spin_blocks) == 3:
                spin_name = "Intermediate Spin"
            else:
                spin_name = f"Intermediate Spin #{i}"
        
        duration_s = block["duration_sec"]
        
        # Determine the correct RPM curve based on spin type and actual duration
        if is_gentle:
            expected_max_rpm = 400
            if duration_s <= 300:
                milestones = [(15, 300), (35, 300), (155, 400), (240, 400)]
            elif duration_s <= 550:
                milestones = [(15, 300), (35, 300), (155, 400), (480, 400)]
            else:
                milestones = [(15, 300), (35, 300), (155, 400), (720, 400)]
        else:
            expected_max_rpm = 700
            if i == 0:
                # Balance Spin
                milestones = [(15, 300), (35, 300), (155, 600), (160, 600), (180, 700)]
            else:
                # Intermediate & Final Spins
                if duration_s <= 300:
                    milestones = [(15, 300), (35, 300), (155, 600), (160, 600), (180, 700), (240, 700)]
                elif duration_s <= 550:
                    milestones = [(15, 300), (35, 300), (155, 600), (160, 600), (180, 700), (480, 700)]
                else:
                    milestones = [(15, 300), (35, 300), (155, 600), (160, 600), (180, 700), (720, 700)]

        # --- 1. Spin Pause Validation ---
        spin_start_row = block["start"]
        search_idx = spin_start_row - 300 # skip immediate ramp up
        last_agitation_row = 0
        while search_idx >= 0:
            if rpm_lookup.get(search_idx, 0) > 50:
                last_agitation_row = search_idx
                break
            search_idx -= 1
            
        if last_agitation_row > 0:
            idle_duration_sec = (spin_start_row - last_agitation_row) * 0.1
            # We expect >= 150s pause. (Actually 150s + drain time, so 145s is a safe minimum)
            if idle_duration_sec >= 145.0:
                p_status = "PASS"
                p_sev = "Low"
                p_msg = f"Motor was idle for {idle_duration_sec:.1f}s before spin. (Required >= 150s)"
            else:
                p_status = "FAIL"
                p_sev = "Medium"
                p_msg = f"Motor was idle for only {idle_duration_sec:.1f}s before spin. (Required >= 150s)"
                
            defects.append({
                "Row_Index":          f"{last_agitation_row}-{spin_start_row}",
                "Test_Name":          f"{spin_name} - Pause Check",
                "Status":             p_status,
                "Severity":           p_sev,
                "Priority":           "Medium",
                "Expected_Sec":       ">= 150s",
                "Actual_Sec":         f"{idle_duration_sec:.1f}s",
                "Delta_Sec":          f"{idle_duration_sec - 150:.1f}s",
                "Technical_Evidence": p_msg
            })

        # --- 2. Spin Milestones Validation ---
        prev_m_sec = 0
        
        # Find the deceleration start row (drop_start_row) to exclude free-fall from average
        temp_drop_start = block["end"]
        while temp_drop_start > block["start"]:
            if rpm_lookup.get(temp_drop_start, 0) > (expected_max_rpm * 0.7):
                break
            temp_drop_start -= 1
            
        for m_sec, m_target_rpm in milestones:
            if block["duration_sec"] < (m_sec - 5.0):
                prev_m_sec = m_sec
                continue
            
            start_row = block["start"] + int(prev_m_sec * 10)
            end_row = block["start"] + int(m_sec * 10)
            
            # Cap the end_row to exclude the deceleration phase
            if end_row > temp_drop_start:
                end_row = temp_drop_start
                
            if start_row >= end_row:
                prev_m_sec = m_sec
                continue
                
            actual_rpms = [rpm_lookup[r] for r in range(start_row, end_row + 1) if r in rpm_lookup]
            
            if not actual_rpms:
                prev_m_sec = m_sec
                continue
                
            avg_rpm = sum(actual_rpms) / len(actual_rpms)
            delta_rpm = avg_rpm - m_target_rpm
            
            # Use ±20 tolerance for average
            if abs(delta_rpm) <= 20:
                status = "PASS"
                severity = "Low"
                msg = f"Interval [{prev_m_sec}s - {m_sec}s].\nTarget: {m_target_rpm} RPM.\nAverage Actual: {avg_rpm:.2f} RPM (Within tolerance)."
            else:
                status = "FAIL"
                severity = "High"
                msg = f"Interval [{prev_m_sec}s - {m_sec}s].\nTarget: {m_target_rpm} RPM.\nAverage Actual: {avg_rpm:.2f} RPM (Out of tolerance)."

            defects.append({
                "Row_Index":          f"{start_row}-{end_row}",
                "Test_Name":          f"{spin_name} - Interval {m_sec}s Check",
                "Status":             status,
                "Severity":           severity,
                "Priority":           "Medium",
                "Expected_Sec":       f"{m_target_rpm} RPM (avg)",
                "Actual_Sec":         f"{avg_rpm:.2f} RPM",
                "Delta_Sec":          f"{delta_rpm:.2f} RPM",
                "Technical_Evidence": msg
            })
            
            prev_m_sec = m_sec
            


    # Sort all defects chronologically based on the start row
    def get_start_row(defect):
        ri = str(defect.get("Row_Index", ""))
        if ri == "N/A" or not ri:
            return 0
        try:
            return int(ri.split("-")[0])
        except Exception:
            return 0

    defects.sort(key=get_start_row)

    # Return defects and empty phase_summary tuple since the original didn't use it but excel exporter does
    return defects, []
