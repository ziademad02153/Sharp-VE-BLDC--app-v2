# SHARP HIL REPORTING MODULE - VERSION 3.0
import pandas as pd
import xlsxwriter
from datetime import datetime

class ExcelExporter:
    def __init__(self, filename):
        self.filename = filename

    def export(self, raw_data, summary_data, defect_data=None):
        """
        raw_data     : list of telemetry rows
        summary_data : list of sequence/timing verification dicts (from logic_monitor)
        defect_data  : list of FAIL-only agitation defect dicts (from agitation_analyzer)
        """
        if isinstance(summary_data, dict) and 'test_cases' in summary_data:
            summary_data = summary_data['test_cases']

        # ── Transform raw telemetry ───────────────────────────────────────────
        transformed_raw = []
        for row in raw_data:
            row_idx   = row[0]
            telemetry = row[2:]
            total_ds  = row_idx - 1
            h         = total_ds // 36000
            remaining = total_ds % 36000
            m         = remaining // 600
            remaining = remaining % 600
            s         = remaining // 10
            ms        = (remaining % 10) / 10.0
            transformed_raw.append([row_idx, h, m, s, ms] + telemetry)

        columns_raw = [
            "Row_Index", "H", "Min", "Sec", "ms", "Motor_RPM", "Cold_V", "Hot_V",
            "Softener", "GearMotor", "Motor_V", "Pump"
        ]
        if len(transformed_raw) > 0 and len(transformed_raw[0]) == 13:
            columns_raw.append("Door")
        df_raw     = pd.DataFrame(transformed_raw, columns=columns_raw)
        # ── Merge and filter defects ──────────────────────────────────────────
        defects = []
        if summary_data:
            for item in summary_data:
                sev = 'High' if item.get('Status') == 'FAIL' else 'Low'
                pri = 'High' if item.get('Status') == 'FAIL' else 'Low'
                item.setdefault('Severity', sev)
                item.setdefault('Priority', pri)
                defects.append(item)
                    
        if defect_data:
            defects.extend(defect_data)

        # Sort combined defects chronologically
        def get_start_row(defect):
            ri = str(defect.get("Row_Index", ""))
            if ri == "N/A" or not ri:
                return 0
            try:
                return int(ri.split("-")[0])
            except Exception:
                return 0
                
        defects.sort(key=get_start_row)

        df_defects = pd.DataFrame(defects) if defects else pd.DataFrame()

        with pd.ExcelWriter(self.filename, engine='xlsxwriter') as writer:
            df_raw.to_excel(writer, sheet_name="Raw_Telemetry", index=False)

            workbook = writer.book

            # ── Shared formats ────────────────────────────────────────────────
            header_fmt = workbook.add_format({
                'bold': True, 'font_size': 14,
                'bg_color': '#0052CC', 'font_color': 'white',
                'align': 'center', 'valign': 'vcenter', 'border': 1
            })
            stat_hdr_fmt  = workbook.add_format({'bold': True, 'font_size': 11, 'bg_color': '#F4F7F9'})
            wrap_fmt      = workbook.add_format({'text_wrap': True, 'valign': 'top', 'border': 1})
            pass_fmt      = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100', 'bold': True, 'border': 1, 'align': 'center'})
            fail_fmt      = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006', 'bold': True, 'border': 1, 'align': 'center'})
            skipped_fmt   = workbook.add_format({'bg_color': '#D6E4F0', 'font_color': '#1F4E79', 'bold': True, 'border': 1, 'align': 'center'})
            warning_fmt   = workbook.add_format({'bg_color': '#FFF2CC', 'font_color': '#7F6000', 'bold': True, 'border': 1, 'align': 'center'})
            default_fmt   = workbook.add_format({'valign': 'top', 'border': 1})
            critical_fmt  = workbook.add_format({'bg_color': '#FF0000', 'font_color': 'white', 'bold': True, 'border': 1, 'align': 'center'})
            high_fmt      = workbook.add_format({'bg_color': '#FF7043', 'font_color': 'white', 'bold': True, 'border': 1, 'align': 'center'})
            medium_fmt    = workbook.add_format({'bg_color': '#FFF176', 'font_color': '#333300', 'bold': True, 'border': 1, 'align': 'center'})
            id_fmt        = workbook.add_format({'bold': True, 'font_color': '#0052CC', 'border': 1, 'align': 'center'})

            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # ══════════════════════════════════════════════════════════════════
            # SHEET 2 : Raw Data Defect Report
            # ══════════════════════════════════════════════════════════════════
            ws_dfl = workbook.add_worksheet('Raw Data Defect Report')

            DEFECT_COLS = [
                'Defect ID', 'Test Phase / Component', 'Summary of Defect',
                'Severity', 'Priority',
                'Start Row', 'End Row',
                'Expected Result (Specifications)', 'Actual Result (Raw Telemetry)',
                'Delta (Difference)',
                'Technical Evidence (Step-by-Step)'
            ]

            ws_dfl.merge_range(0, 0, 0, len(DEFECT_COLS) - 1,
                'Raw Data Defect Report - Sharp HIL Verification', header_fmt)

            # Stats row
            defect_count   = len(defects)
            critical_count = sum(1 for d in defects if d.get('Severity') == 'Critical')
            high_count     = sum(1 for d in defects if d.get('Severity') == 'High')
            medium_count   = sum(1 for d in defects if d.get('Severity') == 'Medium')

            ws_dfl.write(2, 0, 'Report Date:', stat_hdr_fmt)
            ws_dfl.write(2, 1, current_time)
            ws_dfl.write(3, 0, 'Total Defects:', stat_hdr_fmt)
            ws_dfl.write(3, 1, defect_count, fail_fmt if defect_count > 0 else pass_fmt)
            ws_dfl.write(3, 2, f'Critical: {critical_count}', critical_fmt)
            ws_dfl.write(3, 3, f'High: {high_count}', high_fmt)
            ws_dfl.write(3, 4, f'Medium: {medium_count}', medium_fmt)

            # Column headers at row 5
            hdr_row = 5
            col_hdr_fmt = workbook.add_format({
                'bold': True, 'bg_color': '#1A237E', 'font_color': 'white',
                'border': 1, 'align': 'center', 'valign': 'vcenter', 'text_wrap': True
            })
            for ci, col_name in enumerate(DEFECT_COLS):
                ws_dfl.write(hdr_row, ci, col_name, col_hdr_fmt)

            # Data rows
            for di, defect in enumerate(defects):
                dr     = hdr_row + 1 + di
                def_id = f"DF-{di + 1:03d}"

                # Parse Row_Index into start/end
                ri = str(defect.get('Row_Index', 'N/A'))
                if '-' in ri and ri != 'N/A':
                    parts = ri.split('-')
                    try:
                        start_row_val = int(parts[0])
                        end_row_val   = int(parts[1])
                    except Exception:
                        start_row_val = ri
                        end_row_val   = ri
                else:
                    start_row_val = ri
                    end_row_val   = ri

                sev = defect.get('Severity', 'Medium')
                pri = defect.get('Priority', 'Medium')

                sev_fmt_map = {'Critical': critical_fmt, 'High': high_fmt, 'Medium': medium_fmt}
                sev_fmt     = sev_fmt_map.get(sev, medium_fmt)
                pri_fmt_map = {'High': high_fmt, 'Medium': medium_fmt, 'Low': skipped_fmt}
                pri_fmt     = pri_fmt_map.get(pri, medium_fmt)

                # Build a short summary from the test name
                test_name = defect.get('Test_Name', '')
                status_val = defect.get('Status', 'FAIL')
                if status_val == 'PASS':
                    summary = f"{test_name} completed successfully."
                else:
                    summary   = f"{test_name} - ON Overrun/Under-run recorded." \
                                if 'ON Time' in test_name else \
                                f"{test_name} - OFF Rest Deficit/Excess recorded." \
                                if 'OFF Time' in test_name else \
                                f"{test_name} deviation detected."

                ws_dfl.write(dr, 0, def_id, id_fmt)
                ws_dfl.write(dr, 1, test_name, default_fmt)
                ws_dfl.write(dr, 2, summary, wrap_fmt)
                ws_dfl.write(dr, 3, sev, sev_fmt)
                ws_dfl.write(dr, 4, pri, pri_fmt)
                ws_dfl.write(dr, 5, start_row_val, default_fmt)
                ws_dfl.write(dr, 6, end_row_val, default_fmt)
                ws_dfl.write(dr, 7, defect.get('Expected_Sec', ''), default_fmt)
                ws_dfl.write(dr, 8, defect.get('Actual_Sec', ''), default_fmt)
                ws_dfl.write(dr, 9, defect.get('Delta_Sec', 'N/A'), default_fmt)
                ws_dfl.write(dr, 10, defect.get('Technical_Evidence', ''), wrap_fmt)

            # Column widths
            ws_dfl.set_column(0, 0, 12)   # Defect ID
            ws_dfl.set_column(1, 1, 35)   # Component
            ws_dfl.set_column(2, 2, 45)   # Summary
            ws_dfl.set_column(3, 3, 12)   # Severity
            ws_dfl.set_column(4, 4, 12)   # Priority
            ws_dfl.set_column(5, 5, 12)   # Start Row
            ws_dfl.set_column(6, 6, 12)   # End Row
            ws_dfl.set_column(7, 7, 20)   # Expected
            ws_dfl.set_column(8, 8, 20)   # Actual
            ws_dfl.set_column(9, 9, 20)   # Delta
            ws_dfl.set_column(10, 10, 100)  # Evidence

            # Row heights for evidence
            for di in range(defect_count):
                ws_dfl.set_row(hdr_row + 1 + di, 80)

            # ── Raw Telemetry column sizing ────────────────────────────────
            ws_raw = writer.sheets['Raw_Telemetry']
            ws_raw.set_column('A:A', 12)
            ws_raw.set_column('B:E', 10)
            ws_raw.set_column('F:M', 12)
