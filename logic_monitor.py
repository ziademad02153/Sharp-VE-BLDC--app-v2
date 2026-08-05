import json
import logging
import os
from PyQt5.QtCore import QObject, pyqtSignal
from error_monitor import ErrorMonitor
from sequence_validator import SequenceValidator

class LogicMonitor(QObject):
    """
    High-Precision Logic Engine for SHARP BLDC Validation.
    Monitors sequence timing, motor ramps, and safety interlocks.
    """
    log_event = pyqtSignal(str) 
    test_result = pyqtSignal(dict) 
    phase_changed = pyqtSignal(str) 
    validation_status = pyqtSignal(dict) 
    spin_logic_status = pyqtSignal(str, str) 
    pump_duty_status = pyqtSignal(str, str) 
    
    def __init__(self):
        super().__init__()
        self.row_index = 0
        self.history = []
        self.analysis_summary = []
        self.rpm_history = []
        
        # Spin Curve State Machine
        self.spin_timer = 0
        self.spin_decel_timer = 0
        self.spin_state = "IDLE" # IDLE, RAMP_1, BALANCE, RAMP_2, MID_SPIN, RAMP_3, HIGH_SPIN, COASTING
        
        self.current_phase = 'IDLE'
        self.monitoring_active = False
        self.drain_count = 0
        self._prev_pump = False
        self.has_filled = False
        
        self.VOLTAGE_THRESHOLD = 2.0  
        self.current_program = "Regular"
        self.current_level = 1
        self.weight_detect_timer = 0
        self.drain_count = 0
        self.was_draining = False
        self.expected_rinse_count = 2
        
        # Debounce Timers
        self.pump_off_timer = 0
        self.pump_on_timer = 0
        self.rpm_zero_timer = 0
        self.valve_on_timer = 0
        self.softener_on_timer = 0
        
        self.error_monitor = ErrorMonitor(self.log_event.emit, self._record_result_proxy)
        self.sequence_validator = SequenceValidator(self.log_event.emit, self._record_result_proxy)
        self.sequence_validator.validation_status.connect(self.validation_status.emit)
        
    def _record_result_proxy(self, test_name, status, evidence, expected=0, actual=0, row_range=None):
        res = {
            "Row_Index": row_range if row_range is not None else self.row_index, 
            "Test_Name": test_name, 
            "Status": status, 
            "Expected_Sec": expected,
            "Actual_Sec": actual,
            "Technical_Evidence": evidence
        }
        self.analysis_summary.append(res)
        self.test_result.emit(res)

    def set_program(self, ui_program_name, level="LEV-1", soak_option="No Soak", delay_option="None", wash_override="Default", rinse_override="Default", spin_override="Default"):
        # Direct passthrough — main.py combo box sends exact program names
        # that match sharp_spec.json keys (e.g. "Heavy", "Quick Rinse")
        valid_programs = [
            "Regular", "Quick", "Heavy", "Baby Care", "Cotton",
            "Delicates", "Wool", "Jeans", "Blanket",
            "Quick Rinse", "Sports Wear", "Tub Clean"
        ]
        self.current_program = ui_program_name if ui_program_name in valid_programs else "Regular"
        self.current_level = level
        
        self.expected_rinse_count = 2
        try:
            import json, os
            spec_path = os.path.join(os.path.dirname(__file__), "sharp_spec.json")
            with open(spec_path, "r", encoding="utf-8") as f:
                spec_data = json.load(f)
                lvl_key = level if "LEV-" in level else f"LEV-{level.replace('LEV-', '').strip()}"
                self.expected_rinse_count = spec_data.get("sequence_chart", {}).get(self.current_program, {}).get(lvl_key, {}).get("rinse_count", 2)
        except:
            pass
            
        if rinse_override != "Default":
            try:
                self.expected_rinse_count = int(rinse_override.split(" ")[0])
            except:
                pass
                
        self.log_event.emit(f"Program set to {self.current_program} ({level}) - Soak: {soak_option} - Delay: {delay_option}")
        self.sequence_validator.set_program(self.current_program, level, soak_option, delay_option, wash_override, rinse_override, spin_override)
        
    def process_row(self, data):
        try:
            self.row_index += 1
            motor_rpm, cold, hot, softener, gearmotor, motor_v, pump, door = data[2:]
            
            self.rpm_history.append(motor_rpm)
            if len(self.rpm_history) > 5: 
                self.rpm_history.pop(0)
            # Use Median Filter instead of Average to completely reject 1-tick massive DAQ spikes
            smoothed_rpm = sorted(self.rpm_history)[len(self.rpm_history) // 2]
            
            pump_on = pump > self.VOLTAGE_THRESHOLD
            gearmotor_on = gearmotor > self.VOLTAGE_THRESHOLD
            cold_on = cold > self.VOLTAGE_THRESHOLD
            hot_on = hot > self.VOLTAGE_THRESHOLD
            softener_on = softener > self.VOLTAGE_THRESHOLD
            motor_v_on = motor_v > self.VOLTAGE_THRESHOLD
            door_closed = door > 1.0 
            
            # 1. Detection of Machine Start
            if not self.monitoring_active:
                if (smoothed_rpm > 10 or pump_on or gearmotor_on or cold_on or hot_on):
                    self.monitoring_active = True
                    self.log_event.emit("System activity detected. Validation engine is now ACTIVE.")
                else:
                    # While in standby, update UI cards but skip logic
                    self.pump_duty_status.emit("WAITING", "#9E9E9E")
                    return

            state = {
                "door_closed": door_closed, 
                "pump_on": pump_on,
                "gearmotor_on": gearmotor_on,
                "cold_on": cold_on,
                "hot_on": hot_on,
                "softener_on": softener_on,
                "motor_v_on": motor_v_on,
                "rpm": smoothed_rpm,
                "phase": self.current_phase,
                "drain_count": self.drain_count
            }
            
            self._update_phase(state)
            state["phase"] = self.current_phase
            self.history.append(state)
            if len(self.history) > 1000: self.history.pop(0)

            # High-Precision Spin Logic
            self._monitor_spin_curve(smoothed_rpm)
            
            # Fault detection
            self.error_monitor.evaluate_state(self.row_index, state, self.history)
            
            # Update Pump UI Signal
            if getattr(self.error_monitor, 'thermal_warning_logged', False):
                self.pump_duty_status.emit("OVERLOAD", "#FF3131")
            else:
                self.pump_duty_status.emit("OK", "#39FF14")
                
            self.sequence_validator.evaluate_state(self.current_phase, self.row_index)
            
        except Exception as e:
            self.log_event.emit(f"ERROR: Logic processing failed: {str(e)}")

    def _update_phase(self, state):
        old_phase = self.current_phase
        pump = state['pump_on']
        gear = state['gearmotor_on']
        cold = state['cold_on']
        hot = state['hot_on']
        rpm = state['rpm']
        softener = state.get('softener_on', False)
        
        # Hardware Debounce Counters
        if not (pump or gear):
            self.pump_off_timer += 1
            self.pump_on_timer = 0
        else:
            self.pump_on_timer += 1
            self.pump_off_timer = 0
            
        if cold or hot or softener:
            self.valve_on_timer += 1
        else:
            self.valve_on_timer = 0
            
        if softener:
            self.softener_on_timer += 1
        else:
            self.softener_on_timer = 0
            
        if rpm < 5:
            self.rpm_zero_timer += 1
        else:
            self.rpm_zero_timer = 0
        
        # Detect transition from DRAIN or SPIN to next phase
        # Requires 2 seconds (20 ticks) of confirmed Pump/Gear OFF to prevent relay noise from double-counting drains
        if old_phase in ['DRAIN', 'SPIN'] and self.pump_off_timer > 20:
            if not self.was_draining: # Transition edge
                self.drain_count += 1
                self.has_filled = False # Reset fill status for next cycle (Rinse)
                self.was_draining = True
        elif self.pump_on_timer > 5:
            self.was_draining = False

        if not (pump or gear):
            self.spin_decel_timer = 0

        # Require 5 ticks (500ms) of pump/gear to switch to DRAIN/SPIN to avoid spike switching
        if self.pump_on_timer > 5:
            if rpm > 40:
                self.current_phase = 'SPIN'
                self.spin_decel_timer = 0
            else:
                if old_phase == 'SPIN':
                    self.spin_decel_timer += 1
                    if self.spin_decel_timer >= 150: # 15s debounce
                        self.current_phase = 'DRAIN'
                    else:
                        self.current_phase = 'SPIN'
                else:
                    self.current_phase = 'DRAIN'
        elif self.valve_on_timer > 5: # Require 500ms of valve to declare WATER_FILL
            if old_phase not in ['WASH'] and not old_phase.startswith('RINSE'):
                self.current_phase = 'WATER_FILL'
                self.has_filled = True
        elif old_phase == 'SPIN' and self.rpm_zero_timer < 50: # Allow 5 seconds of zero RPM before dropping SPIN
            # Coasting/Deceleration period of SPIN: retain SPIN
            self.current_phase = 'SPIN'
        elif rpm > 5:
            if self.drain_count > self.expected_rinse_count:
                self.current_phase = 'ANTI_WRINKLE'
            elif self.has_filled:
                # Logic: If softener was used, we drained once, or it's Quick Rinse, it's RINSE
                # Debounce softener to prevent 1-tick DAQ noise from causing phase flicker (WASH -> RINSE -> WASH)
                if (self.softener_on_timer > 5) or self.drain_count > 0 or self.current_program == "Quick Rinse":
                    # Map to RINSE_1, RINSE_2 etc for validator matching
                    rinse_num = max(1, self.drain_count)
                    self.current_phase = f'RINSE_{rinse_num}'
                else:
                    self.current_phase = 'WASH'
            else:
                # Smart Detection for mid-cycle start
                self.weight_detect_timer += 1
                if self.weight_detect_timer > 150: 
                    self.current_phase = 'WASH'
                else:
                    self.current_phase = 'WEIGHT_DETECT'
        else:
            self.weight_detect_timer = 0
            # Retain the active phase during standard short inactive pauses (e.g. motor pauses between strokes or valve cycles)
            if old_phase in ['WASH'] or old_phase.startswith('RINSE'):
                pass
            elif not self.has_filled and old_phase == 'WEIGHT_DETECT':
                pass 
            else:
                self.current_phase = 'IDLE'

        if old_phase != self.current_phase:
            self.log_event.emit(f"Phase Transition: {old_phase} -> {self.current_phase}")
            self.phase_changed.emit(self.current_phase)
            self.sequence_validator.sync_to_machine_phase(self.current_phase)

    def _monitor_spin_curve(self, rpm):
        """
        Implements the strict SHARP Spin Curve state machine.
        Reference: Spin control specs.png
        """
        if self.current_phase != 'SPIN':
            if self.spin_state != "IDLE":
                self.spin_state = "IDLE"
                self.spin_timer = 0
                self.spin_logic_status.emit("IDLE", "#9E9E9E")
            return

        self.spin_timer += 1
        t = self.spin_timer / 10.0 # Time in seconds
        
        is_gentle = self.current_program in ["Delicates", "Wool", "Sports Wear"]

        if self.spin_state == "IDLE":
            self.spin_state = "RAMP_1"
            self.spin_logic_status.emit("RAMP 300", "#FFEA00")
            
        elif self.spin_state == "RAMP_1":
            if rpm >= 290:
                if t < 12: # Should be 15s
                    self.spin_logic_status.emit(f"FAST RAMP ({t}s)", "#FF3131")
                else:
                    self.spin_logic_status.emit(f"RAMP OK ({t}s)", "#39FF14")
                self.spin_state = "BALANCE"
                self.balance_start_time = t

        elif self.spin_state == "BALANCE":
            duration = t - self.balance_start_time
            if duration >= 20: # Should stay 20s at 300
                if is_gentle:
                    if rpm > 320:
                        self.spin_state = "RAMP_2"
                        self.spin_logic_status.emit("RAMP 400", "#FFEA00")
                    else:
                        self.spin_logic_status.emit(f"BALANCING ({int(duration)}s)", "#39FF14")
                else:
                    if rpm > 400:
                        self.spin_state = "RAMP_2"
                        self.spin_logic_status.emit("RAMP 600", "#FFEA00")
                    else:
                        self.spin_logic_status.emit(f"BALANCING ({int(duration)}s)", "#39FF14")
            else:
                if (is_gentle and rpm > 350) or (not is_gentle and rpm > 400): # Jumped too early
                    self.spin_logic_status.emit(f"SHORT BAL ({int(duration)}s)", "#FF3131")
                    self.spin_state = "RAMP_2"

        elif self.spin_state == "RAMP_2":
            if is_gentle:
                if rpm >= 380:
                    self.spin_state = "HIGH_SPIN"
                    self.spin_logic_status.emit("HIGH SPIN 400", "#39FF14")
            else:
                if rpm >= 580:
                    self.spin_state = "MID_SPIN"
                    self.spin_logic_status.emit("MID SPIN 600", "#39FF14")

        elif self.spin_state == "MID_SPIN":
            if not is_gentle and rpm > 650:
                self.spin_state = "HIGH_SPIN"
                self.spin_logic_status.emit("HIGH SPIN 700", "#39FF14")

    def reset(self):
        self.row_index = 0
        self.history.clear()
        self.analysis_summary.clear()
        self.rpm_history.clear()
        self.spin_state = "IDLE"
        self.spin_timer = 0
        self.spin_decel_timer = 0
        self.current_phase = 'IDLE'
        self.drain_count = 0
        self.has_filled = False
        self._prev_pump = False
        self.monitoring_active = False
        
        # Reset Debounce Timers
        self.pump_off_timer = 0
        self.pump_on_timer = 0
        self.rpm_zero_timer = 0
        self.valve_on_timer = 0
        self.softener_on_timer = 0
        
        self.error_monitor.reset_timers()
        self.sequence_validator.reset()
        self.spin_logic_status.emit("IDLE", "#9E9E9E")
        self.pump_duty_status.emit("OK", "#39FF14")

    def get_summary(self):
        """Returns the accumulated analysis results for Excel export"""
        # Call finalize to capture any interrupted or missing phases
        self.sequence_validator.finalize(self.row_index)
        
        status = "SUCCESS"
        for entry in self.analysis_summary:
            if entry["Status"] in ["FAIL", "MISSING"]:
                status = "FAIL"
                break
        return {
            "final_status": status,
            "test_cases": self.analysis_summary
        }
