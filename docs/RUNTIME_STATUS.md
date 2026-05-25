# RUNTIME_STATUS.md

## Status

**Runtime Stable Candidate**

当前阶段用于冻结 `Runtime Architecture Validation` 的已完成能力、验证结论和剩余风险。

## 1. 当前已完成 runtime 能力

- EventBus：线程安全、弱引用 listener、异步 emit
- AppState：集中状态管理、可序列化快照、事件广播
- UI Adapter Layer：UI 主线程调度、screen bind/unbind、自动 cleanup
- Screen Runtime：`BaseScreen` 生命周期绑定与解绑
- DownloadManager：任务跟踪、事件流、取消/失败状态广播
- Runtime Demo：事件风暴、生命周期切换、弱引用释放、下载状态流验证
- Lifecycle Simulation Layer：pause/resume、background/foreground、network disconnect/restore
- Runtime Healthcheck：listener leak、event storm、task backlog、screen state、app state consistency

## 2. 已验证项目

- Screen 生命周期切换可运行
- EventBus 到 UI adapter 的主线程派发链路可运行
- 弱引用 listener 可释放
- AppState 更新可被 Screen 感知
- DownloadManager 状态事件可观察
- 生命周期模拟事件可观察
- AppState 持久化快照与 restore 事件可触发

## 3. 已知风险

- 当前验证主要基于桌面环境模拟，不是 Android 真机结论
- 生命周期恢复仍是“热恢复模拟”，不是进程被杀后的冷恢复
- DownloadManager 目前只验证事件流与 backlog，不验证真实后台继续下载
- Event storm 验证关注的是事件送达，不是 UI 帧率或渲染性能

## 4. Android 风险

- Android `Activity` 可能在后台被系统暂停、销毁或重建
- 桌面最小化不等于 Android `pause/stop/destroy`
- 后台网络切换、线程调度、OpenGL 上下文恢复与桌面差异较大
- listener、Screen 实例、Clock 回调在真机恢复路径上可能失效或重复注册

## 5. 当前 PASS/FAIL 项

- PASS：弱引用 listener 释放检查
- PASS：runtime_demo_app 构建与 screen 初始化
- PASS：生命周期模拟事件发射
- PASS：healthcheck 接口返回 PASS/FAIL 结果
- PASS：AppState 快照持久化与 restore 事件触发
- PASS：自动化验证入口 `All` / `Lifecycle Auto`
- FAIL：尚未验证 Android 真机生命周期一致性
- FAIL：尚未验证进程重建后的 Screen/Task 冷恢复

## 6. 当前未解决问题

- 无 Android 真机 `Activity` 生命周期实测数据
- 无进程被系统杀死后的 AppState 恢复方案验证
- 无任务持久化层，DownloadManager 无法跨进程恢复
- 无 Screen 重建后的精确 restore contract

## 7. listener leak 验证结果

- 已有基于 baseline/current listener 总数差值的 leak 检查
- Screen 生命周期压力测试后可做 listener 数量回归比较
- 当前结论：在现有 demo 路径下，listener cleanup 机制具备可验证性

## 8. event storm 验证结果

- 已支持批量异步发射 `runtime.storm`
- 已统计 `expected` 与 `received`
- 当前结论：event storm 链路可做 PASS/FAIL 判定
- 未覆盖：真机高负载下 UI 卡顿、掉帧、恢复后事件堆积

## 9. lifecycle simulation 能力

- `simulate_pause()`
- `simulate_resume()`
- `simulate_background()`
- `simulate_foreground()`
- `simulate_network_disconnect()`
- `simulate_network_restore()`

所有模拟：

- 事件驱动
- 输出日志
- 发射 lifecycle 事件
- 可由 runtime_demo_app 自动串联执行

## 10. AppState restore 能力

- 生命周期进入 pause/background 时会保存 AppState 快照
- resume/foreground 时会发射 `lifecycle.restore`
- healthcheck 可检查当前 AppState 与快照是否一致
- 当前能力属于“内存内热恢复模拟”，不等于磁盘持久化恢复

## 11. 当前 runtime_demo_app 能做什么

- 手动切换 `bookshelf/search/probe`
- 触发 AppState 更新验证
- 触发 event storm 验证
- 触发 Screen lifecycle 压力测试
- 触发 weak listener cleanup 验证
- 触发 DownloadManager 事件流验证
- 手动模拟 pause/resume/background/foreground/network off/on
- 自动执行 lifecycle recovery validation
- 汇总 PASS/FAIL 结果并输出运行日志

## 12. 下一阶段建议

- 增加 Android 真机生命周期观测日志
- 增加冷恢复模拟：重建 ScreenManager 与 binding 后再做 restore 校验
- 增加任务持久化设计，为 DownloadManager 恢复做准备
- 定义 AppState restore contract，明确哪些字段必须恢复，哪些可延迟恢复
- 在真机环境验证 listener restore、screen restore、network restore 的一致性

