# -*- coding: utf-8 -*-
import sys
sys.path.insert(0, r'D:/IFRS17预测模型/ifrs17-system/data_input')
from excel_specs import SYSTEM_DOCK_SPECS, EXCEL_UPLOAD_SPECS
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# 簡體 -> 繁體 映射（以簡體原文為鍵，繁體為值）
_MAP = {
    # 多字（優先順序：長詞在前）
    '对应关系':'對應關係','关系':'關係','保单':'保單','签单':'簽單','对应':'對應',
    '评估':'評估','预测':'預測','费用':'費用','风险':'風險','现有':'現有',
    '合同组':'合同組','新业务':'新業務','净额':'淨額','结算':'結算','投资成分':'投資成分',
    '风险调整':'風險調整','不履约':'不履約','现金流':'現金流','已发生':'已發生',
    '未决':'未決','赔款':'賠款','理赔':'理賠','负债':'負債','摊销':'攤銷',
    '获取':'獲取','维持':'維持','间接':'間接','提转差':'提轉差','折现':'折現',
    '远期':'遠期','计息':'計息','变化':'變化','预期':'預期','摊回':'攤回',
    '赔付':'賠付','假设':'假設','理赔费用':'理賠費用','违约':'違約','实际':'實際',
    '费用类':'費用類','输入项':'輸入項','手续费':'手續費','复效':'復效','准备金':'準備金',
    '参数':'參數','关键':'關鍵','余额':'餘額','曲线':'曲線','用于':'用於',
    '基础':'基礎','系统':'系統','压力':'壓力','增长':'增長','变动':'變動',
    '外汇':'外匯','影响':'影響','黄金':'黃金','应收':'應收','减值':'減值',
    '跟单':'跟單','非跟单':'非跟單','组合':'組合','确认':'確認','体系':'體系',
    '业务':'業務','获':'獲','摊':'攤','赔':'賠','险':'險','费':'費','类':'類',
    '预':'預','测':'測','财':'財','务':'務','调':'調','间':'間','数':'數','据':'據',
    '压':'壓','参':'參','单':'單','签':'簽','变':'變','动':'動','违':'違','黄':'黃',
    '关':'關','汇':'匯','影':'影','响':'響','减':'減','净':'淨','确':'確','认':'認',
    '线':'線','远':'遠','于':'於','业':'業','复':'復','效':'效','获':'獲','损':'損',
    '准':'準','备':'備','实':'實','较':'較','对':'對','应':'應','现':'現','组':'組',
    '购':'購','责':'責',    '结':'結','算':'算',
}
_MAP.update({'时':'時','点':'點','权':'權','资':'資','产':'產','写':'寫',
             '开':'開','维':'維','计':'計','亏':'虧','余':'餘','类':'類',
             '组':'組','购':'購','获':'獲','损':'損','备':'備','务':'務'})
_MULTI = [k for k in _MAP if len(k) > 1]
# 單字鍵（排除已含於多字者，避免重複）
_MULTISET = set(_MULTI)
_SINGLE = {k: v for k, v in _MAP.items() if len(k) == 1 and k not in _MULTISET}

def t(s):
    if not isinstance(s, str):
        return s
    for k in _MULTI:
        if k in s:
            s = s.replace(k, _MAP[k])
    out = []
    for ch in s:
        out.append(_SINGLE.get(ch, ch))
    return ''.join(out)

