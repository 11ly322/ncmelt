# ncmelt 0.1.1alpha

首个公开 alpha 版本。ncmelt 是一个本地运行的网易云 NCM 转换器，提供 Prism 风格的桌面界面、批量队列和同源 CLI。

官网：https://11ly322.github.io/ncmelt/

## 下载

- `ncmelt-Setup-0.1.1alpha.exe` — Windows 安装器
  - 可选择安装位置
  - 可选创建桌面快捷方式
  - 可选把 `ncmelt` 加入 PATH
  - 不需要管理员权限
- `ncmelt-0.1.1alpha-portable-win64.zip` — 便携版，解压即用
- `SHA256SUMS.txt` — 校验值

发布包已内置 FFmpeg 7.1，无需另行安装。系统要求 Windows 10/11 64 位。

## 本次内容

- NCM 解密，兼容 MP3 / FLAC / AAC / M4A 源，覆盖标准、较高、极高与无损档位。
- 输出格式：MP3、FLAC、WAV、M4A、OGG；每种格式独立音质选择。
- 批量队列、拖拽整个窗口、菜单与快捷键。
- 歌曲名 / 歌手 / 专辑标签和封面写入，可开关。
- 编码后完整解码校验，失败文件单独标记。
- 原 NCM 不修改；默认同名自动编号，可选覆盖。
- CLI：`ncmelt input.ncm -o output.mp3`。
- 安装器与界面图标向 Prism 的扁平几何风格致敬；操作结构参考 Prism 的工作区 / 右侧面板 / 底部状态栏。
- 修正 200% 缩放下顶部菜单与设置/帮助对话框的定位和尺寸。
- 修正隐藏右侧面板后残留空白、对话框内按 Esc 误取消转换、CLI 目录模式 `--overwrite` 无效，以及多输入时把 `-o mix.mp3` 误当目录的问题。
- 0.1.1alpha 版本号、安装器、GitHub Release 与源码同步发布。

## 已知限制

- 仅支持 Windows 10/11 64 位；暂未提供 macOS / Linux 打包。
- 输入仅支持 `.ncm`；普通音频文件请先使用其他工具处理。
- WAV 的标签使用 ID3，部分老播放器可能不显示。
- 程序未做代码签名，Windows SmartScreen 可能要求确认。
- 这是早期 alpha，界面与参数仍可能调整；欢迎通过 Issues 反馈。

## 许可

GPL-3.0。内置 FFmpeg 为 GPL 构建，第三方许可见 `THIRD_PARTY_NOTICES.txt`。

本项目是非官方工具，与网易云音乐无关联。请仅转换自己合法拥有、供个人使用的音乐文件。
