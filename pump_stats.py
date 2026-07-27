import pandas as pd

def pump_stats():
    print("Reading Excel...")
    df = pd.read_excel("Heavy_LEV-2_4k_defult_2026-06-28_17-02-16.xlsx", sheet_name="Raw_Telemetry")
    
    pump_history = []
    current_state = None
    start_row = 0
    
    for _, row in df.iterrows():
        r_idx = int(row['Row_Index'])
        pump_v = row['Pump']
        state = 'ON' if pump_v > 2.0 else 'OFF'
        
        if current_state is None:
            current_state = state
            start_row = r_idx
        elif state != current_state:
            duration = (r_idx - start_row) * 0.1
            pump_history.append({
                'state': current_state,
                'start': start_row,
                'end': r_idx - 1,
                'duration': round(duration, 1)
            })
            current_state = state
            start_row = r_idx
            
    if current_state is not None:
        last_idx = int(df.iloc[-1]['Row_Index'])
        duration = (last_idx - start_row + 1) * 0.1
        pump_history.append({
            'state': current_state,
            'start': start_row,
            'end': last_idx,
            'duration': round(duration, 1)
        })
        
    on_count = sum(1 for p in pump_history if p['state'] == 'ON')
    print(f"Total times Pump turned ON: {on_count}\n")
    print("Pump Sequence (From first ON):")
    
    started = False
    for p in pump_history:
        if p['state'] == 'ON':
            started = True
            print(f"PUMP ON  : Row {p['start']} -> {p['end']} | Duration: {p['duration']}s")
        elif p['state'] == 'OFF' and started:
            print(f"PUMP OFF : Row {p['start']} -> {p['end']} | Duration: {p['duration']}s")

if __name__ == "__main__":
    pump_stats()
