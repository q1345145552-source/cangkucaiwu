"""Build local route/evidence inventory without connecting to any database."""
from fixtures import *
import inspect,re,subprocess,hashlib,xml.etree.ElementTree as ET
base='bc903a55c60c865f8eb95a4e6374ef5325ab4685'
requests=json.loads((OUT/'target-requests.json').read_text())
rows=[]
selected={'users':None,'payment_accounts':None,'expense_fund':None,
'employees':{'create_employee','update_employee','resign_employee','delete_employee','bind_existing_accounts'},
'reimbursement':{'review_reimb','pay_reimb','revoke_payment','list_reimbursements','get_reimb_detail'},
'config_api':{'get_work_schedule_settings','set_work_schedule_settings'},
'overtime':{'set_overtime_limit'},'suppliers':{'set_price_threshold','set_approval_threshold','set_concentration_threshold','set_match_policy'},
'expense_approval':{'set_threshold'},'auth':{'change_password'}}
for route in app.routes:
    endpoint=getattr(route,'endpoint',None)
    if not endpoint or not hasattr(route,'methods'):continue
    module=endpoint.__module__.split('.')[-1];name=endpoint.__name__
    if module not in selected or selected[module] is not None and name not in selected[module]:continue
    for method in sorted(route.methods):
        path=route.path
        matched=[r['id'] for r in requests if r.get('method')==method and re.fullmatch(re.sub(r'\{[^}]+\}',r'[^/]+',path),'/api/v1'+r.get('path',''))]
        source=str(Path(inspect.getsourcefile(endpoint)).relative_to(ROOT))+':'+str(inspect.getsourcelines(endpoint)[1])
        fields={}
        for parameter in getattr(route.dependant,'body_params',[]):
            model=parameter.type_
            fields[parameter.name]={k:str(v.annotation) for k,v in getattr(model,'model_fields',{}).items()} or str(model)
        action=name;roles='沿用原读取菜单、角色及授权仓库范围；本轮未扩大读取字段';state='既有状态约束';handoff='无资金交接';audit='既有读取无业务写入'
        if method!='GET':
            roles='管理员在授权范围内操作；主管、财务拒绝；原菜单鉴权仍保留'
            audit='既有写日志；涉及账户配置、资金核验批准执行另有同事务字段/证据历史'
            if name in ('resign_employee','delete_employee'):
                roles='主管/财务保留原员工业务操作，但不改变登录状态；管理员管理登录状态还须通过目标账号角色、全部仓库检查'
            elif name=='update_employee':roles='主管/财务保留原业务字段；user_id/employee_no/password 仅管理员；原薪资字段问题不在本轮修复'
            elif name=='change_password':roles='现有有效登录身份，本人旧密码校验；不需账号管理权限'
            elif name=='create_transfer':roles='主管拒绝；管理员、财务保留既有调拨能力和菜单约束；未新增调拨审批流程'
            elif module=='expense_fund':
                if name in ('add_item','upload_new_item_receipt'):roles='主管/财务仅本人受益账户；管理员可代录；角色与菜单及仓库共同约束'
                elif name=='submit_recharge_request':roles='主管/财务/管理员本人已有活跃备用金账户；不再隐式开户'
                elif name=='topup_account':roles='所有角色拒绝，旧直拨入口关闭'
                elif name=='batch_review':roles='verify：财务/管理员独立核验；approve/reject：管理员；全部明细先校验，本人/关联员工拒绝';state='pending→verified→approved；未付款待处理可驳回；已批准/已付不可借驳回退款';handoff='登记→凭证核验→管理员批准；关联报销另行独立付款'
                elif name=='review_recharge_request':roles='verify：独立财务/管理员；approve/reject：独立管理员';state='pending→verified→approved_ready；核验及批准均不出款';handoff='申请人→独立核验人→管理员'
                elif name=='execute_recharge':roles='独立有权限财务；财务本人申请允许独立管理员执行；实际申请人/受益人/员工关联均校验';state='approved_ready+匹配批准证据→executed；重复409';handoff='管理员批准→独立资金执行人'
            elif name=='review_reimb':roles='非备用金报销沿用原鉴权；只修父子归属和事务；备用金关联批准须独立管理员且有核验证据';state='沿用可审批父单状态；整批ID唯一、存在、属于父单、状态合法；连带备用金同仓同受益人';handoff='只改变合法当前父单及其关联状态；批准不自动付款'
            elif name=='pay_reimb':roles='非备用金付款原权限不变；备用金关联须有效管理员批准及独立财务/财务本人申请的独立管理员';state='已批准/部分批准且未付；备用金还须批准证据';handoff='仅备用金路径收紧批准→执行'
            elif name=='revoke_payment':roles='停用守卫保持拒绝，不能恢复';state='所有状态拒绝'
        groups={'users':'A','employees':'A','auth':'A','payment_accounts':'B','expense_fund':'C','reimbursement':'E','config_api':'D','overtime':'D','suppliers':'D','expense_approval':'D'}
        if name in ('fund_settings','update_settings'):groups[module]='D'
        rows.append({'编号':f'{groups[module]}-{len(rows)+1:02}','动作':action,'HTTP方法与路径':method+' '+path,'后端守卫位置':source,
            '输入字段':fields,'角色权限':roles,'对象范围':'授权仓库；写入验证显式 X-Warehouse-ID；账号还检查目标的全部仓库；无头资金账户写从授权对象归属确定',
            '允许状态':state,'审批与执行交接':handoff,'审计':audit,'前端入口':{'users':'/settings 用户管理','employees':'/employees 新建/绑定/登录字段/离职/删除','auth':'个人设置 修改密码','payment_accounts':'/accounts 新建/编辑/启停/删除/调拨','expense_fund':'/expense-fund 开户/用途记录/补充申请/核验/批准/执行','reimbursement':'/reimbursement 审核明细；备用金付款使用后端 can_fund_pay','config_api':'/config-center 只读/管理员保存','overtime':'配置中心 加班上限','suppliers':'配置中心采购规则/供应商专用策略','expense_approval':'配置中心费用门槛'}.get(module),
            '目标接口实测证据':matched,'证据等级':'本地接口实际验证' if matched else '代码静态确认；该注册接口未由本轮目标脚本直接覆盖，另见相关回归',
            '范围限制':'不是全系统权限矩阵；工资、非备用金报销付款、报表导出、完整员工自助未完成'})
