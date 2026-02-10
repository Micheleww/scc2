# Market Belief Calibration & Scoring Module

## 作用
1. 将原始市场信念(MarketBeliefRaw)转换为校准后的信念(MarketBeliefCalibrated)
2. 评估信念可信度，输出健康评分(HealthScore)，范围[0,1]
3. 校准是慢变量，信念是快变量
4. 评分仅影响风险预算/权重上限，不直接触发交易

## 核心组件
- BeliefCalibrator: 拟合校准模型，校准实时信念
- BeliefScorer: 评估信念可信度，生成健康评分

## 约束
- fit() 不可在实时路径调用
- calibrate() 不访问未来数据
- scoring 结果仅影响风险参数
