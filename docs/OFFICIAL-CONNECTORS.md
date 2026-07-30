# 官方连接器资格审计与无写入请求

## 定位

Phase 5.4A 只建立官方能力的资格报告和请求契约，不调用任何真实平台接口。

```text
六平台内容包 + 发布计划
        ↓
官方资格事实
        ↓
Qualification Report
        ↓
无凭据 Official Request
        ↓
execution_enabled=false
external_write_performed=false
```

`eligible` 只表示前置事实齐全，不表示连接器已启用，也不表示可以写入。

## 当前官方方向

### Halo / 珩小派网站

Halo REST API 提供 Console 文章创建、正文更新和发布等接口。当前请求契约只规划：

1. `POST /apis/api.console.halo.run/v1alpha1/posts`
2. `PUT /apis/api.console.halo.run/v1alpha1/posts/{name}/content`

`publish` 不在 Phase 5.4A 范围。

官方参考：

- `https://api.halo.run/`
- `https://docs.halo.run/`

### 微信公众号

微信公众号草稿箱的新增草稿流程使用服务端 `draft/add`。正文图片和封面素材需要先通过官方素材流程取得对应引用。

当前契约只规划素材映射检查和新增草稿，不执行：

- 获取 `access_token`
- 上传正文图片
- 上传封面素材
- 创建草稿
- 群发或发布

官方参考：

- `https://developers.weixin.qq.com/doc/offiaccount/Draft_Box/Add_draft.html`

### 抖音

抖音图文能力需要应用权限和用户 OAuth 授权。官方文档给出的图文流程包含图片上传与 `/image_text/create/`，单次图片数量上限为 30 张。

当前契约只生成：

1. OAuth 与 `video.create` Scope 前置检查；
2. 图片上传步骤计划；
3. 图文创建步骤计划；
4. 每一步的用户可感知确认要求。

不获取 Token、不上传图片、不创建内容。

官方参考：

- `https://open.douyin.com/platform/resource/docs/openapi/video-management/douyin/publish-img/upload/`
- `https://open.douyin.com/platform/resource/docs/openapi/video-management/douyin/publish-img/publish/`

### 小红书

小红书官方分享开放平台属于客户端 SDK / App 唤起能力，不是服务端静默发布接口。接入需要登记应用、平台审核和 AppKey。

官方 FAQ 还说明标题和文案自动填充存在限制，因此 HXP 不能把 Share SDK 视为完整文案同步。当前契约只规划：

1. SDK 注册资格；
2. 小红书 App 安装检查；
3. 1–18 张有序图片；
4. 唤起官方发布工具；
5. 用户在 App 内继续核对和发布。

官方参考：

- `https://agora.xiaohongshu.com/doc`
- `https://agora.xiaohongshu.com/doc/qa`

## 配置

官方能力配置位于：

```text
config/official-connectors.json
```

全部连接器默认：

```json
{
  "enabled": false,
  "execution_enabled": false,
  "external_write_performed": false,
  "supports_public_publish": false
}
```

配置只保存环境变量名称，不保存 Secret 或 Token 值。

## 生成资格报告

准备本地事实文件：

```json
{
  "connectors": {
    "halo-official-draft": {
      "account_ref": "hxp-site-production",
      "facts": {
        "site_base_url": true,
        "halo_version": true,
        "account_ref": true,
        "token_scope_verified": true
      },
      "capabilities": {
        "create_post": true,
        "update_post_content": true,
        "status_lookup": true
      },
      "assets": {
        "cover_asset_verified": true,
        "body_assets_verified": true
      },
      "credential_references": {
        "HXP_HALO_BASE_URL": true,
        "HXP_HALO_PAT": true
      }
    }
  }
}
```

该文件只能写资格事实和环境变量引用状态，不能写真实密钥。

```bash
python scripts/inspect_official_connector_qualifications.py \
  --facts qualification-facts.json \
  --generated-at 2026-07-30T15:00:00+08:00 \
  --report-slug owner-audit \
  --output connector-qualification.json
```

状态：

- `unknown`：资料不足；
- `eligible`：事实齐全，但真实执行仍关闭；
- `blocked`：已确认不满足官方条件；
- `simulated`：只完成离线 Fixture。

## 构建无写入请求

请求必须绑定内容包、发布计划条目、文案哈希和按顺序排列的图片哈希。

```bash
python scripts/build_official_connector_request.py \
  --qualification-report connector-qualification.json \
  --connector-id halo-official-draft \
  --packages content-packages.json \
  --plan publication-plan.json \
  --material-mapping material-mapping.json \
  --generated-at 2026-07-30T15:10:00+08:00 \
  --expires-at 2026-07-30T16:10:00+08:00 \
  --output official-request.json
```

输出仍固定为：

```json
{
  "execution_enabled": false,
  "external_write_performed": false
}
```

请求中只包含环境变量名称，不包含任何环境变量值。

## 硬阻断

- HTTP 或非官方 Origin；
- Secret、Token、Authorization、Cookie 或 Session 值；
- 内容包和发布计划的平台不一致；
- 文案哈希漂移；
- 图片哈希或顺序漂移；
- 请求已过期或有效期反向；
- 微信素材映射未完成；
- 抖音图片不在 1–30 张范围；
- 小红书图片不在 1–18 张范围；
- 资格为 `unknown` 或 `blocked`；
- 试图启用公开发布。

## 下一阶段

Phase 5.4B 只有在主理人明确提供平台、账号引用、安全环境配置和动作授权后，才选择一个连接器进行真实草稿试验。优先顺序：

1. Halo / 珩小派网站草稿；
2. 微信公众号草稿箱；
3. 抖音官方 OAuth 图文；
4. 小红书官方 Share SDK。
