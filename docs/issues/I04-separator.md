# I04 · 人声分离适配器

Epic: E02  
depends_on: I02

## 合同

包装 `audio-separator`。默认 KTV 模型 `UVR_MDXNET_KARA_2`（去主唱、留和声），质量档可选 BS-RoFormer。  
无模型时标记 `degraded`，使用明确的立体声中置衰减降级，并在 job 日志写出原因。

## 验收

- 适配器单测：成功路径写 vocals/instrumental；失败不得静默当成功。
- 降级路径必须带 `degraded=true`。
