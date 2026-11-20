# 见山 · 检验结果迁移核对站

见山质量档案组13人用源批次、字段映射、后台对账运行完成旧字段检验结果的有证据交接。

## 场景与业务
两间实验室共用一套检验库：每间实验室只能查看和修改自己的批次与映射，也只能读取本室的运行、目标行、对账凭据和备份。旧批次在管理员交接前只对管理员可见；管理员在“批次交接”页把整批（含映射、运行、目标行）交给目标实验室。交接只锁定该批次，迁移落库和备份恢复可与交接并发，其他批次照常写入。交接成功后原实验室已登录的会话立即失去查看与下载权限。

上游实验室交付旧字段JSON检验记录；过去人工改字段名、复制到新表并凭总行数判断成功。痛点：非法数值默默丢失、重复委托号覆盖、备份无法证明能恢复。本站登记原始行，字段映射规定类型和必填，Python逐块转换并保留拒绝原行，真实PG目标表一次提交。下游质量复核人下载对账凭据，管理员用JSON逻辑备份恢复本次运行目标并核验。

五业务页：源批次、字段映射、迁移执行（可取消）、差异核对（拒绝区/目标行/备份）、批次交接（管理员）；管理员另有审计和回传恢复。核心实体labs/users/batches/mappings/runs/handovers，另target_rows持久化目标行。全部实体按模型/schema/service/controller/routes/前端api/store/page贯穿。

## 启动与账号
```sh
cp .env.example .env
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```
前端 http://localhost:18248 ，后端 http://localhost:19248/docs ，PostgreSQL localhost:17748（migrate / migratepass / migrationcheck）。结束docker compose down -v --remove-orphans会清除本地数据。

| 角色 | 账号 | 实验室 / 权限 | 典型动作 |
|---|---|---|---|
| admin | admin@migration.local | 全部实验室；全部页面、审计、交接、恢复 | 交接批次、回传备份恢复目标并校验 |
| operator | operator@migration.local | 检验一室；登记/编辑/执行/取消/导出 | 配置本室映射并迁移 |
| viewer | viewer@migration.local | 检验一室；只读、下载本室凭据/备份 | 复核本室拒绝区和真实目标表 |
| operator | operator.b@migration.local | 检验二室；同上仅限本室 | 接收交接后的批次并迁移 |
| viewer | viewer.b@migration.local | 检验二室；只读本室 | 复核二室数据 |

密码统一Migrate2026!；PBKDF2密码与8小时JWT。JWT在每次请求时按账号与批次当前归属判定，因此交接后旧令牌立即失效于该批次。本地演示凭据与JWT密钥，部署前更换。

## 一天的交接剧本
1. 09:00 operator签入，查看见山日班检验结果12条正常记录（本室批次）。
2. 09:05 登记lab-results-20261117.json，委托号JS-20261117-001结果420.1MPa。
3. 09:10 新建shift-20261117批次，复制旧字段；批次自动归入本室。
4. 09:15 字段映射：委托号→sample_code、检测项→test_name、结果→result_value、单位→unit、时间→measured_at，每块4行。
5. 09:20 提交shift-20261117对账，或运行旧字段异常样本查看重复/非法数字/空值/缺列拒绝。
6. 09:25 查看接受/拒绝与分块证据，读取真实PG目标表。
7. 09:30 下载reconciliation-<id>.json与backup-<id>.json，viewer复核。
8. 10:00 admin在“批次交接”页把旧批次交给检验二室；二室会话随即可见整批历史，一室旧会话立即404。回执丢失时用同一回执重试不会重复转室。

seed含两实验室、五账号、三批次（一室正常、两批未领取的异常/空输入）、三映射。固定数值、自然键upsert式补缺，不覆盖用户编辑；连续执行不新增。

