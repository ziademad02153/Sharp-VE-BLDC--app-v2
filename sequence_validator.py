import json
from PyQt5.QtCore import QObject, pyqtSignal

class SequenceValidator(QObject):
    validation_status = pyqtSignal(dict) # To update UI (expected phase, time left, pass/fail)

    def __init__(self, log_callback, record_callback):
        super().__init__()
        self.log_callback = log_callback
        self.record_callback = record_callback
        
        self.spec = {}
        self.sequence_chart = {}
        self.course_options = {}
        self._load_config()

        self.current_program = None
        self.current_level = None
        
        # Validation State
        self.expected_phases = []
        self.current_step_index = 0
        self.time_in_current_phase = 0
        self.last_phase = 'IDLE'
        self.is_failed = False
        
        self.TOLERANCE_SEC = 2.0 # Strict 2.0-second tolerance for Wash, Pump, Fill, and Drain phases

    def _load_config(self):
        try:
            with open('sharp_spec.json', 'r', encoding='utf-8') as f:
                self.spec = json.load(f)
                self.sequence_chart = self.spec.get("sequence_chart", {})
                self.course_options = self.spec.get("course_option_detail", {})
                self.log_callback(f"SequenceValidator: Loaded Sharp specification logic.")
        except Exception as e:
            self.log_callback(f"SequenceValidator Load Error: {e}")

    def set_program(self, program_name, level, soak_option="No Soak", delay_option="None", wash_override="Default", rinse_override="Default", spin_override="Default"):
        """Builds a linear list of expected phases based on Sharp specifications"""
        self.current_program = program_name
        self.current_level = level
        self.wash_override = wash_override
        self.rinse_override = rinse_override
        self.spin_override = spin_override
        self.expected_phases = []
        self.current_step_index = 0
        self.time_in_current_phase = 0
        self.last_phase = 'IDLE'
        self.is_failed = False
        
        # Normalize program name for mapping
        prog_key = program_name.replace(" ", "_")
        
        # --- DEEP TRUTH LOGIC (From Course Option & Weight Specs) ---
        # 1. Level Locking: Blanket and Tub Clean are FIXED at LEV-4
        if program_name in ["Blanket", "Tub Clean"]:
            level = "LEV-4"
            self.log_callback(f"ℹ️ LOGIC SYNC: '{program_name}' is fixed at LEV-4 per Sharp specs.")

        if program_name not in self.sequence_chart or level not in self.sequence_chart[program_name]:
            self.log_callback(f"SequenceValidator: Program '{program_name}' Level '{level}' not found in spec!")
            return

        times = self.sequence_chart[program_name][level]
        
        # 1. Weight Detection (Happens physically first: brief motor spin right after START)
        # Cancelled for: Delicates, Wool, Blanket, Tub Clean
        no_wd_courses = ["Delicates", "Wool", "Blanket", "Tub Clean"]
        if program_name not in no_wd_courses:
            self.expected_phases.append({"name": "WEIGHT_DETECT", "duration_sec": 7.2, "type": "strict"})

        # 2. Delay Start Option (After weight detection, machine sleeps for the delay period)
        if delay_option != "None":
            try:
                delay_hours = int(delay_option.split(" ")[0])
                delay_sec = delay_hours * 3600
                self.expected_phases.append({"name": "DELAY_START", "duration_sec": delay_sec, "type": "max_limit"})
            except ValueError:
                pass

        # 3. Soak Option (User-selected soak time as max limit ceiling)
        # Soak is a composite phase (Pause + Rotating cycles). Machine must complete within selected time.
        if soak_option == "1 Hour":
            self.expected_phases.append({"name": "SOAK", "duration_sec": 3600, "type": "max_limit"})
        elif soak_option == "2 Hours":
            self.expected_phases.append({"name": "SOAK", "duration_sec": 7200, "type": "max_limit"})
        elif soak_option == "4 Hours":
            self.expected_phases.append({"name": "SOAK", "duration_sec": 14400, "type": "max_limit"})

        # Apply Overrides
        if hasattr(self, 'wash_override') and self.wash_override != "Default":
            try:
                times["main_wash_sec"] = float(self.wash_override.split(" ")[0]) * 60
            except:
                pass
        if hasattr(self, 'rinse_override') and self.rinse_override != "Default":
            try:
                times["rinse_count"] = int(self.rinse_override.split(" ")[0])
            except:
                pass
        if hasattr(self, 'spin_override') and self.spin_override != "Default":
            try:
                times["final_spin_sec"] = float(self.spin_override.split(" ")[0]) * 60
            except:
                pass

        # 3. Main Wash
        main_wash_sec = times.get("main_wash_sec", 0)
        if main_wash_sec is not None and main_wash_sec > 0:
            # Note: Top-up fills (M2, M3) are allowed within this duration
            self.expected_phases.append({"name": "WATER_FILL", "duration_sec": times.get("water_fill_sec", 180), "type": "max_limit"})
            self.expected_phases.append({"name": "WASH", "duration_sec": main_wash_sec, "type": "min_limit"})

        # 4. Rinses
        rinse_count = times.get("rinse_count", 0)
        drain_sec = times.get("drain_sec", 120)
        balance_sec = times.get("balance_spin_sec", 180)
        inertia_sec = 60 
        
        if rinse_count is not None:
            for i in range(1, rinse_count + 1):
                self.expected_phases.append({"name": "DRAIN", "duration_sec": drain_sec, "type": "max_limit"})
                self.expected_phases.append({"name": "SPIN_PAUSE", "duration_sec": 150, "type": "strict"})
                
                # Gentle courses (max 400 RPM) and Quick have shorter medium spin per Spin Control Specs
                gentle_courses = ["Quick", "Quick Rinse", "Delicates", "Wool", "Sports Wear"]
                medium_spin = 40 if program_name in gentle_courses else 120
                total_spin_dur = balance_sec + medium_spin + inertia_sec
                self.expected_phases.append({"name": "SPIN", "duration_sec": total_spin_dur, "type": "strict"})
                self.expected_phases.append({"name": "WATER_FILL", "duration_sec": times.get("water_fill_sec", 180), "type": "max_limit"})
                self.expected_phases.append({"name": f"RINSE_{i}", "duration_sec": times.get("rinse_wash_sec", 240), "type": "strict"})

        # 5. Final Spin
        final_spin_val = times.get("final_spin_sec", 0)
        if final_spin_val is not None and final_spin_val > 0:
            self.expected_phases.append({"name": "DRAIN", "duration_sec": drain_sec, "type": "max_limit"})
            self.expected_phases.append({"name": "SPIN_PAUSE", "duration_sec": 150, "type": "strict"})
            total_final_spin = balance_sec + final_spin_val + inertia_sec
            self.expected_phases.append({"name": "SPIN", "duration_sec": total_final_spin, "type": "strict"})

        # 6. Anti-Wrinkle Exceptions
        # Cancelled for: Quick, Delicates, Wool, Tub Clean
        no_aw_courses = ["Quick", "Delicates", "Sports Wear", "Tub Clean"]
        if final_spin_val > 0 and program_name not in no_aw_courses:
            self.expected_phases.append({"name": "ANTI_WRINKLE", "duration_sec": 120, "type": "max_limit"})

        total_dur = sum(p["duration_sec"] for p in self.expected_phases)
        m, s = divmod(int(total_dur), 60)
        self.log_callback(f"✅ SequenceValidator: '{program_name}' {level} Deep Sync Complete. Total: {m}m {s}s. Steps: {len(self.expected_phases)}")
        self._emit_status()
        
    def sync_to_machine_phase(self, actual_phase):
        """Forces the validator to jump to a specific phase if machine state changes"""
        if self.is_failed or not self.expected_phases:
            return
            
        # Don't sync to IDLE
        if actual_phase == 'IDLE':
            return
            
        # Precision Sync Guard: Do not force-jump if it's the normal expected *next* sequential phase
        if self.current_step_index + 1 < len(self.expected_phases):
            next_name = self.expected_phases[self.current_step_index + 1]["name"]
            if (actual_phase == next_name) or (actual_phase == 'RINSE' and next_name.startswith('RINSE')):
                # Let evaluate_state handle the normal sequential transition and pass/fail recording
                return
            
        # Search for the phase in the future steps
        for i in range(self.current_step_index, len(self.expected_phases)):
            # Handle Rinse generic mapping (RINSE matches RINSE_1, RINSE_2 etc)
            target = self.expected_phases[i]["name"]
            match = (actual_phase == target) or (actual_phase == 'RINSE' and target.startswith('RINSE'))
            
            if match:
                if i != self.current_step_index:
                    missed = [p["name"] for p in self.expected_phases[self.current_step_index:i]]
                    self.log_callback(f"🔄 SYNC: Jumping to {target} (Skipped: {missed})")
                    self.current_step_index = i
                    self.time_in_current_phase = 0
                    self.TOLERANCE_SEC = 60 # Extra tolerance for manual entry
                    self._emit_status()
                return


    def evaluate_state(self, actual_phase, row_index):
        if not self.expected_phases or self.current_step_index >= len(self.expected_phases):
            return

        expected_step = self.expected_phases[self.current_step_index]
        expected_phase_name = expected_step["name"]

        # --- PHASE SYNCHRONIZATION (The "Precision Sync" Guard) ---
        # Only jump if the machine is CLEARLY in a future phase and NOT in the current one.
        is_next_expected = False
        if self.current_step_index + 1 < len(self.expected_phases):
            next_name = self.expected_phases[self.current_step_index + 1]["name"]
            if (actual_phase == next_name) or (actual_phase == 'RINSE' and next_name.startswith('RINSE')):
                if self.last_phase == expected_phase_name:
                    is_next_expected = True

        if actual_phase != expected_phase_name and actual_phase != 'IDLE' and not is_next_expected:
            # Prevent jumping out of SOAK due to normal soak agitations (water fill or short washes)
            if expected_phase_name == "SOAK" and actual_phase in ["WATER_FILL", "WASH"]:
                pass
            else:
                for i in range(self.current_step_index + 1, len(self.expected_phases)):
                    if actual_phase == self.expected_phases[i]["name"]:
                        # If we wake up from Delay Start, explicitly record its actual duration
                        if expected_phase_name == "DELAY_START":
                            delay_time_sec = self.time_in_current_phase / 10.0
                            self._record_pass(expected_phase_name, expected_step["duration_sec"], delay_time_sec, f"{self.phase_start_row}-{row_index}")
                            
                        missed = [p["name"] for p in self.expected_phases[self.current_step_index:i] if p["name"] != "DELAY_START"]
                        if missed:
                            self.log_callback(f"ℹ️ AUTO-SYNC: Machine phase detected -> {actual_phase} (Skipped: {missed})")
                        else:
                            self.log_callback(f"ℹ️ WAKE-UP: Machine started {actual_phase} after Delay.")
                            
                        self.current_step_index = i
                        self.time_in_current_phase = 0
                        self.phase_start_row = row_index
                        # Add extra tolerance for manual phase entry
                        self.TOLERANCE_SEC = 60 
                        expected_step = self.expected_phases[self.current_step_index]
                        expected_phase_name = expected_step["name"]
                        break
        
        # Tracking Time (1 tick = 100ms)
        is_soak_state = expected_phase_name == "SOAK" and actual_phase in ["IDLE", "WATER_FILL", "WASH"]
        is_delay_state = expected_phase_name == "DELAY_START" and actual_phase == "IDLE"
        
        if actual_phase == expected_phase_name or is_soak_state or is_delay_state:
            if self.time_in_current_phase == 0 or getattr(self, 'phase_start_row', None) is None:
                self.phase_start_row = row_index
            self.time_in_current_phase += 1
            
        time_sec = self.time_in_current_phase / 10.0
        
        # Advance SOAK phase purely by time since it's a composite phase
        if is_soak_state:
            target_time = expected_step["duration_sec"]
            if time_sec >= target_time:
                self._record_pass(expected_phase_name, target_time, time_sec, f"{self.phase_start_row}-{row_index}")
                self.current_step_index += 1
                self.time_in_current_phase = 0
                self.phase_start_row = None
                self.TOLERANCE_SEC = 2.0
                self.last_phase = actual_phase
                self._emit_status()
                return

        # Phase Transition Logic
        if actual_phase != self.last_phase:
            if self.last_phase == expected_phase_name:
                target_time = expected_step["duration_sec"]
                
                if expected_phase_name == "SPIN":
                    # Spin duration validation is handled by agitation_analyzer (milestone checks)
                    self._record_pass(expected_phase_name, target_time, time_sec, f"{self.phase_start_row}-{row_index}")
                elif expected_step["type"] == "strict" and abs(time_sec - target_time) > self.TOLERANCE_SEC:
                    self._trigger_fail(f"Phase '{expected_phase_name}' took {time_sec:.1f}s, expected {target_time}s", target_time, time_sec, f"{self.phase_start_row}-{row_index}")
                elif expected_step["type"] == "max_limit" and time_sec > target_time + self.TOLERANCE_SEC:
                    self._trigger_fail(f"Phase '{expected_phase_name}' took {time_sec:.1f}s, max {target_time}s", target_time, time_sec, f"{self.phase_start_row}-{row_index}")
                elif expected_step["type"] == "min_limit" and time_sec < target_time - self.TOLERANCE_SEC:
                    self._trigger_fail(f"Phase '{expected_phase_name}' took {time_sec:.1f}s, expected at least {target_time}s", target_time, time_sec, f"{self.phase_start_row}-{row_index}")
                else:
                    # Do not log PASS for WASH here since Agitation Analyzer logs the exact active time.
                    # Logging chronological time here confuses the user (513s vs 180s active).
                    if expected_phase_name != "WASH":
                        self._record_pass(expected_phase_name, target_time, time_sec, f"{self.phase_start_row}-{row_index}")

                self.current_step_index += 1
                self.time_in_current_phase = 0
                self.phase_start_row = None
                self.TOLERANCE_SEC = 2.0 # Reset tolerance to 2.0 seconds
                self._limit_fail_triggered = False
                
            self.last_phase = actual_phase

        self._emit_status()

    def _trigger_fail(self, reason, expected=None, actual=None, row_range=None):
        phase_name = self.expected_phases[self.current_step_index]['name'] if self.current_step_index < len(self.expected_phases) else "UNKNOWN"
        msg = (
            f"BUG: Timing sequence violation detected! Phase '{phase_name}' was out of bounds: {reason}. "
            f"EXPECTED: Phase duration should be exactly {expected} seconds. "
            f"SOURCE: Sharp Washing Machine HIL Specification Sheet (Course: {self.current_program}, Level: {self.current_level})."
        )
        self.log_callback(f"❌ SEQUENCE FAIL: {reason} (Exp: {expected}, Act: {actual})")
        self.record_callback(f"Phase Validator: {phase_name}", "FAIL", msg, expected if expected else 0, actual if actual else 0, row_range)
        self._emit_status()

    def _record_pass(self, phase, expected_time, actual_time, row_range=None):
        msg = f"✅ SEQUENCE PASS: {phase} ({actual_time:.1f}s / Exp: {expected_time}s)"
        self.log_callback(msg)
        self.record_callback(f"Phase Validator: {phase}", "PASS", msg, expected_time, actual_time, row_range)

    def finalize(self, row_index):
        if not self.expected_phases: return
        
        # Log the current phase if it was interrupted
        if getattr(self, 'phase_start_row', None) is not None and self.current_step_index < len(self.expected_phases):
            expected_step = self.expected_phases[self.current_step_index]
            time_sec = self.time_in_current_phase / 10.0
            self._trigger_fail(f"Phase '{expected_step['name']}' interrupted early at {time_sec:.1f}s", expected_step["duration_sec"], time_sec, f"{self.phase_start_row}-{row_index}")
            self.current_step_index += 1

        # Mark remaining phases as missing
        for i in range(self.current_step_index, len(self.expected_phases)):
            step = self.expected_phases[i]
            msg = f"❌ MISSING: Phase '{step['name']}' was not reached in the recording."
            self.log_callback(msg)
            self.record_callback(f"Phase Validator: {step['name']}", "MISSING", msg, step["duration_sec"], 0, "N/A")

    def _emit_status(self):
        if not self.expected_phases or self.current_step_index >= len(self.expected_phases):
            status = {"expected_phase": "Finished/Idle", "time_left": 0, "status": "FAIL" if self.is_failed else "IDLE"}
        else:
            expected_step = self.expected_phases[self.current_step_index]
            # 1. Current phase time left
            total_left = max(0, expected_step["duration_sec"] - (self.time_in_current_phase / 10.0))
            # 2. Add all future phases durations
            for i in range(self.current_step_index + 1, len(self.expected_phases)):
                total_left += self.expected_phases[i]["duration_sec"]
                
            status = {
                "expected_phase": expected_step["name"],
                "time_left": total_left,
                "status": "FAIL" if self.is_failed else "RUNNING"
            }
        self.validation_status.emit(status)

    def finalize(self, last_row_index):
        """Called at the end of the telemetry file to evaluate the final phase."""
        if not self.expected_phases or self.current_step_index >= len(self.expected_phases):
            return
            
        expected_step = self.expected_phases[self.current_step_index]
        expected_phase_name = expected_step["name"]
        
        if self.last_phase == expected_phase_name:
            target_time = expected_step["duration_sec"]
            time_sec = self.time_in_current_phase / 10.0
            row_range = f"{self.phase_start_row}-{last_row_index}"
            
            # Use the stored limit fail flag if it was triggered
            if getattr(self, '_limit_fail_triggered', False):
                if expected_step["type"] == "strict":
                    self._trigger_fail(f"Phase '{expected_phase_name}' took {time_sec:.1f}s, expected {target_time}s", target_time, time_sec, row_range)
                elif expected_step["type"] == "max_limit":
                    self._trigger_fail(f"Phase '{expected_phase_name}' took {time_sec:.1f}s, max {target_time}s", target_time, time_sec, row_range)
            else:
                # Normal evaluation for the final phase
                if expected_step["type"] == "strict" and abs(time_sec - target_time) > self.TOLERANCE_SEC:
                    self._trigger_fail(f"Phase '{expected_phase_name}' took {time_sec:.1f}s, expected {target_time}s", target_time, time_sec, row_range)
                elif expected_step["type"] == "max_limit" and time_sec > target_time + self.TOLERANCE_SEC:
                    self._trigger_fail(f"Phase '{expected_phase_name}' took {time_sec:.1f}s, max {target_time}s", target_time, time_sec, row_range)
                else:
                    self._record_pass(expected_phase_name, target_time, time_sec, row_range)

    def reset(self):
        self.current_step_index = 0
        self.time_in_current_phase = 0
        self.last_phase = 'IDLE'
        self.is_failed = False
        self.expected_phases = []
        self.phase_start_row = None
