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
        pump = state.get('pump_on', False)
        empty = state.get('empty_on', False) 
        cold = state.get('cold_on', False)
        hot = state.get('hot_on', False)
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
        if (phase == 'DRAIN' or pump):
            self.pump_timer += 1
            if self.pump_timer == 9000: # 15 min @ 10Hz
                self._trigger("E1", row_index - self.pump_timer + 1, row_index, "Drain timeout: Reset level not reached within 15m")
        else:
            self.pump_timer = 0
            
        # Pump Thermal Monitor (STRICT SPEC: 2.5 mins ON, 10s OFF + 1s Tolerance)
        if pump:
            if 0 < self.pump_cooldown_timer < 90:
                actual_off = self.pump_cooldown_timer / 10.0
                msg = f"WARNING: Pump restarted after only {actual_off}s OFF (Minimum: 9.0s)"
                self.log_callback(msg)
                start_row = row_index - self.pump_cooldown_timer
                self.record_callback("Pump Cooldown", "WARNING", f"Row {start_row}-{row_index}: {msg}", 10.0, actual_off, f"{start_row}-{row_index}")

            self.pump_cooldown_timer = 0
            self.continuous_pump_timer += 1
            if self.continuous_pump_timer > 1510: # 150s + 1s tolerance = 151s
                self.thermal_warning_logged = True
        else:
            if self.thermal_warning_logged:
                total_on_time = self.continuous_pump_timer / 10.0
                msg = f"WARNING: Pump continuous operation reached {total_on_time}s (Limit: 150s + 1s tolerance)"
                self.log_callback(msg)
                start_row = row_index - self.continuous_pump_timer
                self.record_callback("Pump Duty Cycle", "WARNING", f"Row {start_row}-{row_index}: {msg}", 150.0, total_on_time, f"{start_row}-{row_index}")
                self.thermal_warning_logged = False
                
            self.pump_cooldown_timer += 1
            if self.pump_cooldown_timer > 20: # 2s debounce to separate ON cycles
                self.continuous_pump_timer = 0
            
        # 3. Water Supply (E5) - 20 min limit & Fallback Checks (#4 & #5)
        if (cold or hot):
            self.water_supply_timer += 1
            if self.water_supply_timer == 12000: # 20.0 min @ 10Hz
                self._trigger("E5", row_index - self.water_supply_timer + 1, row_index, "Fill timeout: Target level not reached within 20m")
        else:
            self.water_supply_timer = 0

        # Hydraulic Fallback Sequence Validation (Defects #4 & #5)
        if hot:
            self.hot_valve_was_on = True
            self.fallback_timer = 0

        if phase == 'WATER_FILL' and self.hot_valve_was_on and not hot:
            if not cold:
                self.fallback_timer += 1
                if self.fallback_timer > 300: # Exceeded 30 seconds @ 10Hz
                    if not self.fallback_delay_logged:
                        actual_delay = round(self.fallback_timer / 10.0, 1)
                        self._trigger("HE-FALLBACK-DELAY", row_index - self.fallback_timer + 1, row_index, 
                                      f"Hot Water Fallback Delay: Compensation cold valve reopening was delayed by {actual_delay}s (Limit: 30s max per Sharp spec)")
                        self.fallback_delay_logged = True
            else:
                if not hot and not self.hot_cutoff_logged:
                    self._trigger("HE-HOT-CUTOFF", row_index - 50, row_index, 
                                  "Hot Water Valve Cutoff: Hot water valve command was shut off (0V) during fallback sequence instead of remaining active alongside cold valve as required by Sharp spec")
                    self.hot_cutoff_logged = True
            
        # 4. Overflow (E6-1)
        if (cold or hot) and pump:
            self.overflow_timer += 1
            if self.overflow_timer > 100: # Fast detection for safety (10s)
                self._trigger("E6-1", row_index - self.overflow_timer + 1, row_index, "Overflow risk: Concurrent fill and drain detected")
        else:
            self.overflow_timer = 0
 
        # 5. Motor Rotation (E7 series)
        if (phase == 'WASH' or phase.startswith('RINSE')) and rpm < 5:
            self.motor_fail_timer += 1
            if self.motor_fail_timer == 1200: # 120 seconds (1200 ticks @ 10Hz) to allow normal Heavy wash pauses
                self._trigger("E7-1", row_index - self.motor_fail_timer + 1, row_index, "Motor failure: No rotation during wash/rinse")
        elif phase == 'SPIN' and rpm < 10:
            self.motor_fail_timer += 1
            if self.motor_fail_timer == 1200: # 120 seconds
                self._trigger("E7-3", row_index - self.motor_fail_timer + 1, row_index, "Spin failure: Motor stalled during spin cycle")
        else:
            self.motor_fail_timer = 0
            
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
                    
 
        # 6. Unbalance (E3-2)
        if len(history) > 1:
            prev_phase = history[-2].get('phase', 'IDLE')
            if prev_phase == 'SPIN_PAUSE' and phase == 'WATER_FILL':
                self.unbalance_retries += 1
                self.log_callback(f"Unbalance attempt #{self.unbalance_retries}")
                if self.unbalance_retries >= 3:
                    self._trigger("E3-2", row_index, row_index, "Critical unbalance: 3 failed recovery attempts")
        if phase == 'IDLE':
            self.unbalance_retries = 0
 
    def _trigger(self, code, start_row, end_row, evidence):
        current_time = end_row
        if code in self._last_log_time and (current_time - self._last_log_time[code]) < 50:
            return
            
        self._last_log_time[code] = current_time
        name = next((e["name"] for e in self.errors_database if e["code"] == code), f"Fault {code}")
        
        self.alarm_triggered.emit(f"Fault {code}: {name} | {evidence}")
        self.log_callback(f"ERROR {code} [{name}]: {evidence}")
        self.record_callback(f"Error {code}", "FAIL", f"Row {start_row}-{end_row}: {evidence}")
 
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
        self.e2_error_logged = False
        self.ea_error_logged = False
        self.thermal_warning_logged = False
        self.fallback_timer = 0
        self.fallback_delay_logged = False
        self.hot_cutoff_logged = False
        self.hot_valve_was_on = False
        self._last_log_time = {}