## 迁移、校验、取消与恢复
字段类型为text/decimal/datetime。decimal使用Decimal精确转换为6位小数字符串，范围±1e9；无穷/NaN拒绝。空值/空串按required隔离（只有unit可非必填）；缺源字段隔离。时间统一UTC，无时区按Asia/Shanghai(+08:00)解释。自然键sample_code+test_name按规范JSON SHA-256计算；同次运行重复键只接受首条合法记录。每行与全部接受行用排序key/紧凑JSON/UTF-8算SHA-256。拒绝行保存原行和原因。

最多2000源行、每行20列、单元格500字符；每块1-500行。逐块更新进度；取消在块间检查，最终提交前锁定run再次检查，成功目标一次提交；取消/异常没有部分目标数据。后台任务使用简单Redis单消费者；进程崩溃可能留下running状态，需人工复核并新建任务，不自动重试。挂起/运行中的迁移按提交时批次归属落库，交接与执行并发时以最终归属为准。

下载备份为本工具目标行的逻辑JSON快照(version1)，含run_id/rows/row_hashes/checksum，不是pg_dump或物理备份，不含WAL/索引/权限。管理员恢复只允许该运行已保存checksum完全匹配的备份；先核验逐行/总体摘要、schema和自然键，再事务性替换该运行target_rows，回读重新计算摘要并保存recovery记录。篡改、错运行、未完成运行拒绝，恢复事务回滚；不能用任意新数据覆盖目标。

## 实验室隔离与交接
- 批次归属存于batches.lab_id；NULL表示未领取的旧批次，仅管理员可见。映射、运行、目标行不单独存归属，始终经batch_id派生，因此整批历史随批次一并转室。
- 非管理员的所有列表、详情、修改、取消、导出与下载都在服务端按本室过滤，跨室一律404，不泄露存在性。观察员仍只读。
- 管理员交接接口POST /handovers需request_id、batch_id、to_lab_id；request_id唯一，重复请求原样返回首次回执（replayed=true），即使批次后来再次转室也不会回移。同一回执编号用于不同批次返回409。交接失败（如目标实验室不存在）事务回滚，批次保持原归属。
- 并发策略：交接仅锁定单个批次行，映射编辑按批次id升序加锁，恢复仅锁定运行行；锁顺序统一为批次→运行，避免死锁并保证其他批次可写。
- 部署升级：启动时幂等补列（users.lab_id、batches.lab_id）与索引，保留既有数据；历史批次保持未领取状态，由管理员逐一交接。

受控场景演示旧字段到新目标结构的逻辑迁移，数据库真实保存源/映射/目标/对账。不能连接远端数据库，不宣称生产异构迁移或灾备能力。

## 工程与开发
Python3.11/FastAPI/SQLAlchemy/psycopg/Redis/PostgreSQL16，原生HTML/CSS/JS，nginx1.27。exact五服务frontend/backend/worker/db/redis均healthcheck，数据库/Redis/共享产物命名卷；依赖健康后启动。请求追踪、全局错误、JWT授权和业务审计横切。

backend/src按models/schemas/services/controllers/routes/middlewares/config/constants/utils；backend/scripts/seed_demo.py；backend/migrations记录元数据版本。frontend/src按api/stores/pages/components/common/hooks/router/types/constants/utils；共享table/status/feedback；forms/poll hooks。角色/状态/类型枚举在backend/src/constants/enums.py与frontend/src/constants/enums.js。墨绿邮政凭单视觉，Noto Sans SC/Space Mono双字体来自Google Fonts，离线回退；桌面/平板/手机响应。

.env.example定义COMPOSE_PROJECT_NAME/三端口/JWT_SECRET/SEED_DEMO；DATABASE_URL/REDIS_URL由Compose注入。启动SEED_DEMO失败只记日志。本地开发pip install -r backend/requirements.txt，设数据库/Redis/JWT环境变量，在backend运行uvicorn src.main:app --reload；前端需/api代理，不能file://。测试/截图/日志放批次test-artifacts/gb-4109，源码不混入。MIT License。
