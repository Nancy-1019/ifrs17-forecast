"""Test validate_upload against the Segment B attachment data-version files."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'ifrs17-system'))
from data_input.excel_validator import validate_upload

FILES = [
    ('excel', '手工输入表_附件数据版.xlsx', os.path.join(ROOT, '验证文件', '手工输入表_附件数据版.xlsx')),
    ('dock', '系统对接输入表_附件数据版.xlsx', os.path.join(ROOT, '验证文件', '系统对接输入表_附件数据版.xlsx')),
    ('excel', 'IFRS17财务预测_改造版_开发.xlsx', os.path.join(ROOT, '验证文件', 'IFRS17财务预测_改造版_开发.xlsx')),
    ('dock', 'IFRS17财务预测_改造版_开发.xlsx(附件)', os.path.join(ROOT, '验证文件', 'IFRS17财务预测_改造版_开发.xlsx')),
]

for source, label, path in FILES:
    print("=" * 70)
    print(f"[{source}] {label}")
    if not os.path.exists(path):
        print("  FILE NOT FOUND")
        continue
    with open(path, 'rb') as f:
        data = f.read()
    res = validate_upload(data, source)
    print(f"  success={res['success']}  sheetCount={res['sheetCount']}  totalRows={res['totalRows']}  errors={res['errors']}")
    bad = [name for name, sr in res['sheetResults'].items() if not sr.get('valid')]
    if bad:
        print(f"  INVALID SHEETS ({len(bad)}):")
        for name in bad:
            print(f"    - {name}: {res['sheetResults'][name]['errors'][:3]}")
    else:
        print("  ALL SHEETS VALID")
