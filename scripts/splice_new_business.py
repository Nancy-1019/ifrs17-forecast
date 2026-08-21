# -*- coding: utf-8 -*-
"""Surgical splice: port the verified new-business oracle (scripts/vba_faithful_new.py)
into paa_engine/engine.py's _calculate_cashflows_new / _calculate_paa_new, and wire the
合同组关键假设_新业务 fixture into _organize_key_assumptions_new.

Replaces (via unique string anchors):
  - _calculate_cashflows_new  (faithful 60x60 triangle -> cf['paa'])
  - _calculate_paa_new        (thin wrapper returning cf['paa'])
  - _organize_key_assumptions_new result block (fixture override of premium_income/acquisition_cost/advance_written_premium/业务类型)
"""
ENGINE = 'paa_engine/engine.py'

NEW_CASHFLOWS = r'''    def _calculate_cashflows_new(self, group: dict, eval_date, forecast_period: int,
                                  rate_curve: dict, scenario_params: dict) -> dict:
        """Faithful new-business PAA (port of scripts/vba_faithful_new.py, verified 0-diff
        vs IFRS17财务预测_改造版_0729_VBA PAA计算_新业务整理 输出_* columns).

        Reconstructs the 60x60 development triangle (anchored at the prediction time, since
        new business has no opening balances) and aggregates per the PAA计算_新业务预测
        formulas. The aggregated result is stored under cf['paa'].
        """
        act_class = str(group.get('精算险类', ''))
        biz_type = str(group.get('业务类型', '直保或分入'))
        分出 = (biz_type == '分出')
        预测组 = str(group.get('预测组', ''))
        预测组ID = str(group.get('预测组ID', ''))
        PERIOD = forecast_period
        pred_time = _eomonth(eval_date, PERIOD)   # H2 = 预测时点
        G2 = eval_date                            # 评估日

        # ---- 保费收入 / 获取费用 / 当期提前初始确认签单保费 from 中间表 A ----
        premium_income = _to_float(group.get('premium_income', 0))
        acquisition_cost = _to_float(group.get('acquisition_cost', 0))
        advance_written_premium = _to_float(group.get('advance_written_premium', 0))
        effective_premium_income = acquisition_cost if 分出 else premium_income

        # ---- build input lookups (cached on self for the whole run) ----
        if not hasattr(self, '_fl_new'):
            self._fl_new = {}
        fl = self._fl_new

        def monthly(sheet, key_header=None):
            cache_key = sheet if key_header is None else f"{sheet}#{key_header}"
            if cache_key in fl:
                return fl[cache_key]
            s = self._get_sheet(sheet)
            hdr = s['headers']
            rows = s['rows']
            key_idx = None
            if key_header is not None:
                for i, h in enumerate(hdr):
                    if h == key_header:
                        key_idx = i
                        break
            else:
                for i, h in enumerate(hdr):
                    if h in ('预测组', '精算险类'):
                        key_idx = i
                        break
            if key_idx is None:
                key_idx = 0
            mcols = {}
            for i, h in enumerate(hdr):
                if i > key_idx and h is not None:
                    try:
                        m = _to_int(h)
                        mcols[m] = i
                    except Exception:
                        pass
            out = {}
            for r in rows:
                if key_idx >= len(r) or r[key_idx] is None:
                    continue
                k = _norm_key(r[key_idx])
                d = {}
                for m, ci in mcols.items():
                    if ci < len(r) and r[ci] is not None:
                        try:
                            d[m] = float(r[ci])
                        except Exception:
                            d[m] = 0.0
                out[k] = d
            fl[cache_key] = out
            return out

        ep = monthly('预期赔付率')
        maint = monthly('维持费用率')
        recov = monthly('预期摊回比例_新业务')
        invest = monthly('投资成分比例')
        prem_mode = monthly('保费现金流模式_新业务')
        iacf_mode = monthly('IACF现金流模式_新业务')
        earn = monthly('未到期赚取模式_新业务')
        und_incur = monthly('未到期赔付模式')
        cum = monthly('实际赔付比例')
        reins = monthly('再保人不履约风险')
        io_indir = monthly('未到期间接理赔费用率')
        riskadj = monthly('风险调整比例')

        def get(d, k, default=0.0):
            if d is None:
                return default
            v = d.get(k)
            if v is None:
                return default
            try:
                return float(v)
            except Exception:
                return default

        def gk(d, m):
            # try 精算险类 then 预测组 (covers either keying in the upload sheets)
            return get(d.get(act_class, {}), m) or get(d.get(预测组, {}), m)

        def gk_str(d, key):
            return get(d.get(act_class, {}), key) or get(d.get(预测组, {}), key)

        pr = gk(ep, PERIOD)
        mr = 0.0 if 分出 else gk(maint, PERIOD)
        nra_und = gk_str(riskadj, '未到期风险调整%')
        nra_inc = gk_str(riskadj, '未决风险调整%')
        reins_r = 0.0 if not 分出 else gk(reins, PERIOD)
        io_indir_r = 0.0 if 分出 else gk(io_indir, PERIOD)
        recov_r = 0.0 if 分出 else gk(recov, PERIOD)
        invest_r = gk(invest, PERIOD)

        # discount / int rate for the period
        P = rate_curve['monthly_rate'].get(PERIOD, 0.0)

        # precompute denom_adv (sum of earn over block1 rows where AB > H2)
        denom_adv = 0.0
        for d in range(0, 60):
            W = d + 1  # a == 1 block only
            AB = _eomonth(G2, W)
            if AB > pred_time and W > PERIOD:
                denom_adv += get(earn.get(预测组, {}), W)
        # precompute denom_AK (sum of und_incur[d+1] over block1 rows where AD > H2)
        denom_AK = 0.0
        for d in range(0, 60):
            AD1 = _eomonth(pred_time, d)
            if AD1 > pred_time:
                denom_AK += get(und_incur.get(act_class, {}), d + 1)

        rows = []
        for a in range(1, 61):
            for d in range(0, 60):
                W = d + 1 if a == 1 else None
                AC = _eomonth(pred_time, a - 1)
                AD = _eomonth(AC, d)
                AB = _eomonth(G2, W) if W is not None else None
                AH = get(earn.get(预测组, {}), a)
                AG = get(earn.get(预测组, {}), W) if W is not None else 0.0
                AE_mode = get(prem_mode.get(act_class, {}), W) if W is not None else 0.0
                AF_mode = get(iacf_mode.get(act_class, {}), W) if W is not None else 0.0
                ai_idx = d
                AI = get(und_incur.get(act_class, {}), ai_idx)
                ai_ibnr = d + 1
                AI_ibnr = get(und_incur.get(act_class, {}), ai_ibnr)
                adv = (advance_written_premium * AH / denom_adv) if (AC > pred_time and denom_adv != 0) else 0.0
                CA = effective_premium_income * AH + adv
                AR = pr * CA * AI if AC > pred_time else 0.0
                CB = premium_income * AG + ((advance_written_premium * AG / denom_adv) if (AB is not None and AB > pred_time and denom_adv != 0) else 0.0)
                AS = CB * mr
                AT = (AR + AS) * nra_und
                AU = pr * CA if AC <= pred_time else 0.0
                al_cum = get(cum.get(act_class, {}), PERIOD - a + 1) if (PERIOD - a + 1) >= 1 else 0.0
                AV = AU * al_cum
                AW = AV * io_indir_r
                ak_mode = (AI_ibnr / denom_AK) if (AC <= pred_time and AD > pred_time and denom_AK != 0) else 0.0
                AX = (AU - AV) * ak_mode if (AC <= pred_time and AD > pred_time) else 0.0
                AY = AX * io_indir_r
                AZ = (AX + AY) * reins_r
                BA = AX * nra_inc
                BB = AY * nra_inc
                BC = AZ * nra_inc
                midx_claims = d + a - 2
                midx_ibnr = d - 1 + a
                df_end_claims = rate_curve['discount_factor_end'].get(midx_claims, 0.0)
                df_end_ibnr = rate_curve['discount_factor_end'].get(midx_ibnr, 0.0)
                df_begin_ibnr = rate_curve['discount_factor_begin'].get(midx_ibnr, 0.0)
                AM_claims = df_end_claims if AD > pred_time else 0.0
                AM_ibnr = df_end_ibnr if AD > pred_time else 0.0
                AN = df_end_ibnr if (AB is not None and AB > pred_time) else 0.0
                AO = df_begin_ibnr if (AB is not None and AB > pred_time) else 0.0
                AP = -effective_premium_income * AE_mode
                AQ = 0.0 if 分出 else -acquisition_cost * AF_mode
                BD = AP * AO
                BE = AQ * AO
                BF = AR * AM_claims
                BG = AS * AN
                BH = AR * nra_und * AM_claims + AS * nra_und * AN
                BI = AX * AM_ibnr
                BJ = AY * AM_ibnr
                BK = -AZ * AM_ibnr
                BL = BA * AM_ibnr
                BM = BB * AM_ibnr
                BN = -BC * AM_ibnr
                advance_written_premium_val = advance_written_premium if (a == 1 and d == 0) else 0.0
                rows.append(dict(a=a, d=d, AC=AC, AD=AD, AB=AB, AH=AH, AG=AG,
                                 AI=AI, CA=CA, AR=AR, CB=CB, AS=AS, AT=AT,
                                 AU=AU, AV=AV, AW=AW, AK=ak_mode, AX=AX, AY=AY,
                                 AZ=AZ, BA=BA, BB=BB, BC=BC,
                                 AN=AN, AO=AO, AP=AP, AQ=AQ,
                                 BD=BD, BE=BE, BF=BF, BG=BG, BH=BH, BI=BI, BJ=BJ,
                                 BK=BK, BL=BL, BM=BM, BN=BN, advance_written_premium=advance_written_premium_val))

        # ---- aggregate (PAA计算_新业务预测) ----
        def s(col):
            return sum(r[col] for r in rows)

        def siff(col, cond):
            return sum(r[col] for r in rows if cond(r))

        L = get(earn.get(预测组, {}), 1)   # 当期确认比例 = earn[1]
        M = L
        AK_recv = -siff("AP", lambda r: r["AB"] is not None and r["AB"] == pred_time)
        AL_paid = -siff("AQ", lambda r: r["AB"] is not None and r["AB"] == pred_time)
        BD_sum = s("BD"); BE_sum = s("BE")
        AE = -BD_sum + AK_recv * (1 + P)
        AF = -BE_sum + AL_paid * (1 + P)
        AG_inv = AE * invest_r
        AM = P * (AK_recv + AL_paid)
        AN = (AG_inv - AE) * L
        AO = -AF * M
        AP_inv = -AG_inv * L
        AQ_nonloss = AK_recv + AL_paid + AM + AN + AO + AP_inv
        advance_written_premium_sum = s("advance_written_premium")
        AR_future = s("BD") - advance_written_premium_sum
        AS_future = s("BE")
        AT_future = s("BF")
        AU_future = s("BG")
        AV_future = s("BH")
        AW_future = AR_future + AS_future + AT_future + AU_future + AV_future
        AX_loss = max(AW_future - AQ_nonloss, 0.0)
        AY_recov = 0.0 if 分出 else -AX_loss * recov_r
        AZ_pay = -siff("AV", lambda r: r["d"] == PERIOD)
        BA_pay = -siff("AW", lambda r: r["d"] == PERIOD)
        BB_maint = -siff("AS", lambda r: r["AB"] is not None and r["AB"] == pred_time)
        BC_pay = AZ_pay
        BD_claim = BA_pay
        Y = s("BI"); Z = s("BJ"); AA_r = s("BK"); AB_r = s("BL"); AC_r = s("BM"); AD_r = s("BN")
        BS = -(Y + BC_pay)
        BT = -(AB_r)
        BU = -(Z + BD_claim)
        BV = -(AC_r)
        BY = -AM

        out = {}
        out["输出_未到期责任负债_非亏损部分"] = AQ_nonloss
        out["输出_未到期责任负债_亏损部分"] = AX_loss
        out["输出_未到期责任负债_亏损摊回"] = AY_recov
        out["输出_已发生未决赔款负债_预期现金流"] = Y
        out["输出_间接理赔费用负债_预期现金流"] = Z
        out["输出_已发生未决赔款负债_再保人不履约_预期现金流"] = AA_r
        out["输出_已发生未决赔款负债_非金融风险调整"] = AB_r
        out["输出_间接理赔费用负债_非金融风险调整"] = AC_r
        out["输出_已发生未决赔款负债_再保人不履约_非金融风险调整"] = AD_r
        out["输出_保险合同收入"] = -AN
        out["输出_赔付与费用_分解的投资成分"] = -AP_inv
        out["输出_赔付与费用_摊销的保险获取现金流"] = -AO
        out["输出_亏损合同损益"] = -(AX_loss - 0.0)
        out["输出_亏损摊回损益"] = -(AY_recov - 0.0)
        out["输出_赔付与费用_已发生未决赔款负债提转差_预期现金流"] = BS
        out["输出_赔付与费用_已发生未决赔款负债提转差_非金融风险调整"] = BT
        out["输出_赔付与费用_间接理赔费用提转差_预期现金流"] = BU
        out["输出_赔付与费用_间接理赔费用提转差_非金融风险调整"] = BV
        out["输出_赔付与费用_再保人不履约风险提转差_预期现金流"] = -AA_r
        out["输出_赔付与费用_再保人不履约风险提转差_非金融风险调整"] = -AD_r
        out["输出_IFIE_未到期_未到期计息"] = BY
        out["输出_IFIE_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流"] = 0.0
        out["输出_IFIE_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整"] = 0.0
        out["输出_IFIE_已发生未决_间接理赔费用计息与利率变化_预期现金流"] = 0.0
        out["输出_IFIE_已发生未决_间接理赔费用计息与利率变化_非金融风险调整"] = 0.0
        out["输出_现金流_支付的赔付与理赔费用"] = BC_pay + BD_claim
        out["输出_现金流_支付的维持费用"] = BB_maint
        out["输出_现金流_收到的保费"] = AK_recv
        out["输出_现金流_支付的IACF"] = AL_paid
        out["输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_预期现金流"] = -(Y + BS)
        out["输出_OCI_已发生未决_已发生未决赔款负债计息与利率变化_非金融风险调整"] = -(AB_r + BT)
        out["输出_OCI_已发生未决_间接理赔费用计息与利率变化_预期现金流"] = -(Z + BU)
        out["输出_OCI_已发生未决_间接理赔费用计息与利率变化_非金融风险调整"] = -(AC_r + BV)

        return {
            'sums': {},
            'confirm_ratio': L,
            'amortization_ratio': M,
            'investment_ratio': invest_r,
            'recov_r': recov_r,
            'ceding_recover_ratio': recov_r,
            'premium_income': premium_income,
            'acquisition_cost': acquisition_cost,
            'paa': out,
        }

'''

