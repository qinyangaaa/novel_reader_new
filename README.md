# Novel Reader

Python + Kivy 的安卓向小说阅读器原型。

当前状态：

- Runtime Architecture 已冻结
- 当前阶段为 `MVP Readable State`
- 已具备基础端到端阅读流程

## 当前架构

### Data Layer

- `database/models.py`
- `database/db_manager.py`
- `database/dao/book_dao.py`
- `database/dao/chapter_dao.py`

职责：

- SQLite 初始化
- 短生命周期连接
- 书籍 / 章节 CRUD

### Service Layer

- `services/book_service.py`
- `services/chapter_service.py`
- `services/crawler_service.py`
- `services/download_manager.py`

职责：

- 书籍与阅读进度
- 本地章节读取与落库
- 章节列表 / 正文抓取
- 后台预加载与下载事件流

### Core Runtime

- `core/event_bus.py`
- `core/app_state.py`
- `core/task_state.py`
- `core/lifecycle_manager.py`
- `core/runtime_healthcheck.py`
- `core/cold_restore.py`

说明：

- Runtime 层已冻结
- 不再继续扩展 runtime / lifecycle / healthcheck

### UI Layer

- `ui/adapters/event_adapter.py`
- `ui/adapters/screen_state_binding.py`
- `ui/adapters/ui_dispatcher.py`
- `ui/screens/bookshelf_screen.py`
- `ui/screens/search_screen.py`
- `ui/screens/reader_screen.py`

职责：

- 主线程 UI 调度
- Screen 生命周期绑定
- 书架 / 搜索 / 阅读页

## 当前 MVP 功能

- 书架展示本地书籍
- 搜索书籍并进入阅读页
- 阅读章节正文
- 上一章 / 下一章切换
- 自动保存阅读进度
- App 启动恢复上次阅读
- 日夜模式切换
- 字体大小调整
- 后台预加载后续章节
- 基础错误提示：
  - 搜索失败
  - 网络失败
  - 预加载失败

## 运行方式

推荐解释器：

- `D:\GTMC_User_Profiles\huaibin_guo\AppData\Local\miniconda3\envs\my_project_test\python.exe`

启动 MVP App：

```powershell
& 'D:\GTMC_User_Profiles\huaibin_guo\AppData\Local\miniconda3\envs\my_project_test\python.exe' -m novel_reader.app
```

启动 Runtime Demo：

```powershell
& 'D:\GTMC_User_Profiles\huaibin_guo\AppData\Local\miniconda3\envs\my_project_test\python.exe' -m novel_reader.runtime_demo_app
```

## 后续任务

- 优化 `SearchScreen` 结果表现和可用性
- 优化 `ReaderScreen` 的章节切换体验
- 增加本地章节列表 / 目录视图
- 增加真实 Android 真机验证
- 规划离线阅读与任务持久化，但不要先扩 runtime 层

## AI 接管说明

后续 AI 接手时应遵守：

- 不新增 runtime 层
- 不新增 manager
- 不重构 EventBus
- 不修改 lifecycle 架构
- UI 不直接访问 DAO
- UI 更新继续走现有 adapter / `ui_dispatcher`

