# PROJECT MAP

## TECH_STACK
- **Language:** Python 3.x
- **Libraries:** NumPy, Pandas (for data analysis/export), PyQt5 (assumed for UI/DAQ interface), nidaqmx (DAQ Hardware)
- **Environment:** Windows, DAQ system integration

## SYSTEM_FLOW
1. **Data Acquisition (DAQ):** Reads electrical signals (Motor RPM, Valves, Pump, Door) from Sharp Washing Machines via NI DAQ at 10,000 Hz, with DSP noise rejection (`daq_handler.py`).
2. **Data Logging:** Records timestamped rows of data every 100ms (`main.py`).
3. **Logic & Error Monitoring:** Tracks the state machine (`sequence_validator.py`, `logic_monitor.py`) and standard E1-E7 errors (`error_monitor.py`).
4. **Agitation Analysis:** Evaluates motor ON/OFF timing during WASH phases (M1-M4, MU) against strict symmetrical specifications (`agitation_analyzer.py`).
5. **Report Generation:** Exports aggregated analysis, exact row ranges for anomalies, and technical evidence into an Excel summary report (`excel_exporter.py`).

## CURRENT STATE & PENDING
- **Agitation Analyzer:** COMPLETED. Strict symmetric alignment with Sharp HIL spec is enforced. No asymmetric logic remains.
- **Reporting System:** COMPLETED. Outputs exact row ranges (e.g. Row X-Y) for absolute traceability.
- **System Integrity:** COMPLETED. Codebase is clean, no TODOs, strict adherence to Simplicity First protocol.

## ORPHANS
- None.
