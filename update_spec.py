"""
update_spec.py
Updates sharp_spec.json with new findings from screenshots analysis.
Run: python update_spec.py
"""
import json

with open('sharp_spec.json', 'r', encoding='utf-8') as f:
    spec = json.load(f)

# ── 1. BLOCK DIAGRAM (New complete hardware map) ──────────────────────────────
spec["hardware_io"] = {
    "inputs": {
        "Operation_Switches": "User buttons on panel",
        "Water_Pressure_Sensor": "Monitors water level frequency",
        "Temperature_Sensor": "CROSSED OUT - NOT USED in this model",
        "MEMS_Acceleration_Sensor": "Detects unbalance during spin",
        "Motor_Feedback": "BLDC motor feedback signal",
        "Lid_Switch": "Door open/close detection",
        "RPM_Sensor": "Separate sensor - measures motor RPM (Hall sensor output)"
    },
    "outputs": {
        "Display": "3-digit 7-segment + LEDs",
        "Cold_Water_Valve": "AI channel - relay 0/5V",
        "Softener_Water_Valve": "Exists in hardware! (not monitored in current setup)",
        "Hot_Water_Valve": "AI channel - relay 0/5V",
        "Clutch_Geared_Motor": "AI channel - relay 0/5V (separate from BLDC!)",
        "BLDC_Motor": "Controlled by inverter - RPM via external sensor",
        "Drain_Pump": "AI channel - relay 0/5V"
    },
    "note": "Temperature Sensor is crossed out = not present in this model. RPM Sensor is SEPARATE from Motor Feedback."
}

