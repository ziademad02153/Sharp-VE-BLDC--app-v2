import pandas as pd
from datetime import datetime
import os

from agitation_analyzer import analyze_telemetry
from excel_exporter import ExcelExporter
from logic_monitor import LogicMonitor

def export_test():
    print("Loading Original Raw Telemetry from Heavy_LEV-4_13k_18W-2R-5M_2026-07-06_12-52-25.xlsx ...")
    df = pd.read_excel("Heavy_LEV-4_13k_18W-2R-5M_2026-07-06_12-52-25.xlsx", sheet_name="Raw_Telemetry")
    
    raw_data_log = []
    for _, row in df.iterrows():
        raw_data_log.append([
            int(row['Row_Index']),
            "00:00:00", 
            row['Motor_RPM'],
            row['Cold_V'],
            row['Hot_V'],
            row['Softener'],
            row['GearMotor'],
            row.get('motor_v', row.get('Motor_V', 0)),
            row['Pump'],
            row.get('Door', 0)
        ])
        
    program_name = "Heavy"
    level = "LEV-4"
    wash_override = "18 Min"
    rinse_override = "2 Times"
    spin_override = "5 Min"
    
    # 1. Run Logic Monitor
    print("Running Logic Monitor...")
    logic_mon = LogicMonitor()
    logic_mon.set_program(program_name, level=level, soak_option="No Soak", delay_option="None",
                          wash_override=wash_override, rinse_override=rinse_override, spin_override=spin_override)
    for row in raw_data_log:
        logic_mon.process_row(row)
        
    summary = logic_mon.get_summary()
    test_cases = summary['test_cases']
    
    # 2. Run Agitation Analyzer
    print("Running Agitation Analyzer...")
    agitation_defects, _ = analyze_telemetry(
        raw_data_log,
        program_name,
        level,
        wash_override=wash_override,
        rinse_override=rinse_override,
        spin_override=spin_override
    )
    
    # 3. Export using Excel Exporter (The old code)
    print("Exporting Excel File...")
    exporter = ExcelExporter("Heavy_Report_v1.xlsx")
    exporter.export(raw_data_log, test_cases, defect_data=agitation_defects)
    print("Done! Created Heavy_Report_v1.xlsx")

if __name__ == "__main__":
    export_test()
