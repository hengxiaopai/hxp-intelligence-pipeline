# 珩小派品牌资产接入

本目录只记录正式品牌资产的接入规范，不存放或分发字体文件。

## 正式 Logo 要求

视觉流水线需要主理人批准的珩小派 Logo 文件，支持：

- SVG（优先）
- PNG
- JPG / JPEG

正式文件建议命名为：

```text
assets/brand/hengxiaopai-logo-approved.svg
```

Logo 必须来自既有品牌资产，不得由流水线临时绘制、重构或猜测。正式渲染时缺少该文件会硬阻断。

## 测试资产

`tests/fixtures/hxp-test-logo.svg` 仅用于 CI 和预览，图中明确标记 `HXP TEST`，不得用于公开发布，也不代表正式品牌 Logo。

## 字体

仓库不提交字体文件。PNG 导出使用操作系统已安装的 CJK 字体，优先顺序为：

1. Noto Sans CJK SC
2. Source Han Sans SC
3. Microsoft YaHei
4. PingFang SC

找不到可用中文字体时，正式栅格化会给出明确错误并停止。
