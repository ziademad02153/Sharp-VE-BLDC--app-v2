import json
import os
from PyQt5.QtCore import QObject, pyqtSignal

class ErrorMonitor(QObject):
    """
    Handles fault detection and error code triggering based on system specifications.
    """
    alarm_triggered = pyqtSignal(str)

    def __init__(self, log_callback, record_callback):
        super().__init__()
        self.log_callback = log_callback
        self.record_callback = record_callback
        self.errors_database = []
        
        # State trackers
        self.pump_timer = 0
        self.continuous_pump_timer = 0
        self.pump_cooldown_timer = 0
        self.motor_fail_timer = 0
        self.water_supply_timer = 0
        self.overflow_timer = 0
        self.motor_stuck_timer = 0
        self.leak_timer = 0
        self.unbalance_retries = 0
        self.e2_timer = 0
        
        # Logging flags
        self.e2_error_logged = False
        self.ea_error_logged = False
        self.thermal_warning_logged = False
        
        # Hydraulic Fallback Trackers (Defects #4 and #5)
        self.fallback_timer = 0
        self.fallback_delay_logged = False
        self.hot_cutoff_logged = False
        self.hot_valve_was_on = False
        
        # Sensor Debounce Trackers
        self.pump_active_ticks = 0
        self.cold_active_ticks = 0
        self.hot_active_ticks = 0
        self.softener_active_ticks = 0
        
        self._last_log_time = {}
        self._load_config()

    def _load_config(self):
        spec_path = 'sharp_spec.json'
        if not os.path.exists(spec_path):
            spec_path = 'wm_config.json'
            
        try:
            if os.path.exists(spec_path):
                with open(spec_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.errors_database = config.get("errors", [])
        except Exception:
            pass

    def evaluate_state(self, row_index, state, history):
        """
        Analyzes the current machine state to detect faults.
        """
        phase = state.get('phase', 'IDLE')
        rpm = state.get('rpm', 0)
        
        # Debounce Digital Sensors (300ms filter) to prevent 1-tick DAQ noise failures
        raw_pump = state.get('pump_on', False)
        self.pump_active_ticks = (self.pump_active_ticks + 1) if raw_pump else 0
        pump = (self.pump_active_ticks > 3) or (raw_pump and self.continuous_pump_timer > 0)
        
        raw_cold = state.get('cold_on', False)
        self.cold_active_ticks = (self.cold_active_ticks + 1) if raw_cold else 0
        cold = self.cold_active_ticks > 3
        
        raw_hot = state.get('hot_on', False)
        self.hot_active_ticks = (self.hot_active_ticks + 1) if raw_hot else 0
        hot = self.hot_active_ticks > 3
        
        raw_softener = state.get('softener_on', False)
        self.softener_active_ticks = (self.softener_active_ticks + 1) if raw_softener else 0
        softener = self.softener_active_ticks > 3
        
        empty = state.get('empty_on', False) 
        door_closed = state.get('door_closed', True)
        
        # 1. Lid Opening (E2) - DISABLED UNTIL CONNECTED
        # Door allowed to be open ONLY during WATER_FILL before Wash or Rinse
        # if not door_closed and phase not in ['IDLE', 'WATER_FILL']:
        #     self.e2_timer += 1
        #     if self.e2_timer >= 2: # 0.2 seconds at 10Hz
        #         if not self.e2_error_logged:
        #             self._trigger("E2", row_index - self.e2_timer + 1, row_index, f"Lid opened during active phase: {phase}")
        #             self.e2_error_logged = True
        # else:
        #     self.e2_timer = 0
        #     self.e2_error_logged = False

        # 2. Drain Failure (E1) - 15 min limit
        if phase == 'DRAIN' or (pump and phase != 'SPIN'):
            self.pump_timer += 1
            self.drain_idle = 0
            if self.pump_timer == 9000: # 15 min @ 10Hz
                self._trigger("E1", row_index - self.pump_timer + 1, row_index, "Drain timeout: Reset level not reached within 15m")
        else:
            self.drain_idle = getattr(self, 'drain_idle', 0) + 1
            if self.drain_idle > 50: # 5 seconds of confirmed pump OFF before resetting
                self.pump_timer = 0
            
        # Pump Thermal Monitor (STRICT SPEC: 2.5 mins ON, 10s OFF + 1s Tolerance)
        if pump:
            if 5 < self.pump_cooldown_timer < 90:
                actual_off = self.pump_cooldown_timer / 10.0
                msg = f"FAIL: Pump restarted after only {actual_off}s OFF (Minimum: 9.0s)"
                self.log_callback(msg)
                start_row = row_index - self.pump_cooldown_timer
                self.record_callback("Pump Cooldown", "FAIL", f"Row {start_row}-{row_index}: {msg}", 10.0, actual_off, f"{start_row}-{row_index}")
            elif 0 < self.pump_cooldown_timer <= 5:
                # < 500ms OFF is DAQ/Relay noise, ignore it and resume duty cycle
                pass

            self.pump_cooldown_timer = 0
            self.continuous_pump_timer += 1
            if self.continuous_pump_timer > 1510: # 150s + 1s tolerance = 151s
                self.thermal_warning_logged = True
        else:
            if self.thermal_warning_logged:
                total_on_time = self.continuous_pump_timer / 10.0
                msg = f"FAIL: Pump continuous operation reached {total_on_time}s (Limit: 150s + 1s tolerance)"
                self.log_callback(msg)
                start_row = row_index - self.continuous_pump_timer
                self.record_callback("Pump Duty Cycle", "FAIL", f"Row {start_row}-{row_index}: {msg}", 150.0, total_on_time, f"{start_row}-{row_index}")
                self.thermal_warning_logged = False
                
            self.pump_cooldown_timer += 1
            if self.pump_cooldown_timer > 20: # 2s debounce to separate ON cycles
                self.continuous_pump_timer = 0
            
        # 3. Water Supply (E5) - 20 min limit & Fallback Checks (#4 & #5)
        is_filling = (cold or hot)
        is_fallback_gap = (phase == 'IDLE' or phase == 'WATER_FILL') and self.hot_valve_was_on and not hot and not cold
        
        if is_filling or is_fallback_gap:
            self.water_supply_timer += 1
            self.fill_idle = 0
            if self.water_supply_timer == 12000: # 20.0 min @ 10Hz
                self._trigger("E5", row_index - self.water_supply_timer + 1, row_index, "Fill timeout: Target level not reached within 20m")
        else:
            self.fill_idle = getattr(self, 'fill_idle', 0) + 1
            if self.fill_idle > 50: # 5 seconds of confirmed NO fill before resetting
                self.water_supply_timer = 0

        # Hydraulic Fallback Sequence Validation (Defects #4 & #5)
        if phase in ['WASH', 'DRAIN', 'SPIN'] or phase.startswith('RINSE'):
            self.hot_valve_was_on = False
            self.fallback_timer = 0
            self.fallback_delay_logged = False
            self.hot_cutoff_logged = False
            self.hot_cutoff_timer = 0
            
        if hot:
            self.hot_valve_was_on = True
            self.fallback_timer = 0
            self.hot_cutoff_timer = 0

        if (phase == 'WATER_FILL' or phase == 'IDLE') and self.hot_valve_was_on and not hot:
            if not cold:
                self.fallback_timer += 1
                self.hot_cutoff_timer = 0
                self.cold_was_off = True
                self.cold_on_debounce = 0
            else:
                self.cold_on_debounce = getattr(self, 'cold_on_debounce', 0) + 1
                if self.cold_on_debounce > 10: # 1 second of stable cold ON to defeat sensor noise
                    if getattr(self, 'cold_was_off', False):
                        # Transition! Cold just turned on. Evaluate gap length.
                        if self.fallback_timer > 300: # Gap was > 30s
                            if not self.fallback_delay_logged:
                                actual_delay = round(self.fallback_timer / 10.0, 1)
                                self._trigger("HE-FALLBACK-DELAY", row_index - self.fallback_timer + 1, row_index, 
                                              f"Hot Water Fallback Delay: Compensation cold valve reopening was delayed by {actual_delay}s (Limit: 30s max per Sharp spec)")
                                self.fallback_delay_logged = True
                        self.cold_was_off = False
                        self.fallback_timer = 0 # Reset so it doesn't trigger again
                        
                    self.hot_cutoff_timer = getattr(self, 'hot_cutoff_timer', 0) + 1
                    if self.hot_cutoff_timer > 50: # 5 seconds of cold-only after hot was on
                        if not self.hot_cutoff_logged:
                            self._trigger("HE-HOT-CUTOFF", row_index - self.hot_cutoff_timer + 1, row_index, 
                                          "Hot Water Valve Cutoff: Hot water valve was shut off during fill while cold valve remained active for >5s. Spec requires both to remain active during Fallback.")
                            self.hot_cutoff_logged = True
        else:
            self.hot_cutoff_timer = 0
            self.cold_on_debounce = 0
            
        # 4. Overflow (E6-1)
        # Spec: "if the water remains at the dangerous overflow level for 5 minutes"
        if (cold or hot) and pump:
            self.overflow_timer += 1
            self.overflow_idle = 0
            if self.overflow_timer > 3000: # 5 mins (300 seconds @ 10Hz = 3000 ticks)
                self._trigger("E6-1", row_index - self.overflow_timer + 1, row_index, "Overflow risk: Concurrent fill and drain detected for > 5 mins")
        else:
            self.overflow_idle = getattr(self, 'overflow_idle', 0) + 1
            if self.overflow_idle > 50: # 5 seconds debounce
                self.overflow_timer = 0
            
        # 4b. Water Leakage (E9)
        # Spec: "if during wash (not filling) there is no water in the tub"
        if phase == 'WASH' and empty and not (cold or hot):
            self.leak_timer += 1
            self.leak_idle = 0
            if self.leak_timer > 100: # 10 seconds empty detection
                self._trigger("E9", row_index - self.leak_timer + 1, row_index, "Water Leakage: Tub is empty during wash phase.")
        else:
            self.leak_idle = getattr(self, 'leak_idle', 0) + 1
            if self.leak_idle > 30: # 3 seconds debounce for water sloshing
                self.leak_timer = 0
 
        # 5. Motor Rotation (E7 series)
        # Spec: E7-1 (CW fail), E7-2 (CCW fail), E7-3 (Spin CW fail), E7-4 (CW/CCW fail).
        motor_on = state.get("motor_v_on", False)
        if phase == 'WASH' or phase.startswith('RINSE'):
            if motor_on and rpm < 5:
                self.motor_fail_timer += 1
                self.motor_success_timer = 0
                if self.motor_fail_timer > 100: # 10 accumulated seconds of ON time with no rotation
                    self._trigger("E7-1/E7-2", row_index - self.motor_fail_timer + 1, row_index, "Motor failure (E7): Motor jammed (no rotation detected over multiple strokes)")
            elif rpm >= 5:
                self.motor_success_timer = getattr(self, 'motor_success_timer', 0) + 1
                if self.motor_success_timer > 5: # 500ms of stable rotation to defeat inductive noise
                    self.motor_fail_timer = 0
        elif phase == 'SPIN':
            if motor_on and rpm < 10:
                self.motor_fail_timer += 1
                self.motor_success_timer = 0
                if self.motor_fail_timer > 300: # 30 accumulated seconds of ON time with no rotation
                    self._trigger("E7-3", row_index - self.motor_fail_timer + 1, row_index, "Spin failure (E7-3): Motor stalled during Spin")
            elif rpm >= 10:
                self.motor_success_timer = getattr(self, 'motor_success_timer', 0) + 1
                if self.motor_success_timer > 10: # 1s of stable rotation
                    self.motor_fail_timer = 0
        else:
            self.motor_fail_timer = 0
            
        # 5a. Missing Hardware Errors (LP, E5-1, E3)
        # Note: LP (Low Power) requires Main Voltage < 160V for 5 mins (Not available in CSV).
        # Note: E5-1 requires Water Level Frequency data (Not available in CSV).
        # Note: E3 requires MEMS data (Not available in CSV).
            
        # 5b. Phantom RPM / Sensor Noise (e.g. 750 RPM from 50Hz water short)
        if phase in ['WATER_FILL', 'IDLE', 'DRAIN'] and rpm > 300:
            if not hasattr(self, 'phantom_rpm_timer'):
                self.phantom_rpm_timer = 0
            self.phantom_rpm_timer += 1
            if self.phantom_rpm_timer > 50: # 5 seconds of impossible high RPM
                self._trigger("SENSOR-SHORT", row_index - self.phantom_rpm_timer + 1, row_index, f"CRITICAL: Impossible {rpm} RPM detected during {phase}. Possible water leak on sensor (50Hz noise).")
        else:
            self.phantom_rpm_timer = 0

        # 7. Softener Dispense Rules
        softener = state.get("softener_on", False)
        drain_count = state.get("drain_count", 0)
        
        if softener:
            if drain_count == 0:
                if not getattr(self, 'softener_premature_logged', False):
                    self._trigger("SOFT-1", row_index, row_index, "Premature Softener Dispense: Valve opened before first drain (during wash).")
                    self.softener_premature_logged = True

        # 8. Sharp V4 Spec: Hot Water Restrictions & High-Speed Spin Safety Rules
        # Rule 8a: Hot Water Valve strictly prohibited during Rinse (Rinse is Cold Water Only per Table3)
        if phase.startswith('RINSE') and hot:
            if not getattr(self, 'hot_rinse_logged', False):
                self._trigger("HOT-RINSE-VIOLATION", row_index - 10, row_index, 
                              "Unauthorized Hot Water Fill: Hot water valve activated during Rinse phase. Sharp spec Table3 restricts Hot/Warm water to Wash phase only; all Rinse fills must be Cold Water Only.")
                self.hot_rinse_logged = True
        elif not phase.startswith('RINSE'):
            self.hot_rinse_logged = False

        # Rule 8b: Water Inlet Valves (Cold/Hot/Softener) strictly prohibited during High Speed Spin (>300 RPM)
        if rpm > 300 and (cold or hot or softener):
            if not getattr(self, 'valve_spin_logged', False):
                active_valves = []
                if cold: active_valves.append("Cold")
                if hot: active_valves.append("Hot")
                if softener: active_valves.append("Softener")
                valve_str = "+".join(active_valves)
                self._trigger("VALVE-SPIN-VIOLATION", row_index - 10, row_index, 
                              f"Safety Violation: Water Inlet Valve ({valve_str}) activated during High Speed Spin ({rpm} RPM > 300 RPM limit).")
                self.valve_spin_logged = True
        elif rpm <= 300:
            self.valve_spin_logged = False
                    
 
        # 6. Unbalance (E3-2)
        if phase == 'SPIN':
            if not getattr(self, 'unbalance_was_spinning', False):
                self.unbalance_spin_timer = 0
            self.unbalance_was_spinning = True
            self.unbalance_spin_timer += 1
            self.unbalance_idle_timer = 0
        elif phase == 'IDLE' and getattr(self, 'unbalance_was_spinning', False):
            self.unbalance_idle_timer += 1
            if self.unbalance_idle_timer > 600: # 60s without fill -> it was a successful spin, or user paused
                self.unbalance_was_spinning = False
                self.unbalance_idle_timer = 0
        elif phase == 'WATER_FILL' and getattr(self, 'unbalance_was_spinning', False):
            if len(history) > 1 and history[-2].get('phase') != 'WATER_FILL': # Transition edge
                # It filled shortly after a spin. Was the spin aborted early?
                if getattr(self, 'unbalance_spin_timer', 0) < 900: # Spin lasted less than 90s
                    self.unbalance_retries += 1
                    self.log_callback(f"Unbalance attempt #{self.unbalance_retries} (Spin aborted after {self.unbalance_spin_timer/10.0}s)")
                    if self.unbalance_retries >= 3:
                        self._trigger("E3-2", row_index, row_index, "Critical unbalance: 3 failed recovery attempts")
                else:
                    # Successful spin, normal rinse fill
                    self.unbalance_retries = 0
            self.unbalance_was_spinning = False
 
    def _trigger(self, code, start_row, end_row, evidence):
        current_time = end_row
        if code in self._last_log_time and (current_time - self._last_log_time[code]) < 50:
            return
            
        self._last_log_time[code] = current_time
        name = next((e["name"] for e in self.errors_database if e["code"] == code), f"Fault {code}")
        
        self.alarm_triggered.emit(f"Fault {code}: {name} | {evidence}")
        self.log_callback(f"ERROR {code} [{name}]: {evidence}")
        self.record_callback(f"Error {code}", "FAIL", f"Row {start_row}-{end_row}: {evidence}", 0, 0, f"{start_row}-{end_row}")
 
    def reset_timers(self):
        self.pump_timer = 0
        self.continuous_pump_timer = 0
        self.pump_cooldown_timer = 0
        self.motor_fail_timer = 0
        self.water_supply_timer = 0
        self.overflow_timer = 0
        self.motor_stuck_timer = 0
        self.leak_timer = 0
        self.unbalance_retries = 0
        self.e2_timer = 0
        self.e2_error_logged = False
        self.ea_error_logged = False
        self.thermal_warning_logged = False
        self.fallback_timer = 0
        self.fallback_delay_logged = False
        self.hot_cutoff_logged = False
        self.hot_valve_was_on = False
        self.hot_cutoff_timer = 0
        self.cold_was_off = False
        self.cold_on_debounce = 0
        
        self.pump_active_ticks = 0
        self.cold_active_ticks = 0
        self.hot_active_ticks = 0
        self.softener_active_ticks = 0
        
        self.softener_premature_logged = False
        self.hot_rinse_logged = False
        self.valve_spin_logged = False
        self.phantom_rpm_timer = 0
        
        # Idle Debounce trackers
        self.drain_idle = 0
        self.fill_idle = 0
        self.overflow_idle = 0
        self.leak_idle = 0
        self.motor_success_timer = 0
        
        # Unbalance state
        self.unbalance_was_spinning = False
        self.unbalance_spin_timer = 0
        self.unbalance_idle_timer = 0
        
        self._last_log_time = {}