DESC_TRAD = {
    '模型基础参数配置':'模型基礎參數配置',
    '合同组与合同组合映射关系':'合同組與合同組合映射關係',
    '压力情景参数配置':'壓力情景參數配置',
    '新业务与现有业务合同组拼接关系':'新業務與現有業務合同組拼接關係',
    '各合同组新业务生效保费（按月）':'各合同組新業務生效保費（按月）',
    '各合同组新业务签单保费（按月）':'各合同組新業務簽單保費（按月）',
    '各精算险类新增应收保费减值（按月）':'各精算險類新增應收保費減值（按月）',
    '各合同组新业务跟单获取费用或净额结算比例（按月）':'各合同組新業務跟單獲取費用或淨額結算比例（按月）',
    '各精算险类新业务非跟单获取费用比例（按月）':'各精算險類新業務非跟單獲取費用比例（按月）',
    '新业务保费现金流分配模式':'新業務保費現金流分配模式',
    '新业务IACF现金流分配模式':'新業務IACF現金流分配模式',
    '新业务未到期责任赚取模式':'新業務未到期責任賺取模式',
    '新业务预期摊回比例（按月）':'新業務預期攤回比例（按月）',
    '各合同组预期赔付率假设':'各合同組預期賠付率假設',
    '各精算险类维持费用率假设':'各精算險類維持費用率假設',
    '未到期间接理赔费用率':'未到期間接理賠費用率',
    '未决赔款间接理赔费用率':'未決賠款間接理賠費用率',
    '各精算险类风险调整比例参数':'各精算險類風險調整比例參數',
    '再保人违约风险调整参数':'再保人違約風險調整參數',
    '各合同组投资成分分解比例（按月）':'各合同組投資成分分解比例（按月）',
    '未到期赔付分配模式':'未到期賠付分配模式',
    '未决赔款赔付分配模式':'未決賠款賠付分配模式',
    '实际赔付比例数据':'實際賠付比例數據',
    '费用类输入项（调整手续费、复效保费、手续费及佣金支出等）':'費用類輸入項（調整手續費、復效保費、手續費及佣金支出等）',
    '其他输入参数（提取保费准备金、利息收入、投资收益等）':'其他輸入參數（提取保費準備金、利息收入、投資收益等）',
    '现有业务合同组关键假设参数':'現有業務合同組關鍵假設參數',
    '系统期初各合同组余额表（45字段）':'系統期初各合同組餘額表（45欄位）',
    '现有业务保费现金流分配模式':'現有業務保費現金流分配模式',
    '现有业务IACF现金流分配模式':'現有業務IACF現金流分配模式',
    '现有业务未到期责任赚取模式':'現有業務未到期責任賺取模式',
    '现有业务预期摊回比例':'現有業務預期攤回比例',
    '现有业务提前确认保单（按月）':'現有業務提前確認保單（按月）',
    'CAS25财务报表实际数':'CAS25財務報表實際數',
    '各合同组初始确认利率曲线（月度远期利率）':'各合同組初始確認利率曲線（月度遠期利率）',
    '即期利率曲线（用于折现）':'即期利率曲線（用於折現）',
}

HEADER_FILL = PatternFill('solid', fgColor='1677FF')
HEADER_FONT = Font(name='Arial', bold=True, color='FFFFFF', size=11)
TITLE_FONT = Font(name='Arial', bold=True, size=16, color='1677FF')
SUB_FONT = Font(name='Arial', bold=True, size=12, color='222222')
CELL_FONT = Font(name='Arial', size=10, color='222222')
ALT_FILL = PatternFill('solid', fgColor='F5F8FF')
THIN = Side(style='thin', color='D0D5DD')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(vertical='center', wrap_text=True)
CENTER = Alignment(horizontal='center', vertical='center', wrap_text=True)

wb = Workbook()
ws = wb.active
ws.title = '說明'
ws.sheet_view.showGridLines = False
ws['A1'] = '新準則預測模型 — 數據需求說明'
ws['A1'].font = TITLE_FONT
ws['A2'] = '（繁體中文版 · 依據系統手工輸入表與系統輸入表權威定義整理）'
ws['A2'].font = Font(name='Arial', size=10, italic=True, color='667085')

