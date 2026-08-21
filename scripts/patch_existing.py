# -*- coding: utf-8 -*-
"""Splice the faithful existing-business PAA into engine.py, replacing the old
_calculate_cashflows_existing and _calculate_paa_existing implementations."""
import os

ENG = os.path.join("D:/IFRS17预测模型/ifrs17-system", "paa_engine", "engine.py")
CF = os.path.join(os.path.dirname(__file__), "new_cf_existing.txt")
PAA = os.path.join(os.path.dirname(__file__), "new_paa_existing.txt")

text = open(ENG, encoding='utf-8').read()
new_cf = open(CF, encoding='utf-8').read()
new_paa = open(PAA, encoding='utf-8').read()

# 1) replace _calculate_cashflows_existing (from its def through the Pattern-helpers comment block)
start = text.index('    def _calculate_cashflows_existing(self, group: dict, eval_date, forecast_period: int,')
end_marker = '    # ============================================================\n    # Pattern lookup helpers'
end = text.index(end_marker)
text = text[:start] + new_cf + '\n' + text[end:]

# 2) replace _calculate_paa_existing (from its def through the Step 6 comment block)
start2 = text.index('    def _calculate_paa_existing(self, cf: dict, eval_date, forecast_period: int,')
end_marker2 = '    # ============================================================\n    # Step 6: Main calculation runner'
end2 = text.index(end_marker2)
text = text[:start2] + new_paa + '\n' + text[end2:]

open(ENG, 'w', encoding='utf-8').write(text)
print("patched engine.py: replaced _calculate_cashflows_existing + _calculate_paa_existing")
