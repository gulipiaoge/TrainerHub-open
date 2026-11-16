# Third-Party Notices

TrainerHub 使用以下第三方开源组件。本文件列出各组件的许可信息，
以满足各项许可证的署名与告知要求。

项目自身代码采用 [MIT License](LICENSE)。

---

## 直接依赖

### PyWebView — BSD 3-Clause License
- 主页：https://github.com/r0x0r/pywebview
- 用途：提供 Python → 系统 WebView（Windows 上为 Edge WebView2）的桌面窗口桥接
- 许可证：BSD 3-Clause
- 版权声明：Copyright (c) 2013-2024, Raman Kalpakam and contributors

### Requests — Apache License 2.0
- 主页：https://github.com/psf/requests
- 用途：HTTP 请求（在线检索与文件下载）
- 许可证：Apache License 2.0
- 版权声明：Copyright 2019 Kenneth Reitz

### Python.NET — MIT License
- 主页：https://github.com/pythonnet/pythonnet
- 用途：PyWebView 在 Windows 上的 .NET / CLR 互操作支持（由 PyWebView 间接依赖）
- 许可证：MIT
- 版权声明：Copyright (c) 2013-2023 Igor Novgorodov and contributors

---

## 间接依赖

以下组件由上述直接依赖间接引入，同样以宽松型许可证发布：

| 组件 | 版本 | 许可证 |
|---|---|---|
| bottle | 0.13.4 | MIT |
| certifi | 2026.10.23 | MPL-2.0 |
| cffi | 2.1.1 | MIT |
| charset-normalizer | 3.5.2 | MIT |
| clr-loader | 0.3.1 | MIT |
| idna | 3.20 | BSD-3-Clause |
| pythonnet | 3.2.1 | MIT |
| pycparser | 3.12 | BSD-3-Clause |
| typing_extensions | 4.16.0 | Python Software Foundation License |
| urllib3 | 2.8.0 | MIT |

---

## 运行时组件（不随本仓库分发）

### Microsoft Edge WebView2 Runtime
- 由系统预装或从微软官方渠道安装，遵循其独立的许可条款
- 下载：https://developer.microsoft.com/microsoft-edge/webview2/

---

## 说明

上述各许可证均为宽松型（permissive）许可，允许在保留版权声明与许可文本的前提下
使用、修改与分发，包括用于闭源商业产品。本项目未修改任何第三方组件的源代码。

完整的第三方许可文本，请查阅各组件在其发行包内的 `LICENSE` / `COPYING` 文件，
或访问上述对应主页。