# ── 2. ERRORS - COMPLETE TABLE (from errors.png) ──────────────────────────────
spec["errors"] = [
    {"code": "E5",   "name": "Water Supply Failure",
     "detection": "Water supply not finished within 20 minutes",
     "buzzer": "Every 10 min for 10 sec",
     "release": "Open/close lid, check remedy, press START/PAUSE",
     "remedy": "Check inlet hose, tap, frozen pipe, valve filter, pressure",
     "daq_detectable": True, "daq_method": "Cold/Hot valve ON >20 min with no level change"},

    {"code": "E1",   "name": "Drain Failure",
     "detection": "Water level doesn't reach reset level within 15 minutes from drain start",
     "buzzer": "Every 10 min for 10 sec",
     "release": "Open/close lid, press START/PAUSE. If still error: water level calibration",
     "remedy": "Check drain hose frozen/blocked/height/immersed in water",
     "daq_detectable": True, "daq_method": "Pump ON >15 min (150s test limit)"},

    {"code": "E2",   "name": "Lid Opening Failure",
     "detection": "Lid opened during delay start, wash, rinse or spin processes",
     "buzzer": "Every 10 min for 10 sec",
     "release": "Close lid, machine operates automatically",
     "remedy": "Is the lid opened?",
     "daq_detectable": True, "daq_method": "Door signal = OPEN during WASH/RINSE/SPIN phase"},

    {"code": "E3-2", "name": "Unbalance Failure",
     "detection": "Clothes collected on one side during spin AND automatic correction failed 3 times",
     "buzzer": "Every 10 min for 10 sec",
     "release": "Open/close lid, check remedy, press START/PAUSE",
     "remedy": "Are clothes collected on one side? Is machine on uneven surface?",
     "daq_detectable": False, "daq_method": "Requires MEMS sensor data (not in current DAQ setup)"},

    {"code": "E6-1", "name": "Overflow Failure",
     "detection": "1) Continuous water supply failure reaches normal overflow level (pump ON only). 2) Water reaches dangerous level (pump ON, inlets closed). 3) Water remains at dangerous overflow for 5 min",
     "buzzer": "Every 10 min for 10 sec",
     "release": "Press Power off, close tap, drain manually. If still: water level calibration",
     "remedy": "Inlet valve defective, drain pump defective, water level sensor defective, PCB, pressure tube leakage",
     "daq_detectable": True, "daq_method": "Cold+Hot valve ON + Pump ON simultaneously = overflow attempt"},

    {"code": "E5-1", "name": "Abnormal Water Level Sensor Reading",
     "detection": "Detected water level frequency out of normal range",
     "buzzer": "Every 10 min for 10 sec",
     "release": "Press Power off, check remedy",
     "remedy": "Water level sensor defective, PCB defective",
     "daq_detectable": False, "daq_method": "Requires frequency measurement of water level sensor"},

    {"code": "E7-1", "name": "Motor CW Rotation Failure",
     "detection": "Motor is short or open circuit in CW direction during wash",
     "buzzer": "Every 10 min for 10 sec",
     "release": "Press Power off, check remedy",
     "remedy": "PCB or motor defective",
     "daq_detectable": True, "daq_method": "Motor signal = 0 during expected CW wash phase"},

    {"code": "E7-2", "name": "Motor CCW Rotation Failure",
     "detection": "Motor is short or open circuit in CCW direction during wash",
     "buzzer": "Every 10 min for 10 sec",
     "release": "Press Power off, check remedy",
     "remedy": "PCB or motor defective",
     "daq_detectable": True, "daq_method": "Motor signal = 0 during expected CCW wash phase"},

    {"code": "E7-3", "name": "Motor Spin Rotation Failure",
     "detection": "Motor is short or open circuit in CW direction during spin",
     "buzzer": "Every 10 min for 10 sec",
     "release": "Press Power off, check remedy",
     "remedy": "PCB or motor defective",
     "daq_detectable": True, "daq_method": "Motor signal = 0 during SPIN phase"},

    {"code": "E7-4", "name": "Motor CW/CCW Rotation Failure",
     "detection": "Motor is short or open circuit in BOTH CW & CCW direction during wash",
     "buzzer": "Every 10 min for 10 sec",
     "release": "Press Power off, check remedy",
     "remedy": "PCB or motor defective",
     "daq_detectable": True, "daq_method": "Motor signal = 0 during entire WASH phase"},

    {"code": "E9",   "name": "Abnormal Water Leakage Failure",
     "detection": "During wash (NOT filling), there is no water in the tub",
     "buzzer": "Every 10 min for 10 sec",
     "release": "Press Power off, check remedy",
     "remedy": "Check tub for cracks, PCB defective",
     "daq_detectable": False, "daq_method": "Requires water level sensor (frequency) - not in current DAQ"},

    {"code": "E3",   "name": "MEMS Failure",
     "detection": "MEMS sensor not working due to defect or wrong assembly",
     "buzzer": "Every 10 min for 10 sec",
     "release": "Press Power off, check remedy",
     "remedy": "MEMS sensor defective",
     "daq_detectable": False, "daq_method": "Requires MEMS data"},

    {"code": "Eb-1", "name": "General Motor Failure",
     "detection": "During machine startup, motor is still rotating and doesn't stop within 1 minute",
     "buzzer": "Every 10 min for 10 sec",
     "release": "Press Power off, check remedy",
     "remedy": "PCB defective, motor defective",
     "daq_detectable": True, "daq_method": "Motor signal = 5V during IDLE/startup phase"},

    {"code": "EA",   "name": "Abnormal Water When Dry Failure",
     "detection": "During spin, water is in tub when it shouldn't be. Machine tries 5 correction attempts then shows error",
     "buzzer": "Every 10 min for 10 sec",
     "release": "Press Power off. If still: water level calibration",
     "remedy": "Water inlet defective, drain blocked/too high, pressure tube loose, water level sensor, PCB",
     "daq_detectable": True, "daq_method": "Pump activates repeatedly during SPIN phase (should not happen)"},

    {"code": "LP",   "name": "Low Power Failure",
     "detection": "Voltage level drops below 160V for 5 minutes",
     "buzzer": "Every 10 min for 10 sec",
     "release": "Press Power off, check remedy",
     "remedy": "Is the voltage level OK in the household?",
     "daq_detectable": False, "daq_method": "Requires voltage monitoring (not in current DAQ setup)"}
]

