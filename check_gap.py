
import pandas as pd
df = pd.read_excel('Heavy_LEV-2_4k_defult_2026-06-28_17-02-16.xlsx', sheet_name='Raw_Telemetry')
spins = df[df['Motor_RPM'] > 150].index.tolist()
if spins:
    first_spin = spins[0]
    pump_on = df[(df.index < first_spin) & (df['Pump'] > 0)].index.tolist()
    if pump_on:
        print('Gap from Pump ON to Spin:', (first_spin - pump_on[0])*0.1)
    agitation = df[(df.index < first_spin) & (df['Motor_RPM'] > 50)].index.tolist()
    if agitation:
        print('Gap from Agitation to Spin:', (first_spin - agitation[-1])*0.1)
