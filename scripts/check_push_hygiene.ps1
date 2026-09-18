$ErrorActionPreference = "Stop"

$forbiddenPaths = git ls-files | rg '(^|/)(superpowers|\.codex|\.pytest_cache|\.ruff_cache|\.venv|\.vscode|logs)(/|$)|\.log$'
if ($forbiddenPaths) {
    Write-Error "版本库包含本地工具、缓存、日志或环境文件：$forbiddenPaths"
    exit 1
}

$forbiddenMarkdown = git --no-pager grep -n -I -i -E 'OpenAI|Codex|ChatGPT|Claude|LLM|large language|language model|prompt|agentic|superpowers|人工智能|大模型|生成式|机器生成|AI[ ：_-]' -- '*.md'
if ($forbiddenMarkdown) {
    Write-Error "Markdown 包含不应提交的工作流表述：$forbiddenMarkdown"
    exit 1
}

$absolutePaths = git --no-pager grep -n -I -P '(?<![A-Za-z])[A-Z]:\\[A-Za-z]|(?<![A-Za-z])[A-Z]:/[A-Za-z]' --
if ($absolutePaths) {
    Write-Error "版本库包含本机绝对路径：$absolutePaths"
    exit 1
}

$licenseText = git --no-pager grep -n -I -i -F -e ('Serial' + ' number') -e ('Licensed' + ' to') -e ('Authorization' + ' code') -e ('License' + ' code') --
if ($licenseText) {
    Write-Error "版本库包含许可证信息。"
    exit 1
}

Write-Output "推送前工作区规范检查通过。"
