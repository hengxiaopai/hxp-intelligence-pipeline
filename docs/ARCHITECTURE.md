# HXP Intelligence Pipeline Architecture

## 总体架构

```
Signal Sources
      ↓
Collector
      ↓
Normalizer
      ↓
Dedup Engine
      ↓
Editorial Review
      ↓
Visual Production
      ↓
Quality Check
      ↓
Asset Archive
```

## 四阶段生产链

### Phase 1 情报采集

输入：AI、开源、产业链、社媒、产品、设计、政策等信号。

输出：结构化候选事件。

### Phase 2 编辑审核

负责：

- 来源验证
- 置信度判断
- 最近主题去重
- 价值评分
- 内容方向判断

### Phase 3 视觉生产

原则：

AI 负责主题视觉；模板负责文字布局。

输出：

- 9:16 海报
- 汇总海报
- 多平台适配素材

### Phase 4 归档

保存：

- briefing.md
- briefing.json
- sources.json
- poster assets
- manifest.json
