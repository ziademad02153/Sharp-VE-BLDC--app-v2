import sys

with open('agitation_analyzer.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
skip = False

for i, line in enumerate(lines):
    if line.strip() == "# ── 6. WASH Total Duration ────────────────────────────────────────────────":
        skip = True
        
        # Insert our new chronological logic
        new_lines.append("""        else:
            defects.append({
                "Row_Index":          f"{first_fill_row}-{actual_end}",
                "Test_Name":          "Phase Tracking: Initial Water Fill",
                "Status":             "PASS",
                "Severity":           "Low",
                "Priority":           "Low",
                "Expected_Sec":       f"Max {FILL_TIMEOUT_SEC}s",
                "Actual_Sec":         f"{fill_sec}s",
                "Technical_Evidence": f"Initial Water Fill completed successfully.\\nDuration: {fill_sec}s."
            })

    # ── 6. Chronological Wash Phase Tracking (M2 -> M3 -> M4 -> MU) ───────────
    # Filter strokes to ONLY include those AFTER the initial fill
    valid_strokes = [s for s in calibrated if fill_end_row is None or s["start_row"] > fill_end_row]

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
    
    for s in valid_strokes:
        if last_spin_row > 0 and s["start_row"] > last_spin_row:
            if s["elec_on"] >= 0.3:
                aw.append(s)
            continue

        if s["elec_on"] > 10.0:
            continue
            
        if s["start_row"] > drain_ref:
            if s["elec_on"] <= 0.6:
                mu.append(s)
                if not mu_start: mu_start = s["start_row"]
                mu_end = s["end_row"]
            continue
            
        # Accumulate active wash time
        active_wash_time += s["elec_on"]
        off_time = s.get("elec_off", 0.0)
        if off_time is not None and off_time <= 5.0:
            active_wash_time += off_time
            
        # Classify based on active wash time
        if active_wash_time <= 60.0:
            m2.append(s)
            if not m2_start: m2_start = s["start_row"]
            m2_end = s["end_row"]
        elif active_wash_time <= 240.0:
            m3.append(s)
            if not m3_start: m3_start = s["start_row"]
            m3_end = s["end_row"]
        elif expected_wash_sec and active_wash_time <= (240.0 + expected_wash_sec):
            m4.append(s)
            if not m4_start: m4_start = s["start_row"]
            m4_end = s["end_row"]
        else:
            mu.append(s)
            if not mu_start: mu_start = s["start_row"]
            mu_end = s["end_row"]

    # Helper for appending Phase Tracking PASS records
    def append_phase_tracking(name, start, end, expected_sec):
        if not start or not end: return
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
            "Technical_Evidence": f"Phase {name} successfully identified.\\nStart Row: {start}\\nEnd Row: {end}\\nClock Duration: {dur_sec}s."
        })

    # Append Phase Tracking
    append_phase_tracking("M2", m2_start, m2_end, "60s (Active)")
    append_phase_tracking("M3", m3_start, m3_end, "180s (Active)")
    append_phase_tracking("M4", m4_start, m4_end, f"{expected_wash_sec}s (Active)" if expected_wash_sec else "N/A")
    if mu_start: append_phase_tracking("MU", mu_start, mu_end, "N/A")

    # Check for Water Refills between phases
    def track_water_refills_between(name, start_limit, end_limit):
        if not start_limit or not end_limit: return
        in_refill = False
        refill_start = 0
        valves_active = []
        
        for r in raw_data_log:
            row_idx = r[0]
            if row_idx <= start_limit: continue
            if row_idx >= end_limit: break
            
            cold_on = (r[3] > 4.0)
            hot_on = (r[4] > 4.0)
            
            if cold_on or hot_on:
                if not in_refill:
                    in_refill = True
                    refill_start = row_idx
                    valves_active = []
                if cold_on and "Cold" not in valves_active: valves_active.append("Cold")
                if hot_on and "Hot" not in valves_active: valves_active.append("Hot")
            else:
                if in_refill:
                    in_refill = False
                    dur_sec = round((row_idx - refill_start) * 0.1, 1)
                    if dur_sec > 2.0: # Only log significant refills > 2s
                        valve_names = " + ".join(valves_active)
                        defects.append({
                            "Row_Index":          f"{refill_start}-{row_idx}",
                            "Test_Name":          f"Phase Tracking: Water Refill (After {name})",
                            "Status":             "PASS",
                            "Severity":           "Low",
                            "Priority":           "Low",
                            "Expected_Sec":       "N/A",
                            "Actual_Sec":         f"{dur_sec}s",
                            "Technical_Evidence": f"Water Refill ({valve_names} Valve) occurred after {name}."
                        })

    if m2_end and m3_start: track_water_refills_between("M2", m2_end, m3_start)
    if m3_end and m4_start: track_water_refills_between("M3", m3_end, m4_start)

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
                    f"DEAD MOTOR: No {phase_name} strokes detected during expected phase window.\\n"
                    f"Expected: Motor must agitate per spec (ON: {expected_specs[0]}s / OFF: {expected_specs[1]}s)\\n"
                    f"Source: Sharp HIL Specification (Course: {program_name}, Level: LEV-{level_key}, Phase: {phase_name})"
                )
            })
            return result

        exp_on, exp_off = expected_specs

        for idx, s in enumerate(movement_strokes):
            stroke_num = idx + 1

            actual_on = s["elec_on"]
            actual_off = s.get("elec_off")
            
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
                        f"Number of rows: ({s['end_row']} - {s['start_row']} + 1) = {on_rows} rows\\n"
                        f"Time in seconds: {on_rows} * 0.1 = {actual_on}s\\n"
                        f"Expected ON: {exp_on}s\\n"
                        f"Delta: {actual_on} - {exp_on} = {on_delta:+.2f}s ({direction})"
                    )
                })

            # ── OFF Time check ──
            actual_off = s.get("elec_off")
            if actual_off is not None and actual_off < 15.0:
                off_delta = round(actual_off - exp_off, 2)

                if not cycle_pass and abs(off_delta) > TOLERANCE:
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
                            f"Number of rows: ({ns} - {s['end_row']} - 1) = {off_rows} rows\\n"
                            f"Time in seconds: {off_rows} × 0.1 = {actual_off}s\\n"
                            f"Expected OFF: {exp_off}s\\n"
                            f"Delta: {actual_off} - {exp_off} = {off_delta:+.2f}s ({direction})"
                        )
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
        
        m4_active_time = sum(s["elec_on"] + (s.get("elec_off", 0.0) if s.get("elec_off", 0.0) <= 5.0 else 0.0) for s in m4)
        
        delta = round(m4_active_time - expected_wash_sec, 1)
        
        if abs(delta) > TOLERANCE_WASH:
            direction = "Overrun" if delta > 0 else "Deficit"
            defects.append({
                "Row_Index":          f"{first_m4}-{last_m4}",
                "Test_Name":          "WASH Total Duration Validation",
                "Status":             "FAIL",
                "Severity":           "High",
                "Priority":           "Medium",
                "Expected_Sec":       f"{expected_wash_sec}s (Active)",
                "Actual_Sec":         f"{round(m4_active_time, 1)}s (Active)",
                "Technical_Evidence": (
                    f"M4 Wash Phase from row {first_m4} to {last_m4}.\\n"
                    f"Clock Duration: {m4_clock_sec}s\\n"
                    f"Active Wash Time: {round(m4_active_time, 1)}s\\n"
                    f"Expected Active Time: {expected_wash_sec}s\\n"
                    f"Delta: {delta:+.1f}s ({direction})"
                )
            })
\n""")

    elif line.strip() == "# ── 9. Spin Profile Validation ─────────────────────────────────────────────":
        skip = False
        new_lines.append(line)
        
    elif not skip:
        new_lines.append(line)

with open('agitation_analyzer.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