# ── 3. SPIN CONTROL - COMPLETE WITH ALL DURATIONS ─────────────────────────────
spec["spin_control"] = {
    "standard_courses": {
        "programs": ["Regular", "Heavy", "Cotton", "Baby Care", "Jeans", "Quick Rinse", "Blanket"],
        "rpm_curve_all_durations": {
            "1_min": [
                {"time_sec": 0,   "rpm": 0},
                {"time_sec": 15,  "rpm": 300},
                {"time_sec": 35,  "rpm": 300},
                {"time_sec": 155, "rpm": 600},
                {"time_sec": 160, "rpm": 600},
                {"time_sec": 180, "rpm": 700},
                {"time_sec": 240, "rpm": 700}
            ],
            "5_min": [
                {"time_sec": 0,   "rpm": 0},
                {"time_sec": 15,  "rpm": 300},
                {"time_sec": 35,  "rpm": 300},
                {"time_sec": 155, "rpm": 600},
                {"time_sec": 160, "rpm": 600},
                {"time_sec": 180, "rpm": 700},
                {"time_sec": 480, "rpm": 700}
            ],
            "9_min": [
                {"time_sec": 0,   "rpm": 0},
                {"time_sec": 15,  "rpm": 300},
                {"time_sec": 35,  "rpm": 300},
                {"time_sec": 155, "rpm": 600},
                {"time_sec": 160, "rpm": 600},
                {"time_sec": 180, "rpm": 700},
                {"time_sec": 720, "rpm": 700}
            ]
        },
        "max_rpm": 700
    },
    "gentle_courses": {
        "programs": ["Delicates", "Wool", "Sports Wear"],
        "max_rpm": 400,
        "rpm_curve": [
            {"time_sec": 0,   "rpm": 0},
            {"time_sec": 15,  "rpm": 300},
            {"time_sec": 35,  "rpm": 300},
            {"time_sec": 155, "rpm": 400},
            {"time_sec": 240, "rpm": 400}
        ]
    },
    "spin_pause_at_reset_level_sec": 150,
    "spin_end": "No braking - free fall after reaching spin end time",
    "clutch_change_after_stop": "After RPM sensor stop signal, shift 20 seconds",
    "pause_behavior": "If user pauses during spin twice, must restart from Balance Spin period",
    "source": "Spin Control Specs sheet + spin control specs.png"
}

# ── 4. TABLE 3 - SETTINGS DURING OPERATION ───────────────────────────────────
spec["operation_settings"] = {
    "changeable_during_run": {
        "Water_Level": {"allowed": False, "note": "Allowed during wash or rinse - requires Pause"},
        "Water_Temp": {"allowed": False, "note": "Allowed during wash only. Rinse always cold. Requires Pause"},
        "Wash_Time": {"allowed": False, "note": "Allowed during wash only - requires Pause"},
        "Rinse_Times": {"allowed": False, "note": "Allowed during wash and rinse - requires Pause"},
        "Spin_Times": {"allowed": False, "note": "Allowed during Wash, Rinse & Spin - requires Pause"},
        "Program": {"allowed": False, "note": "INVALID - cannot change after START"},
        "Delay_Start": {"allowed": False, "note": "INVALID - cannot change after START"},
        "Child_Lock": {"allowed": True, "note": "Allowed during any time - Execution/pause state"},
        "Anti_Wrinkle": {"allowed": False, "note": "Allowed during rinse or wash only. Once entering spin, cannot change. Requires Pause"},
        "Soak": {"allowed": False, "note": "Allowed only during wash - requires Pause"}
    },
    "buzzer_tones": {
        "Pause": "APP_BUZZER_PROGRAM_PAUSE_TONE",
        "ReStart": "APP_BUZZER_START_UP_TONE",
        "Invalid": "APP_BUZZER_KEY_INVALID_PRESS_TONE",
        "Program_Switch": "APP_BUZZER_KEY_VALID_PRESS_TONE"
    },
    "source": "Table3.png"
}

# ── 5. UNBALANCE PROTOCOL - DETAILED ─────────────────────────────────────────
spec["unbalance_protocol"] = {
    "error_code": "E3-2",
    "trigger": "After 3 failed spin attempts with automatic correction",
    "correction_sequence": [
        "Water Supply",
        "Stirring (motor CW/CCW)",
        "Drain Water",
        "Re-attempt Spin"
    ],
    "max_correction_attempts": 3,
    "final_spin_trigger": "E3 after 3 failed final spin attempts",
    "super_spin_protocol": {
        "note": "Only SUPER SPIN DRY starts process from *1 at the setting",
        "unbalance_stir_ON_sec": 0.3,
        "unbalance_stir_OFF_sec": 1.2,
        "stir_timeout_sec": 10
    },
    "source": "Unbalance protocol.png"
}