(OUT/'action-permissions.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
coverage={'registered_in_round2_scope':len(rows),'target_exercised':sum(bool(r['目标接口实测证据']) for r in rows),'unexercised':[r['HTTP方法与路径'] for r in rows if not r['目标接口实测证据']],'note':'路由级覆盖不代表全部字段/状态组合覆盖；批量核验/批准/驳回分别见目标请求，不以注册一条接口宣称动作全覆盖。'}
(OUT/'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2))
lines=['# 本轮动作权限与入口对照','', '财务在代码中为 staff。所有允许项均叠加现有菜单、有效账号、对象仓库和状态条件；历史全权限不能突破角色上限。字段、位置和请求编号见 action-permissions.json。此表按注册接口列行，以下附表再拆分同接口的账号字段及审批动作。','', '|编号|动作/接口|角色与交接|页面|验证|','|---|---|---|---|---|']
for r in rows:lines.append('|'+ '|'.join([r['编号'],r['HTTP方法与路径'],r['角色权限'],r['前端入口'],', '.join(r['目标接口实测证据']) or '静态/相关回归；目标脚本未直测'])+'|')
lines+=['','## 同接口的动作拆分','','|动作|输入|权限/状态|审计|','|---|---|---|---|',
'|修改用户名/显示名|username/display_name|用户管理只限管理员及原平台超管规则；员工入口 username 只允许劳工目标|既有账号历史|',
'|重置他人密码|password|主管/财务拒绝；管理员须授权目标范围；本人改密走独立接口|不记录密码明文|',
'|启用/停用登录账号|is_active|仅授权管理员，不能用员工离职或删除借权；员工业务状态与账号状态分别处理|账号历史；离职历史 account_disabled 如实记录|',
'|变更角色|role|主管/财务拒绝；管理员仍保留原“不得改角色”限制；不扩大超管能力|既有账号历史|',
'|变更仓库|warehouse_id/warehouse_ids|主管/财务拒绝，全部目标仓库须授权；原同级限制保留|既有账号历史|',
'|变更扩展菜单|extra_permissions|主管/财务拒绝；菜单不能突破硬性角色上限|既有账号历史|',
'|修改账户名称/币种/账号/期初/状态|账户配置字段；未知字段拒绝|仅授权管理员；已发生流水的删除及币种限制仍在|真实对象仓库、实际变更字段；账号/户名/备注脱敏|',
'|核验补充申请|action=verify|财务或管理员；本人及代录受益人/关联员工拒绝；pending|recharge_verify 快照，不出款|',
'|批准补充申请|action=approve|独立管理员；verified+匹配核验证据|recharge_approve 快照，不出款|',
'|驳回补充申请|action=reject|独立管理员；pending/verified/approved_ready，历史已付不可处理|recharge_reject|',
'|执行补充拨付|request_id/payment_account_id/receive_date|有效批准后独立执行；重复/并发只产生一次资金效果|recharge_execute+逐笔拨付+支出，同事务|',
'|批量核验开销|item_ids/action=verify|独立财务/管理员；整批合法 pending，凭证必需|item_verify，不付款|',
'|批量批准开销|item_ids/action=approve|独立管理员；verified+证据；关联报销不自动付款|item_approve|',
'|批量驳回开销|item_ids/action=reject|独立管理员；未批准待处理；已付不能借此退款|item_reject；保留既有未付退款口径|',
'|备用金设置单键写入|key/value|仅 fund_limit、fund_alert_threshold；管理员；其他模块/保留/未知 key 拒绝|既有写日志；不改默认值|',
'|配置中心批量规则写入|作息字段+overtime_limit|管理员；原字段验证和默认值不变|既有写日志|',
'|采购职责专用配置|专用版本、request_key、原因|原额外保护、版本与例外机制不变；通用设置不能写|原采购职责审计|',
'|报销批准/驳回明细|items.item_id/status|整批先校验父子/仓库/重复/状态；任何无效项整批无业务副作用|既有请求日志；合法金额只计当前父单|',
'', '不存在的备用金独立账户配置修改/停用/删除路由没有新建；本轮仅收口已有开户、设置及手工开销编辑/作废入口。完整员工薪资字段/模板规则和普通报销付款分工留待后续，不把它们写成已完成或待确认政策。']
(OUT/'ACTION-PERMISSIONS.md').write_text('\n'.join(lines)+'\n')
old=json.loads((ROOT/'docs/permissions-audit-round1-20261028/requests.json').read_text())
changes=[]
for r in old:
    matching=[n for n in requests if n.get('method')==r['method'] and n.get('path')==r['path'] and n.get('uid')==r['uid']]
    if matching and any(n['actual_status']!=r['status'] for n in matching):
        changes.append({'旧证据':r['id'],'请求':r['method']+' '+r['path'],'旧返回':r['status'],'本轮对照':[{'编号':n['id'],'返回':n['actual_status']} for n in matching],'说明':'旧证据完整保留；本轮使用独立合成场景，业务状态/输入可能不同。禁止将旧越权200作为验收目标。'})
(OUT/'round1-expectation-changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2))
print(json.dumps(coverage,ensure_ascii=False))
