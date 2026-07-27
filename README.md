# SHARP VE-BLDC Industrial HIL Validation Suite

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![PyQt5](https://img.shields.io/badge/PyQt5-GUI-green.svg)
![Hardware-In-the-Loop](https://img.shields.io/badge/Testing-HIL-orange.svg)
![Status](https://img.shields.io/badge/Status-Industrial_Production_Ready-success.svg)

## Engineering Lead & Authorship

- **Lead R&D Systems Engineer**: Ziad Emad Allam
- **Organization**: El Araby Group R&D Engineering Division
- **System Domain**: Hardware-in-the-Loop (HIL) Automated Firmware Validation & SCADA Analytics

---

## Executive Summary

The **SHARP VE-BLDC Industrial HIL Validation Suite** is an advanced Hardware-In-the-Loop (HIL) automated testing and diagnostic platform engineered specifically for the **Sharp VE BLDC 11kg/13kg** washing machine firmware series.

By sampling 8 high-speed electrical and frequency channels through a National Instruments DAQ hardware interface at 10,000 Hz with real-time DSP noise filtering, the system automates physical software verification. It validates 100% of the embedded timing specifications, agitation motor waveforms (M1-M4, MU, MR), safety protocols, and hydraulic fallback sequences defined by Sharp engineering standards.

---

## System Architecture

The software architecture is designed using modular **Clean Architecture** principles, decoupling hardware signal acquisition, digital signal processing (DSP), finite state machine (FSM) phase inference, rule-based error evaluation, and industrial SCADA visualization.

```mermaid
graph TD
    subgraph Hardware[Physical Hardware Layer]
        WM[Sharp VE BLDC Washing Machine]
    end

    subgraph DAQ[Acquisition & DSP Layer]
        NI[NI-DAQmx Card / Telemetry Stream]
        DSP[10kHz DSP Noise Filter & Schmitt Trigger]
    end
    
    subgraph Core[Core Validation Engine]
        LM[Logic Monitor: FSM State Machine]
        AA[Agitation Analyzer: M1-M4/MU Motion Extraction]
        SV[Sequence Validator: Program Spec Matcher]
        EM[Error Monitor: Sharp Fault Trees & Hydraulic Checks]
    end
    
    subgraph UI[SCADA Visualization Layer]
        Header[El Araby Brand Header & Live Pipeline Stepper Bar]
        Cards[Digital I/O Status Cards]
        Scope[Live 8-Channel Oscilloscope Display]
        Adv[Advanced Hardware Dynamics Panel]
    end
    
    subgraph Output[Automated Reporting Engine]
        Excel[Multi-Sheet Excel Report Generator]
    end

    WM -- 8 Physical Channels --> NI
    NI -- Raw Analog Data --> DSP
    DSP -- Clean 10Hz Telemetry --> LM
    LM -- Signal Array --> AA
    LM -- State Tracking --> Header
    LM -- Phase Compliance --> SV
    LM -- Voltage & Frequency Checks --> EM
    AA & EM -- Failure Logs --> Adv
    SV & EM & AA -- Complete Dataset --> Excel
```

---

## Finite State Machine (FSM) & Hydraulic Logic

The core logic engine infers physical washer operations from analog voltage levels and motor frequency pulses. It supports 12 factory programs across 4 water levels:

```mermaid
stateDiagram-v2
    [*] --> IDLE
    IDLE --> WEIGHT_DETECT : Motor CW/CCW Pulses (7.2s Sequence)
    WEIGHT_DETECT --> WATER_FILL : Valve Voltage Active (>2.0V)
    IDLE --> WATER_FILL : Valve Voltage Active (>2.0V)
    
    WATER_FILL --> WASH : Fill Complete & Agitation Motion Starts
    WATER_FILL --> DRAIN : Drain Pump Active (>2.0V)
    WATER_FILL --> HYDRAULIC_FALLBACK : Hot Valve Interrupted (30s Timer)
    HYDRAULIC_FALLBACK --> WATER_FILL : Cold Valve Reopens
    
    WASH --> DRAIN : Drain Pump Active
    WASH --> WATER_FILL : Level Drop / Water Refill
    
    DRAIN --> SPIN_PAUSE : Pump Stop & Clutch Transition (150s)
    SPIN_PAUSE --> SPIN : Motor Ramp (300 RPM Balance -> 600/700 RPM)
    
    SPIN --> IDLE : Power Cutoff / Cycle Finish
    SPIN --> UNTANGLE : Post-Spin Micro Agitation (MU)
    UNTANGLE --> IDLE : Cycle End
```

---

## Industrial Fault Tree & Safety Library

The **ErrorMonitor** continuously checks telemetry against Sharp industrial fault specifications and hydraulic failure rules:

| Fault Code | Failure Description | Trigger Logic & Tolerances | Severity |
| :--- | :--- | :--- | :--- |
| **E1** | Drain Timeout | Tub water level fails to reset within 15 minutes of continuous pump operation. | CRITICAL |
| **E2** | Lid Safety Violation | Lid opened during active washing motor stroke or high-speed spin phase. | HIGH |
| **E3-2** | Unbalance Failure | Machine fails load redistribution after 3 consecutive spin pause/refill retries. | HIGH |
| **E5** | Water Fill Timeout | Target water level frequency not reached within 20 minutes of inlet valve opening. | HIGH |
| **E6-1** | Overflow Risk | Inlet valves and drain pump remain active simultaneously for >10 seconds. | CRITICAL |
| **E7-1 / E7-3** | Motor Hall Failure | Hall-sensor feedback missing during active Wash (E7-1) or Spin (E7-3). | CRITICAL |
| **E9** | Water Leakage | Unexpected water level frequency drop detected during active Wash phase. | HIGH |
| **EA** | Abnormal Water Level | Water detected in tub during high-speed Spin phase. | CRITICAL |
| **Eb-1** | Motor Relay Fused | Unplanned motor rotation detected while state machine is IDLE. | CRITICAL |
| **HE-FALLBACK-DELAY** | Hydraulic Delay Violation | Cold water valve reopening delayed by >30s during hot water supply fallback sequence. | HIGH |
| **HE-HOT-CUTOFF** | Hot Valve Cutoff Defect | Hot water valve command shut off (0V) during fallback instead of staying active. | CRITICAL |
| **PUMP-DUTY** | Thermal Duty Overload | Drain pump continuous operation exceeds 150s or violates 10s minimum cooldown. | MEDIUM |

---

## Key Technical Features

1. **Agitation Motion Extraction (M1, M2, M3, M4, MU, MR):**
   - Automatically measures Clockwise (CW), Counter-Clockwise (CCW), and Stop durations in milliseconds for Group 1, Group 2, Group 3, Blanket, and Tub Clean programs.

2. **Process Pipeline Stepper Bar:**
   - Real-time industrial SCADA stepper bar with active glowing neon indicators, completed phase checkmarks (`✓`), and dynamic iteration badges (`RINSE #1`, `DRAIN #2`).

3. **Multi-Sheet Executive Excel Reporting:**
   - **Raw Telemetry**: High-resolution 10Hz data log with timestamp breakdown (H, Min, Sec, ms).
   - **Automated Verification**: Phase-by-phase compliance summary with expected vs actual durations.
   - **Raw Data Defect Report**: Priority-sorted bug log with exact start/end row ranges (`Row X-Y`) and evidence logs.

---

## Installation & Execution

### Prerequisites
- Python 3.8+
- National Instruments DAQmx Driver (optional for live hardware DAQ, simulated mode supported natively)

### Setup Command
```bash
pip install PyQt5 pyqtgraph pandas xlsxwriter nidaqmx qtawesome openpyxl
```

### Running the Suite
```bash
python main.py
```

---

## Industrial Compliance & Verification

This platform is deployed for validation of embedded firmware logic in Sharp washing machine controllers manufactured by El Araby Group. All timing tolerances conform strictly to Sharp Factory Standard Specification `Sharp VE BLDC 11,13kg V0.xlsx`.
