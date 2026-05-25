# PROJECT_CONTEXT.md

# 项目名称

Novel Reader（Python + Kivy 安卓小说阅读器原型）

---

# 当前阶段

当前阶段：

`MVP Readable State`

当前状态：

- Runtime Architecture 已冻结
- 已完成基础端到端阅读流
- 当前重点是稳定完善 MVP 阅读体验

当前不是：

- 重做 runtime
- 新增 manager
- 重构 EventBus
- 修改 lifecycle 架构

---

# 技术栈

- Python 3.11
- Kivy 2.x
- SQLite
- requests
- trafilatura
- threading
- ThreadPoolExecutor

目标平台：

Android（非 root）

---

# 当前架构

## 1. Data Layer

目录：

- `database/models.py`
- `database/db_manager.py`
- `database/dao/book_dao.py`
- `database/dao/chapter_dao.py`

特点：

- SQLite WAL
- Row factory
- `check_same_thread=False`
- 短生命周期连接
- `books` / `chapters` 两张核心表

约束：

- DAO 仅负责 CRUD
- UI 不允许直接访问 DAO

## 2. Service Layer

目录：

- `services/book_service.py`
- `services/chapter_service.py`
- `services/crawler_service.py`
- `services/download_manager.py`

职责：

- 书籍信息与阅读进度
- 本地章节读取 / 落库 / 轻量缓存
- 章节列表 / 正文抓取
- 后台预加载与任务状态事件

约束：

- 不写 UI 逻辑
- 不引用 Screen
- 不直接写 Kivy 组件

## 3. Core Layer

目录：

- `core/event_bus.py`
- `core/app_state.py`
- `core/task_state.py`
- `core/lifecycle_manager.py`
- `core/runtime_healthcheck.py`
- `core/cold_restore.py`

说明：

- Runtime 层已冻结
- 仅维护，不继续扩展

`AppState` 当前承载：

- `current_book`
- `current_chapter`
- `active_downloads`
- `crawler_status`
- `reading_theme`
- `font_size`

## 4. UI Adapter Layer

目录：

- `ui/adapters/event_adapter.py`
- `ui/adapters/screen_state_binding.py`
- `ui/adapters/ui_dispatcher.py`

职责：

- EventBus 到 UI 的主线程切换
- Screen bind/unbind
- 安全后台回调落回 UI

约束：

- Screen 不直接订阅底层 EventBus
- 所有 UI 更新必须在主线程

## 5. UI Screens

目录：

- `ui/screens/bookshelf_screen.py`
- `ui/screens/search_screen.py`
- `ui/screens/reader_screen.py`

当前能力：

- 书架浏览
- 搜索并进入阅读
- 阅读章节正文
- 进度恢复
- 字体 / 日夜模式
- 后续章节预加载

---

# 当前 MVP 功能

已完成：

- Bookshelf -> Reader 导航
- Search -> Reader 导航
- Reader -> Bookshelf 返回
- App 启动恢复上次阅读
- 自动保存阅读进度
- 本地章节优先
- 后台预加载后续章节
- 基础错误处理 UI

---

# 运行方式

推荐环境：

- `my_project_test`

启动主应用：

```powershell
& 'D:\GTMC_User_Profiles\huaibin_guo\AppData\Local\miniconda3\envs\my_project_test\python.exe' -m novel_reader.app
```

启动 runtime 验证工具：

```powershell
& 'D:\GTMC_User_Profiles\huaibin_guo\AppData\Local\miniconda3\envs\my_project_test\python.exe' -m novel_reader.runtime_demo_app
```

---

# 当前数据流

UI Screen  
↓  
UI Adapter Layer  
↓  
AppState / EventBus  
↓  
Services  
↓  
Crawler / DAO / Network

---

# 当前约束

禁止：

- 新增 runtime 层
- 新增 manager
- 重构 EventBus
- 修改 lifecycle 架构
- UI 线程网络请求
- UI 直接访问 DAO
- UI 直接访问 crawler
- `universal_crawler` 写成巨型 if/else
- 全局 SQLite 长连接

---

# AI 接手建议

后续 AI 接手时优先关注：

1. `reader_screen.py`
2. `search_screen.py`
3. `bookshelf_screen.py`
4. `chapter_service.py`
5. `download_manager.py`

优先做：

- MVP 可用性和稳定性优化
- 目录页 / 章节列表体验
- 真机验证

不要先做：

- 新 runtime 系统
- 新 manager
- 大规模架构重写