# ── 6. TUB CLEAN - COMPLETE SPECS ─────────────────────────────────────────────
spec["tub_clean"] = {
    "water_supply_and_stirring": {
        "step1": {"water_liters": 28, "motor_CW_sec": 3.4, "stop_sec": 4.6, "motor_CCW_sec": 3.4, "stop2_sec": 4.6, "total_stir_sec": 120},
        "step2": {"water_liters": 50, "stirring": "Same as first stirring"},
        "step3": {"water_liters": 71, "stirring": "Same as first stirring"},
        "step4": {"water_liters": 93, "stirring": "Same as first stirring"}
    },
    "soak": {
        "water_level": "4th (93L)",
        "motor_CW_sec": 1.5, "stop1_sec": 1.0,
        "motor_CCW_sec": 1.5, "stop2_sec": 1.0,
        "total_min": 20,
        "pattern": "Stir 1 minute then stop 4 minutes - repeated within 20 min"
    },
    "wash": {
        "motor_CW_sec": 1.5, "stop1_sec": 1.0,
        "motor_CCW_sec": 1.5, "stop2_sec": 1.0,
        "total_min": 180
    },
    "spin_sequence": {
        "1st_spin": {"top_rpm": 70, "ramp_rpm_per_sec": 10, "after_stop": "shift to next process (MAX 30s)", "then": "Drain Water → reset water level"},
        "2nd_spin": {"top_rpm": 700, "ON_sec": 100, "after_stop": "shift to next process (MAX 30)"},
        "water_stir_wash": {"note": "Same as water supply with stirring specs"},
        "wash_phase": {"motor_CW_sec": 1.5, "motor_CCW_sec": 1.5, "total_sec": 3},
        "3rd_spin": {"top_rpm": 70, "ramp_rpm_per_sec": 10, "after_stop": "shift next (MAX 30)"},
        "4th_spin": {"note": "Drain valve open", "top_rpm": 700, "ON_sec": 100, "after_stop": "shift next (MAX 30)"}
    },
    "rules": [
        "No supply water is added during wash",
        "Reservations (Delay Start) cannot be set",
        "Abnormality detection same as regular course operation"
    ],
    "source": "Tub clean.png + Tub clean part 2.png"
}

# ── 7. COURSE OPTION - DETAILED PER PROGRAM ──────────────────────────────────
spec["course_option_detail"] = {
    "Quick_Rinse": {
        "wash_time": "0 (NO WASH - rinse only!)",
        "rinse_times_default": 1,
        "spin_time_default": "5 min",
        "water_temp": "Cold only",
        "water_level": "All levels available",
        "soak": "NOT available",
        "weight_detection": True,
        "anti_wrinkle": True
    },
    "Tub_Clean": {
        "wash_time": "NOT selectable (fixed)",
        "rinse_times": "NOT selectable",
        "spin_time": "NOT selectable",
        "water_level": "NOT selectable (fixed LEV-4)",
        "water_temp": "NOT selectable",
        "soak": "NOT available",
        "weight_detection": False,
        "anti_wrinkle": False,
        "delay_start": True
    },
    "Quick": {
        "wash_time_default": "3 min",
        "rinse_times_default": 1,
        "spin_time_default": "1 min",
        "water_temp_default": "Cold",
        "soak": "NOT available",
        "weight_detection": True
    },
    "Delicates": {
        "water_temp_default": "Cold",
        "wash_time_default": "9 min",
        "rinse_times_default": 2,
        "spin_time_default": "5 min",
        "weight_detection": False,
        "note": "Wool type motion, gentle wash"
    },
    "Wool": {
        "water_temp_default": "Cold",
        "wash_time_default": "9 min",
        "rinse_times_default": 1,
        "spin_time_default": "1 min",
        "weight_detection": False
    },
    "Sports_Wear": {
        "wash_time_default": "9 min",
        "rinse_times_default": 1,
        "spin_time_default": "5 min",
        "weight_detection": True,
        "water_temp": "Warm default"
    },
    "source": "Course Option.png"
}

# ── 8. WD DISPLAY BEHAVIOR ────────────────────────────────────────────────────
spec["weight_detection_display"] = {
    "before_WD": "7-segment shows approximate program duration",
    "during_WD": {
        "water_level_LEDs": "Animation pattern: bottom to top then top to bottom, repeat. One full cycle = 1.5 SEC. Each LED fades in/out as next begins.",
        "seven_segment": "Shows dashes: - - - -",
        "program_LEDs": "Not affected",
        "function_LEDs": "Not affected"
    },
    "after_WD": {
        "water_level_LEDs": "Detected water level LED lights ON",
        "seven_segment": "Shows program duration for 3 seconds then starts counting down"
    },
    "source": "WD.png"
}

