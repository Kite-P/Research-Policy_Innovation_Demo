# CNIPA 免费专利数据协议

## Source decision

正式撤销 Google Patents BigQuery 作为本研究 2020—2024 年专利来源。公开 metadata 未能可靠支持目标年份，因此不再要求 Google Cloud authentication。首选来源改为国家知识产权局知识产权数据资源公共服务系统及其专利检索与分析系统。

本阶段只完成接口准备，不注册、不登录、不下载专利、不绕过验证码，也不运行专利相关回归。

## Time and entity scope

- primary application year: 2020—2024;
- 2025: coverage audit only;
- entity scope: `listed_entity_only`;
- included names: listed legal entity name and verified historical legal name;
- excluded by default: short name, stock abbreviation, subsidiary, fuzzy name and unverified alias.

## Query protocol

查询由公司法定全称组成，名称首尾空白被删除，重复项删除，使用 UTF-8 字节序确定性升序。多个名称以 ` OR ` 连接，不使用通配符。默认 pilot 参数为每批最多 20 个名称、最多 1500 个字符；实际网页长度限制须在合法访问后重新记录。

## Export fields

至少保存以下字段：

`申请号`、`申请日`、`公开（公告）号`、`公开（公告）日`、`申请人（专利权人）`、`发明名称`、`专利类型/文献类型`、`IPC`。

系统提供时一并保存申请人邮编。无需下载 PDF 全文。

## Local parser output

`read_cnipa_export` 支持 XLSX 和 XML，并标准化为：

`application_number`、`application_date`、`publication_number`、`publication_date`、`applicant_raw`、`patent_title`、`patent_type_raw`、`ipc_raw`。

专利类型优先使用 CNIPA 导出字段定义。无法从明确字段判断时输出 `unknown`，不根据公开号末尾的 A、B、U 字符自动猜测发明或实用新型。

## Audit requirements

未来人工导出后必须记录来源页面、导出时间、字段字典、查询批次、下载文件校验值和覆盖情况；不得记录账号、密码、token、cookie 或本机绝对路径。
