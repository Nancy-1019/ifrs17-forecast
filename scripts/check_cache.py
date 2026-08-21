# -*- coding: utf-8 -*-
import os, json
CACHE=os.path.join("D:/IFRS17预测模型/ifrs17-system","data_input","runtime_cache","calc_result_cache.json")
result=json.load(open(CACHE,encoding='utf-8'))['result']
for r in result['existingBusinessPredict']:
    if r.get('预测间隔')==1 and '交强险_直保或分入_现有业务&0' in str(r.get('合同组ID','')):
        for c in ['输出_已发生未决赔款负债_预期现金流','输出_间接理赔费用负债_预期现金流',
                  '输出_未到期责任负债_非亏损部分','输出_保险合同收入','输出_赔付与费用_已发生未决赔款负债提转差_预期现金流',
                  '期末现值_未决赔款现金流_期初','期末现值_未决赔款现金流_期末','当期确认比例','获取现金流摊销比例']:
            print(f"  {c}: {r.get(c)}")
        break
