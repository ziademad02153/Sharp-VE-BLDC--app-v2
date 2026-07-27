import nidaqmx
import nidaqmx.constants
import threading
from PyQt5.QtCore import QObject, pyqtSignal

class DAQHandler(QObject):
    data_ready = pyqtSignal(list)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.running = False
        self.task = None
        self.channels = [
            'cDAQ1Mod1/ai0', 'cDAQ1Mod1/ai1', 'cDAQ1Mod1/ai2', 'cDAQ1Mod1/ai3',
            'cDAQ1Mod1/ai4', 'cDAQ1Mod1/ai5', 'cDAQ1Mod1/ai6', 'cDAQ1Mod1/ai7'
        ]

    def start(self):
        self.running = True
        try:
            self.task = nidaqmx.Task()
            for ch in self.channels:
                self.task.ai_channels.add_ai_voltage_chan(ch)
            
            # 10,000 Hz Industrial Sampling Rate (Matches LabVIEW High-Speed standard)
            self.task.timing.cfg_samp_clk_timing(
                rate=10000.0,
                sample_mode=nidaqmx.constants.AcquisitionType.CONTINUOUS
            )
            
            self.thread = threading.Thread(target=self._daq_loop, daemon=True)
            self.thread.start()
        except Exception as e:
            self.error_occurred.emit(f"Hardware Connection Error: {e}. Check USB or DAQ Chassis.")

    def stop(self):
        self.running = False
        if self.task:
            try:
                self.task.stop()
                self.task.close()
            except:
                pass
            self.task = None

    def _daq_loop(self):
        while self.running:
            try:
                # Read 1000 samples (takes exactly 0.1 seconds at 10,000 Hz)
                data = self.task.read(number_of_samples_per_channel=1000, timeout=1.0)
                
                if not isinstance(data[0], list):
                    continue

                processed_data = []
                
                if not hasattr(self, 'global_idx'):
                    self.global_idx = 0
                    self.last_crossing_idx = -1
                    self.current_state = 'DOWN'
                    self.last_valid_rpm = 0.0
                    self.debounce_counter = 0

                PULSES_PER_REV = 4.0
                high_thresh = 2.0
                low_thresh = 1.0
                
                for val in data[0]:
                    # Timeout to force RPM to 0 if motor stops (no pulses for 0.25 seconds)
                    if self.last_crossing_idx != -1 and (self.global_idx - self.last_crossing_idx) > 2500:
                        self.last_valid_rpm = 0.0
                        
                    if self.debounce_counter > 0:
                        self.debounce_counter -= 1
                    else:
                        if self.current_state == 'DOWN' and val >= high_thresh:
                            self.current_state = 'UP'
                            if self.last_crossing_idx != -1:
                                delta_samples = self.global_idx - self.last_crossing_idx
                                time_elapsed = delta_samples / 10000.0
                                frequency = 1.0 / time_elapsed
                                self.last_valid_rpm = (frequency / PULSES_PER_REV) * 60.0
                            self.last_crossing_idx = self.global_idx
                            self.debounce_counter = 40  # Lock out all noise/bounces for 4ms
                        elif self.current_state == 'UP' and val <= low_thresh:
                            self.current_state = 'DOWN'
                            self.debounce_counter = 40  # Lock out falling edge bounces too
                    
                    self.global_idx += 1
                
                # Zero-speed timeout: if no edges detected for 1.0 second (10000 samples)
                if (self.global_idx - self.last_crossing_idx) > 10000:
                    self.last_valid_rpm = 0.0
                
                rpm = self.last_valid_rpm
                
                # --- DSP NOISE REJECTION FILTER ---
                # Only reject physically impossible spikes (> 2600 RPM)
                if not hasattr(self, 'last_valid_rpm_check'):
                    self.last_valid_rpm_check = 0.0
                
                if rpm > 2600.0:  # Absolute physical ceiling
                    rpm = self.last_valid_rpm_check
                else:
                    self.last_valid_rpm_check = rpm
                
                # --- LABVIEW-GRADE MEDIAN FILTER (Size 3) ---
                if not hasattr(self, 'rpm_history'):
                    self.rpm_history = [0.0, 0.0, 0.0]
                
                self.rpm_history.append(rpm)
                if len(self.rpm_history) > 3:
                    self.rpm_history.pop(0)
                    
                sorted_history = sorted(self.rpm_history)
                filtered_rpm = sorted_history[1]
                
                processed_data.append(round(filtered_rpm, 2)) 

                
                # 2. Process Analog Channels (ai1 to ai7 DC Voltage)
                for ch_idx in range(1, 8):
                    avg_val = sum(data[ch_idx]) / 1000.0
                    processed_data.append(round(avg_val, 3)) 
                    
                self.data_ready.emit(processed_data)
                
            except Exception as e:
                if self.running:
                    self.stop()
                    self.error_occurred.emit(f"🔴 HARDWARE DISCONNECTED: {e}")
                break
