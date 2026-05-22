# Live2D 模型放置说明

将 Live2D Cubism 4 模型文件放入此目录：

```
tent_avatar.model3.json   # 模型配置文件
*.moc3                    # 模型本体
*.png                     # 纹理贴图
*.physics3.json           # 物理设置（可选）
*.userData3.json          # 用户数据（可选）
```

## 获取免费模型

1. **Live2D 官方样本模型**: https://www.live2d.com/download/sample-data/
2. **Hiyori**: 下载后将文件解压到此目录，重命名配置文件为 `tent_avatar.model3.json`

## 注意事项

- 模型路径在代码中配置为 `/ui/models/tent_avatar/tent_avatar.model3.json`
- 如果模型加载失败，前端会自动降级为 CSS 动画占位
- 模型文件较大（通常 5-20MB），首次加载可能需要几秒
