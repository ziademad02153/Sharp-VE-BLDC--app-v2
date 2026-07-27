import pandas as pd

def check_spins():
    df = pd.read_excel('Heavy_New_Baseline.xlsx', sheet_name='Raw Data Defect Report')
    spins = df[df['Test_Name'].str.contains('Spin', na=False)]
    for _, r in spins.iterrows():
        print(f"Test: {r['Test_Name']}")
        print(f"Status: {r['Status']}")
        print(f"Evidence:\n{r['Technical_Evidence']}")
        print("---")

if __name__ == "__main__":
    check_spins()
