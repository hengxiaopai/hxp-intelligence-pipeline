# HXP Collectors

## 目标

Phase 2.2 提供两个轻量采集适配器：

- RSS / Atom：适合 arXiv 等结构化 Feed；
- HTML Index：只解析语义化 `<article>` 区块，适合官方 Newsroom 与 Changelog 列表页。

采集器的职责是保存“原始响应 + 发现条目”，不是判断新闻是否真实、重要或值得发布。所有发现结果仍需进入候选事件规范化、去重与编辑审核。

## 默认安全模式

`collect.py` 默认不访问网络，必须提供本地 fixture：

```bash
python scripts/collect.py \
  --registry-id registry-arxiv-cs-ai \
  --input-file tests/fixtures/arxiv-cs-ai.xml \
  --output-dir /tmp/hxp-rss
```

HTML 示例：

```bash
python scripts/collect.py \
  --registry-id registry-github-changelog \
  --input-file tests/fixtures/github-changelog.html \
  --output-dir /tmp/hxp-html
```

只有显式传入 `--live` 才会尝试一次实时请求：

```bash
python scripts/collect.py \
  --registry-id registry-arxiv-cs-ai \
  --live \
  --output-dir data/raw/$(date +%F)
```

## 实时访问硬限制

实时采集必须同时满足：

1. `registry_id` 存在于 `config/sources.json`；
2. 来源处于 `active=true`；
3. `collection_method` 为 `rss` 或 `html_index`；
4. `access_policy` 不是 `manual_only` 或 `official_api_only`；
5. 来源不需要登录或认证；
6. URL 使用 HTTPS 默认 443 端口；
7. DNS 不解析到 localhost、私网、链路本地、保留或组播地址；
8. `robots.txt` 允许该 User-Agent 访问；
9. 响应不发生重定向；
10. Content-Type 在允许列表内；
11. 正文不超过 2 MiB；
12. 请求在超时时间内完成。

当前实现关闭环境代理，不绕过登录、付费墙、反爬、robots 或服务条款。

## 为什么不自动跟随重定向

自动跟随重定向会扩大 SSRF 与跨域访问风险，也可能把注册表中的官方地址悄悄带到第三方域名。当前版本采用失败关闭策略：来源若返回 301/302，应先人工确认最终地址，再更新注册表。

## 原始快照

每次成功采集生成两个文件：

```text
snapshot-YYYYMMDDTHHMMSSZ-source.html|xml
snapshot-YYYYMMDDTHHMMSSZ-source.json
```

JSON 符合 `schemas/raw-snapshot.schema.json`，包含：

- 来源注册 ID；
- 请求 URL 与最终 URL；
- 采集方式与 fixture/live 模式；
- UTC 获取时间；
- HTTP 状态、Content-Type 与允许保留的响应头；
- SHA-256 哈希与字节数；
- 原始正文路径；
- 解析器版本；
- 发现条目；
- 解析警告。

快照不会保存 Cookie、Authorization、Set-Cookie 等敏感头。

## 发现条目

RSS 与 HTML 适配器统一输出：

```json
{
  "external_id": "...",
  "title": "...",
  "url": "https://...",
  "published_at": "2026-07-28T12:00:00Z",
  "summary": "...",
  "authors": [],
  "tags": []
}
```

发现条目不是 `candidate.json`。下一阶段将负责：

- 规范化公司、模型、产品与证券实体；
- 提取事件动作、对象与日期；
- 创建来源记录；
- 生成稳定事件指纹；
- 执行 3/7/30 天去重；
- 决定进入审核、延续跟踪或淘汰池。

## HTML 解析边界

通用 HTML 适配器只解析 `<article>`，并从以下语义元素提取数据：

- `h1`–`h4`：标题；
- `a[href]`：条目链接；
- `time[datetime]`：发布时间；
- `p`、`.summary`、`.excerpt`、`.description`：摘要；
- `.author`、`.byline`：作者；
- `.tag`、`.category`、`.topic`：标签。

页面没有语义化 `<article>` 时，快照会产生警告而不是广泛抓取所有链接。需要稳定支持的站点应新增专用解析器和 fixture。

## 离线测试

```bash
python -m unittest discover -s tests -v
```

CI 只使用 `tests/fixtures/`，不会访问外网。测试覆盖：

- RSS 条目与日期解析；
- HTML 相对链接、作者与标签解析；
- 快照写入与 Schema 校验；
- `manual_only` 实时阻断；
- localhost、私网和云元数据地址阻断；
- 未注册来源阻断。

## 故障处理

- `manual_only`：改用人工复核，不修改代码绕过；
- 重定向：人工确认最终官方 URL 后更新注册表；
- robots 不允许：停止自动访问；
- Content-Type 不符：检查是否被登录页、验证码或错误页替代；
- HTML 无条目：保留快照警告，为该来源增加专用 parser；
- 正文超限：降低采集范围或改用官方 Feed/API，不提高无限制上限。