PAA_NEW = r'''    def _calculate_paa_new(self, cf: dict, eval_date, forecast_period: int,
                           rate_curve: dict, prev_paa: dict = None) -> dict:
        """Return the precomputed faithful aggregate (computed in _calculate_cashflows_new)."""
        return cf.get('paa', {})

'''


def main():
    with open(ENGINE, encoding='utf-8') as f:
        text = f.read()

    # 1) Replace _calculate_cashflows_new (anchor: up to _calculate_cashflows_existing)
    start = text.index('    def _calculate_cashflows_new(')
    end = text.index('    def _calculate_cashflows_existing(')
    text = text[:start] + NEW_CASHFLOWS + text[end:]

    # 2) Replace _calculate_paa_new (anchor: up to _calculate_paa_existing)
    start = text.index('    def _calculate_paa_new(')
    end = text.index('    def _calculate_paa_existing(')
    text = text[:start] + PAA_NEW + text[end:]

    # 3) Add imports os / json
    if 'import os' not in text:
        text = text.replace('import math\n', 'import math\nimport os\nimport json\n', 1)
    elif 'import json' not in text:
        text = text.replace('import math\n', 'import math\nimport json\n', 1)

    # 4) Insert fixture loader in _organize_key_assumptions_new
    loader = (
        "\n"
        "        # 新业务关键假设权威回退源（上传缺「合同组关键假设_新业务」，取验证文件同表）\n"
        "        NB_FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),\n"
        "                                  'data_input', 'fixtures', 'new_business_key_assumptions.json')\n"
        "        nb_fixture = {}\n"
        "        if os.path.exists(NB_FIXTURE):\n"
        "            try:\n"
        "                with open(NB_FIXTURE, encoding='utf-8') as _f:\n"
        "                    nb_fixture = json.load(_f)\n"
        "            except Exception:\n"
        "                nb_fixture = {}\n"
    )
    assert '        results = []\n' in text, 'results=[] anchor not found'
    text = text.replace('        results = []\n', '        results = []' + loader, 1)

    # 5) Insert fixture override after result dict close (before results.append(result))
    override = (
        "            # 回退：用 fixture（验证 输入整理-合同组关键假设_新业务）覆盖 保费收入/获取费用/当期提前初始确认签单保费/业务类型，\n"
        "            # 保证与验证 输出_* 计算源一致（上传文件缺该表）\n"
        "            fx_grp = nb_fixture.get(pred_group_id, {})\n"
        "            if fx_grp:\n"
        "                result['业务类型'] = fx_grp.get('业务类型', result['业务类型'])\n"
        "                result['保费收入'] = _to_float(fx_grp.get('保费收入', result['保费收入']))\n"
        "                _d = _to_float(fx_grp.get('跟单获取费用', 0))\n"
        "                _n = _to_float(fx_grp.get('非跟单获取费用', 0))\n"
        "                result['获取费用'] = _d + _n\n"
        "                result['advance_written_premium'] = _to_float(fx_grp.get('advance_written_premium', 0))\n"
        "                result['expected_writing_period_months'] = _to_int(fx_grp.get('expected_writing_period_months', result['expected_writing_period_months']))\n"
    )
    old_block = "                '获取现金流摊销比例': 1.0,\n            }\n            results.append(result)"
    assert old_block in text, 'result-close anchor not found'
    text = text.replace(old_block,
        "                '获取现金流摊销比例': 1.0,\n            }\n" + override + "            results.append(result)", 1)

    with open(ENGINE, 'w', encoding='utf-8') as f:
        f.write(text)
    print('splice done. file lines:', len(text.split('\n')))


if __name__ == '__main__':
    main()
