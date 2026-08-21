"""IFRS17 PAA (Premium Allocation Approach) Calculation Engine.

Based on the Excel model 'IFRS17财务预测_改造版_0727.xlsx' and VBA code
ProcessAllBusinessCashFlows.

Calculation flow:
1. Scenario selection -> apply stress parameters
2. Input organization -> join contract groups, patterns, rates
3. Interest rate curve processing -> discount factors
4. Cashflow calculation -> monthly development triangle per contract group
5. PAA prediction -> aggregate into LRC/LIC/revenue/expense
6. Summary -> combine new + existing business
"""
from .engine import PAAEngine, CalculationResult

__all__ = ['PAAEngine', 'CalculationResult']
