import pandas as pd
from logic_monitor import LogicMonitor

def check_pump():
    print("Reading Excel...")
    df = pd.read_excel("Heavy_LEV-2_4k_defult_2026-06-28_17-02-16.xlsx", sheet_name="Raw_Telemetry")
    
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
        
    logic_mon = LogicMonitor()
    logic_mon.set_program("Heavy", level="LEV-2", soak_option="No Soak", delay_option="None")
    
    for row in raw_data_log:
        logic_mon.process_row(row)
        
    summary = logic_mon.get_summary()
    test_cases = summary['test_cases']
    
    pump_defects = [tc for tc in test_cases if "Pump" in tc.get("Test_Name", "")]
    
    print("=== PUMP DEFECTS FOUND ===")
    if not pump_defects:
        print("None!")
    for p in pump_defects:
        print(f"[{p.get('Row_Index')}] {p.get('Test_Name')}: {p.get('Technical_Evidence')}")
    print("=== END ===")

if __name__ == "__main__":
    check_pump()