rows = [
    ('', ''),
    ('一、文件目的', ''),
    ('', '本說明彙整「新準則預測模型」所需的全部數據輸入項，區分「手工輸入表（Excel 上傳）」與「系統輸入表（系統對接）」兩大渠道，供數據提供方依表填報。'),
    ('', '本工作簿共三張工作表：① 說明（本表，含填報約定與目錄）；② 手工輸入表明細（25 張表）；③ 系統輸入表明細（10 張表）。'),
    ('', ''),
    ('二、數據輸入渠道', ''),
    ('手工輸入表', '由業務/精算人員透過 Excel 上傳介面填報，共 25 張工作表，涵蓋基本資訊、新業務假設、新業務現金流模式、新業務比率假設及其他輸入項。'),
    ('系統輸入表', '由周邊系統對接自動寫入，共 10 張工作表，涵蓋現有業務假設、期初數據、現有業務現金流模式、財務報表與利率曲線。'),
    ('', ''),
    ('三、通用欄位與填報約定', ''),
    ('評估時點', '模型評估基準日，格式 YYYY-MM-DD（如 2025-12-31），所有表均含此欄。'),
    ('更新日期', '數據最近更新日期，格式 YYYY-MM-DD，手工/系統表多數含有。'),
    ('預測組', '模型最小計量單元標識（由原「合同組ID」體系遷移而來），用於拼接新業務與現有業務。'),
    ('精算險類', '精算口徑險類分類（如壽險、意外險等），多數比率/現金流表以此分組。'),
    ('業務類型', '區分新業務/現有業務等業務標籤。'),
    ('數據類型', '標識數據性質（如模式、比例等），現金流模式表多數含有。'),
    ('預測維度', '合併/單體等維度標識。'),
    ('60 個月度數值欄', '標註「60月數值」的表，除文字欄位外含第1月~第60月共 60 個月度數值欄（部分表以 1..60 命名）。'),
    ('模式類（加總＝1）', '標註「加總＝1」的現金流模式表，每一資料列的 60 個月數值加總須等於 1（分配權重）。'),
    ('比率類', '比率假設表（如預期賠付率、維持費用率等）按月填報比率值，多數含 60 個月度欄。'),
    ('', ''),
    ('四、工作表目錄', ''),
    ('手工輸入表（25 張）', '、'.join(t(n) for n in EXCEL_UPLOAD_SPECS.keys())),
    ('系統輸入表（10 張）', '、'.join(t(n) for n in SYSTEM_DOCK_SPECS.keys())),
    ('', ''),
    ('五、填報注意事項', ''),
    ('1', '版本一致：上傳檔案欄位順序須與本說明及系統校驗規範一致，數值列數以總數寬鬆匹配。'),
    ('2', '模式加總：現金流模式表每行 60 月數值之和必須等於 1，否則校驗失敗。'),
    ('3', '月度欄：60 月數值欄對應預測期第1月~第60月，請勿遺漏或錯位。'),
    ('4', '預測組體系：自 v5.9.10 起統一使用「預測組」標識，舊「合同組ID」欄位已於現金流模式表移除。'),
    ('5', '期初餘額表：系統期初餘額表含 45 個欄位（v5.9.9 移除 4 個 IFIE「計息」列之「計息」、移除末列「減值」；v5.9.10 移除「簽單保費_提前初始確認」）。'),
    ('6', '上傳校驗：系統依 excel_specs.py 進行表頭與數值列數校驗，建議先以小樣本驗證再全量上傳。'),
]
r = 4
for a, b in rows:
    is_sec = bool(a) and not b and a[0] in '一二三四五六'
    ws.cell(row=r, column=1, value=a).font = SUB_FONT if is_sec else CELL_FONT
    c = ws.cell(row=r, column=2, value=b)
    c.font = CELL_FONT; c.alignment = WRAP
    r += 1
ws.column_dimensions['A'].width = 22
ws.column_dimensions['B'].width = 110

def build_detail(sheet_name, specs_dict, channel):
    sh = wb.create_sheet(sheet_name)
    sh.sheet_view.showGridLines = False
    headers = ['序號', '工作表名稱', '輸入渠道', '類別', '欄位序號', '欄位名稱', '屬性', '說明']
    for ci, h in enumerate(headers, 1):
        c = sh.cell(row=1, column=ci, value=h)
        c.fill = HEADER_FILL; c.font = HEADER_FONT; c.alignment = CENTER; c.border = BORDER
    for ci, w in enumerate([6, 28, 12, 14, 8, 48, 16, 52], 1):
        sh.column_dimensions[get_column_letter(ci)].width = w
    sh.freeze_panes = 'A2'
    row = 2; seq = 0
    for sheet_n, spec in specs_dict.items():
        tn = t(sheet_n); cat = t(spec.category)
        desc = DESC_TRAD.get(spec.description, t(spec.description))
        for hi, hcol in enumerate(spec.headers, 1):
            seq += 1
            vals = [seq, tn, channel, cat, hi, t(hcol), '文字欄', desc if hi == 1 else '']
            for ci, v in enumerate(vals, 1):
                cc = sh.cell(row=row, column=ci, value=v)
                cc.font = CELL_FONT; cc.border = BORDER
                cc.alignment = CENTER if ci in (1,3,4,5,7) else WRAP
                if row % 2 == 0: cc.fill = ALT_FILL
            row += 1
        if spec.numeric_cols:
            seq += 1
            attr = '60月數值·加總=1' if spec.sum_to_one else '60月數值'
            vals = [seq, tn, channel, cat, '-',
                    '第1月 ~ 第%d月（共%d個月度數值欄）' % (spec.numeric_cols, spec.numeric_cols),
                    attr, desc]
            for ci, v in enumerate(vals, 1):
                cc = sh.cell(row=row, column=ci, value=v)
                cc.font = CELL_FONT; cc.border = BORDER
                cc.alignment = CENTER if ci in (1,3,4,5,7) else WRAP
                if row % 2 == 0: cc.fill = ALT_FILL
            row += 1
    return sh

build_detail('手工輸入表明細', EXCEL_UPLOAD_SPECS, '手工')
build_detail('系統輸入表明細', SYSTEM_DOCK_SPECS, '系統')

out = r'D:/IFRS17预测模型/數據需求說明_繁體.xlsx'
wb.save(out)
print('SAVED', out)
