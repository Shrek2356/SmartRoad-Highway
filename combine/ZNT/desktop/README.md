# 路安智巡桌面端

源码启动入口为应用根目录的 `start-platform.bat`。桌面 EXE 负责窗口、前端代理和服务生命周期，检测与业务代码从本软件工作目录加载。

构建使用 `build-desktop-exe.bat`；产物为 `../desktop-dist/SmartRoad-Inspection.exe`，品牌与版本来自 `version_info.txt`。先构建 `pc-admin`，再重新打包桌面程序。完整交付包可使用 `pack-release.ps1` 创建，首次以演示模式启动。

使用已有 Python 环境运行 `smoke_road_api.py --image <道路图片> --record <新记录路径>` 可验证真实模型上传、知识库、报告和业务入库。该测试不打开原生窗口，也不测算法准确率。

安装程序使用独立的道路产品标识，避免覆盖历史工地软件。源文件名 `installer/SiteSafe.iss` 保留以兼容构建命令，安装界面与程序名已使用道路名称。未经重新构建的旧 ZIP、EXE 或安装包不代表最新代码。