# ── 9. RINSE PROCESS TYPES ────────────────────────────────────────────────────
spec["rinse_process"] = {
    "types": {
        "Static_Rinse_W": "Wide rinse - used as last rinse always",
        "Static_Rinse_S": "Short rinse - used for intermediate rinses"
    },
    "by_rinse_count": {
        "1_time": ["Static_Rinse_W"],
        "2_times": ["Static_Rinse_S", "Static_Rinse_W"],
        "3_times": ["Static_Rinse_S", "Static_Rinse_S", "Static_Rinse_W"]
    },
    "water_temp": "Cold only - ALWAYS",
    "water_level": "4th level if not manually selected",
    "spin_pause_at_reset_level_sec": 150,
    "after_spin_shift_next_process_sec": 20,
    "source": "Rinse.png"
}

# ── 10. DIFFERENCES - COMPLETE ────────────────────────────────────────────────
spec["differences_summary"] = {
    "BLDC_vs_AC": {
        "programs_count": {"AC": 10, "BLDC": 12},
        "extra_in_BLDC": ["Quick Rinse", "Sports Wear"],
        "display_digits": {"AC": 4, "BLDC": 3},
        "balance_spin": {"AC": "ON/OFF", "BLDC": "Spin Curve"}
    },
    "Tornado_vs_Sharp": {
        "programs_count": {"Tornado": 9, "Sharp": 12},
        "Tornado_has_not_in_Sharp": ["Rapid (Sharp has Quick instead)", "Stain LVL", "Extra Spin"],
        "Sharp_extra": ["Quick Rinse", "Sports Wear"],
        "note": "In Tornado, Tub Clean is an option not a program"
    },
    "11kg_vs_13kg": {
        "only_difference": "Water amount at LEV-4 before M2 motion",
        "Sharp_VE_BLDC_11kg": "90 Liters",
        "Sharp_VE_BLDC_13kg": "93 Liters"
    },
    "source": "Differences Summary.png"
}

# ── 11. SEQUENCE - Quick Rinse correction ─────────────────────────────────────
spec["quick_rinse_special"] = {
    "wash_time": 0,
    "note": "Quick Rinse has NO wash phase at all - goes directly to rinse",
    "rinse_count_default": 1,
    "total_time_min": {"LEV-1": 24, "LEV-2": 25, "LEV-3": 26, "LEV-4": 27},
    "source": "Sequence Chart2.png"
}

# ── 12. LAYOUT CONFIRMED ──────────────────────────────────────────────────────
spec["ui_layout"] = {
    "brand": "SHARP CORPORATION, JAPAN",
    "technology": "J-TECH INVERTER",
    "features": ["SUPERHEX DRUM", "COOL JET"],
    "programs_count": 12,
    "programs_order": ["Regular", "Quick", "Heavy", "Baby Care", "Cotton",
                       "Delicates", "Wool", "Quick Rinse", "Jeans", "Blanket",
                       "Tub Clean", "Sports Wear"],
    "options": ["Anti-Wrinkle", "Delay Start", "Soak", "Child Lock"],
    "manual_selections": {
        "Water_Temp": ["Cold", "Warm", "Hot"],
        "Wash_Time": ["3 min", "9 min", "12 min", "18 min"],
        "Rinse_Times": ["1 time", "2 times", "3 times"],
        "Spin_Time": ["1 min", "5 min", "9 min", "Super Spin (20 min)"],
        "Water_Level": ["LEV-1", "LEV-2", "LEV-3", "LEV-4"]
    },
    "display": "3-digit 7-segment (Hrs, Mins, Times)",
    "source": "Layout.png"
}

# Save updated spec
with open('sharp_spec.json', 'w', encoding='utf-8') as f:
    json.dump(spec, f, indent=2, ensure_ascii=False, default=str)

print("sharp_spec.json updated successfully!")
print(f"Total sections: {len(spec)}")
print(f"Total errors: {len(spec['errors'])}")
print("New sections added:", [
    'hardware_io', 'operation_settings', 'unbalance_protocol',
    'tub_clean', 'course_option_detail', 'weight_detection_display',
    'rinse_process', 'quick_rinse_special'
])
