# I01 · 仓库骨架、协议与 vendor 拉取

Epic: E01  
depends_on: —

## 合同

建立 `lov-ktv` 单仓：docs、backend、frontend、android-tv、vendor、scripts、compose。  
`scripts/fetch-vendors.sh` 浅克隆对照项目，GPL 源码不进入发行镜像。

## 验收

- 根 README 写明启动、版权、vendor 许可证。
- `.gitignore` 排除 data、模型、.env、巨大 vendor 对象。
- vendor 脚本可重复执行（已存在则跳过）。
